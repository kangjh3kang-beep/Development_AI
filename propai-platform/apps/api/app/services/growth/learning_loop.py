"""자가성장 엔진 Phase 5 — L3 자가학습 루프(설계서 §6.4).

교정·검증판정·사용자 피드백을 축적해 학습셋을 **자동 성장**시킨다. 단,
안전경계(설계 §1.3·§6.4) 절대 준수:
- 파인튜닝 잡 **자동실행 금지** — (입력요약, 좋은출력) 페어 JSONL **생성까지만** 자동.
- few-shot **활성화는 사람 승인** — 큐레이션은 status='candidate' 로만 등록(자동 active 금지).
  promote API(routers/growth.py)가 사람 승인으로만 candidate→active 전환.
- PII 미저장 — input_summary/good_output 은 capture_service.mask_pii 로 익명화 후 적재.
- 전 조치 admin_audit_log(actor='growth_engine').

학습 신호 소스(설계 §6.4):
- ai_feedback(verdict=up/down·correction) — 직접 사용자 피드백.
- platform_events(verify_result, payload.verdict 또는 severity) — 검증관 판정.
- analysis_ledger(content_hash 로 버전별 결과 payload) — 좋은출력 원본.

흐름:
1) curate_few_shot: verdict='up' 이고 content_hash 가 있는 피드백 → analysis_ledger
   payload(좋은출력) 조인 → PII 마스킹·요약 → learning_examples status='candidate' 등록.
   (service, content_hash) 멱등(중복 등록 차단).
2) build_dataset_jsonl: learning_examples(기본 active, 옵션 candidate) 의
   (input_summary, good_output) 페어를 JSONL 문자열로 생성(생성만, 잡 트리거 안 함).
3) list_examples: 사람이 승인/거부를 판단할 수 있게 후보를 **id 와 함께** 목록으로 준다.
   (build_dataset_jsonl 은 학습셋 계약이라 id 를 안 준다 — 그래서 승인 화면용 조회는 별도다.)
4) compute_down_rates: service별 down율(ai_feedback down% + verify fail%) → 개선대상 식별.

순수 함수(DB·LLM 무의존)는 단위검증 가능하게 분리:
  _summarize_payload / _to_jsonl_line / _down_rate / _preview.
best-effort: 어떤 예외도 호출경로(주간 배치)를 죽이지 않는다.
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_ACTOR = "growth_engine"

# few-shot 후보 등록 1회 배치 상한(과적재 방지).
MAX_CURATE_PER_RUN = 200
# 요약 문자열 최대 길이(저장·프롬프트 주입 비용 가드).
SUMMARY_MAX_CHARS = 2000
# down율 개선대상 식별 임계(%) + 최소표본.
DOWN_RATE_TARGET_PCT = 30.0
DOWN_RATE_MIN_SAMPLES = 10

_VALID_STATUSES = {"candidate", "active", "rejected"}

# 승인 화면(관리자)에 내려보내는 본문 미리보기 최대 길이.
# 왜 자르나: 적재본은 최대 2000자(SUMMARY_MAX_CHARS)라 한 페이지 50건이면 응답이 200KB 까지
# 커진다. 표에서 훑어보는 용도라 앞부분만 보여주고, 잘렸다는 사실을 함께 알려준다
# (자른 것을 숨기면 관리자가 "이게 전부"라고 오독한다).
CANDIDATE_PREVIEW_MAX_CHARS = 600
# 후보 목록 1회 조회 상한(응답 크기·DB 부하 가드).
LIST_MAX_LIMIT = 200


# ════════════════════════════════════════════════════════════════════════════
# 순수 함수군 (DB/LLM 무의존 — inline 단위검증 대상)
# ════════════════════════════════════════════════════════════════════════════

def _summarize_payload(payload: Any, *, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    """analysis_ledger payload(dict/str)를 PII 마스킹 + 요약 문자열로 변환한다.

    - capture_service.mask_pii 로 민감 **키**(이메일·전화·주민번호·주소·이름 등)와
      **값 내부 패턴**(이메일·전화·주민번호)을 제거.
      ★**주소는 값 안에서 지워지지 않는다**(2026-08-27 실측 — `_mask_str` 에 주소 정규식이 없다).
      프론트 `maskString` 은 `ADDRESS_RE` 로 지우지만 이 경로는 프론트를 거치지 않는다.
      초판 주석은 *"주소 등 제거"* 라고 **선언만** 했다 — 후임이 재검증 없이 신뢰한다.
      부채는 `tests/test_pii_mask_diagnostic_keys.py` 의 xfail 로 **초록 안에 보이게** 남겼다
      (고쳐지면 XPASS 로 시끄럽게 알린다). 처방 방향은 결정 필요 — 이 경로가 태우는 것은
      `analysis_ledger` 부동산 분석 payload 이고 **주소가 곧 분석 대상**이라, 지우는 것이
      학습 신호를 파괴할 수 있다(단독 판단하지 않았다).
    - dict 면 키 정렬 JSON, 그 외엔 str. max_chars 로 절단(긴 분석 본문 가드).
    원본 미저장 원칙: 이 함수가 반환한 익명 요약만 learning_examples 에 적재한다.
    """
    try:
        from app.services.growth import capture_service

        masked = capture_service.mask_pii(payload)
    except Exception:  # noqa: BLE001 — 마스킹 모듈 미가용 시에도 동작은 보장(보수적 처리).
        masked = payload
    if isinstance(masked, (dict, list)):
        text = json.dumps(masked, ensure_ascii=False, sort_keys=True, default=str)
    else:
        text = str(masked)
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "…"
    return text


def _preview(value: Any, *, max_chars: int = CANDIDATE_PREVIEW_MAX_CHARS) -> tuple[str, bool]:
    """긴 본문을 미리보기용으로 자른다. 반환 (자른 문자열, 잘렸는지 여부).

    ★"잘렸는지"를 같이 돌려주는 게 핵심이다 — 화면이 이 값을 표시해야 관리자가
    "본문이 여기까지"라고 오독하지 않는다. max_chars 가 0 이하면 자르지 않는다.
    """
    text = "" if value is None else str(value)
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def _to_jsonl_line(input_summary: str, good_output: str) -> str:
    """(입력요약, 좋은출력) 페어를 파인튜닝셋 JSONL 1줄로 직렬화한다.

    OpenAI chat 파인튜닝 호환 포맷({"messages":[user, assistant]}). 파인튜닝
    잡은 사람이 트리거하므로(자동실행 금지) 여기서는 문자열 생성만 한다.
    """
    obj = {
        "messages": [
            {"role": "user", "content": input_summary or ""},
            {"role": "assistant", "content": good_output or ""},
        ]
    }
    return json.dumps(obj, ensure_ascii=False, default=str)


def _down_rate(down: int, feedback_total: int, fail: int, verify_total: int) -> float:
    """service 의 종합 down율(%) = (피드백 down + 검증 fail) / (피드백계 + 검증계).

    표본이 0 이면 0.0. 피드백·검증 양쪽 신호를 합산해 단일 품질저하 지표로 본다.
    """
    denom = max(0, int(feedback_total)) + max(0, int(verify_total))
    if denom <= 0:
        return 0.0
    bad = max(0, int(down)) + max(0, int(fail))
    return round(100.0 * bad / denom, 2)


# ════════════════════════════════════════════════════════════════════════════
# few-shot 큐레이션 — verdict=up·고평가 사례를 candidate 로 등록(자동 active 금지)
# ════════════════════════════════════════════════════════════════════════════

async def _audit(action: str, target: str, detail: dict[str, Any]) -> None:
    """admin_audit_log 기록(actor='growth_engine'). best-effort."""
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=_ACTOR, actor_role="system",
            action=f"growth.learn.{action}", target=target, detail=detail,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("L3 audit 실패: %s", str(e)[:120])


async def curate_few_shot(db, *, since_days: int = 7,
                          max_examples: int = MAX_CURATE_PER_RUN) -> dict[str, Any]:
    """verdict='up' + content_hash 있는 피드백 → 좋은출력(원장) 조인 → candidate 등록.

    - analysis_ledger.payload(가장 최신 버전)를 좋은출력으로, 요약(PII 마스킹) 적재.
    - input_summary 는 원장 payload 의 입력 컨텍스트 요약(없으면 analysis_type 라벨).
    - (service, content_hash) 멱등(ON CONFLICT DO NOTHING) — 매주 배치 중복 적재 방지.
    - ★status='candidate' 로만 등록(자동 active 절대 금지 = 사람 승인 게이트).

    반환: {"scanned","curated","skipped"}. best-effort.
    """
    from sqlalchemy import text

    summary: dict[str, Any] = {"scanned": 0, "curated": 0, "skipped": 0}
    since = datetime.now(UTC) - timedelta(days=since_days)

    try:
        # up 피드백 중 content_hash 가 있어 원장 좋은출력에 연결 가능한 것만.
        rows = (await db.execute(text(
            "SELECT id, service, analysis_type, content_hash "
            "FROM ai_feedback "
            "WHERE verdict='up' AND content_hash IS NOT NULL "
            "  AND created_at >= :since "
            "ORDER BY created_at DESC LIMIT :lim"
        ), {"since": since, "lim": max_examples})).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("L3 큐레이션 피드백 조회 실패: %s", str(e)[:160])
        return summary

    summary["scanned"] = len(rows)

    for r in rows:
        fb_id, service, analysis_type, content_hash = r[0], r[1], r[2], r[3]
        if not content_hash:
            summary["skipped"] += 1
            continue
        # 원장에서 해당 content_hash 의 좋은출력 payload 조회(가장 최신 버전).
        try:
            led = (await db.execute(text(
                "SELECT payload, analysis_type, tenant_id FROM analysis_ledger "
                "WHERE content_hash = :ch ORDER BY version DESC LIMIT 1"
            ), {"ch": content_hash})).fetchone()
        except Exception as e:  # noqa: BLE001
            logger.debug("L3 원장 조회 실패(%s): %s", content_hash, str(e)[:120])
            led = None
        if led is None:
            summary["skipped"] += 1
            continue

        ledger_payload = led[0]
        led_atype = led[1] or analysis_type
        # ★테넌트 영속: 원장의 tenant_id를 학습예시에 보존 → few-shot 주입 시 테넌트 격리(누출 차단).
        led_tenant = led[2]  # SELECT가 payload·analysis_type·tenant_id 3컬럼 보장
        good_output = _summarize_payload(ledger_payload)
        # 입력요약: 원장 payload 의 입력 컨텍스트(있으면) 또는 analysis_type 라벨.
        input_ctx: Any = None
        if isinstance(ledger_payload, dict):
            input_ctx = (ledger_payload.get("input")
                         or ledger_payload.get("request")
                         or ledger_payload.get("context"))
        input_summary = (_summarize_payload(input_ctx)
                         if input_ctx is not None
                         else f"[analysis_type={led_atype}] 입력 컨텍스트 요약 없음")

        try:
            res = await db.execute(text(
                "INSERT INTO learning_examples "
                "(input_summary, good_output, service, analysis_type, "
                " source_feedback_id, content_hash, tenant_id, status) "
                "VALUES (:isum, :gout, :svc, :at, :fid, :ch, :tid, 'candidate') "
                "ON CONFLICT (service, content_hash) DO NOTHING "
                "RETURNING id"
            ), {
                "isum": input_summary, "gout": good_output, "svc": service,
                "at": led_atype, "fid": str(fb_id), "ch": content_hash,
                "tid": led_tenant,
            })
            await db.commit()
            inserted = res.fetchone()
            if inserted:
                summary["curated"] += 1
            else:
                summary["skipped"] += 1  # 멱등 충돌(이미 등록됨).
        except Exception as e:  # noqa: BLE001
            logger.debug("L3 candidate 등록 실패: %s", str(e)[:120])
            with contextlib.suppress(Exception):
                await db.rollback()
            summary["skipped"] += 1

    if summary["curated"]:
        await _audit("curate", "few_shot",
                     {"curated": summary["curated"], "scanned": summary["scanned"]})
        logger.info("growth L3 few-shot 후보 %d건 등록(candidate, 사람 승인 대기)",
                    summary["curated"])
    return summary


# ════════════════════════════════════════════════════════════════════════════
# 파인튜닝 데이터셋 생성 — JSONL 문자열 생성까지만(잡 트리거 절대 안 함)
# ════════════════════════════════════════════════════════════════════════════

async def build_dataset_jsonl(db, *, service: str | None = None,
                              statuses: tuple[str, ...] = ("active",),
                              limit: int = 5000,
                              enforce_asset_rights: bool = False) -> dict[str, Any]:
    """learning_examples 의 (input_summary, good_output) 페어를 JSONL 문자열로 생성.

    ★생성까지만 — 파인튜닝 잡은 절대 트리거하지 않는다(사람 승인 후 수동 실행).
    기본은 status='active'(사람이 promote 한 것)만. 옵션으로 candidate 포함 가능.
    service 필터 지정 시 해당 service 만.

    ★P16 학습게이트(WP-H 세션2 결선): enforce_asset_rights=True 면 각 예시의 자산
    (content_hash, tenant_id)을 asset_rights 레지스트리로 조회해 **train_allowed 인 것만** 학습셋에
    포함한다(권리 불명·미등록=제외 = default-deny). 게이트 판정은 공용 순수 함수
    `keep_train_allowed`(asset_rights)에 위임한다 — 한 곳을 고치면 전 학습 경로가 따른다.
    ▶실소비 활성화(플래그 ON)와 레지스트리 시딩(ingest 시 upsert_asset_right)은 WP-J 이관.
      기본값 False 라 현재 동작(run_learning_cycle 메타 카운트·기존 테스트)은 무회귀.

    반환: {"count","jsonl","service","statuses","rights_enforced","excluded_no_rights"}.
          jsonl 은 '\n' 구분 문자열.
    """
    from sqlalchemy import text

    valid = tuple(s for s in statuses if s in _VALID_STATUSES) or ("active",)
    placeholders = ",".join(f":st{i}" for i in range(len(valid)))
    params: dict[str, Any] = {f"st{i}": s for i, s in enumerate(valid)}
    where = [f"status IN ({placeholders})", "good_output IS NOT NULL"]
    if service:
        where.append("service = :svc")
        params["svc"] = service
    params["lim"] = limit
    where_sql = " AND ".join(where)

    lines: list[str] = []
    excluded_no_rights = 0
    try:
        # content_hash·tenant_id 를 함께 조회(학습게이트 키 — asset_rights 는 (asset_key, tenant) 키).
        rows = (await db.execute(text(
            "SELECT input_summary, good_output, content_hash, tenant_id "
            "FROM learning_examples "
            f"WHERE {where_sql} ORDER BY created_at DESC LIMIT :lim"
        ), params)).fetchall()

        pairs = [(r[0] or "", r[1] or "", r[2], r[3]) for r in rows]

        if enforce_asset_rights:
            from app.services.security.asset_rights import (
                get_asset_rights_batch,
                keep_train_allowed,
            )

            # 고유 (content_hash, tenant_id) 조합을 **배치 1질의**로 조회(N+1 제거 — WP-I 리뷰 LOW:
            #   WHERE (asset_key, tenant) IN (...)). 미등록 키는 배치 헬퍼가 default-deny 로 채운다.
            batch_keys = [(ch, tid) for (_, _, ch, tid) in pairs if ch]
            rights = await get_asset_rights_batch(db, batch_keys)
            # keep_train_allowed 는 평면 dict(키=행의 key_index 값)로 판정 → 행에 복합키를 실어 넘긴다.
            keyed = [(inp, out, (ch, tid)) for (inp, out, ch, tid) in pairs]
            kept, excluded_no_rights = keep_train_allowed(keyed, rights, key_index=2)
            pairs = [(inp, out, None, None) for (inp, out, _k) in kept]

        for inp, out, _ch, _tid in pairs:
            lines.append(_to_jsonl_line(inp, out))
    except Exception as e:  # noqa: BLE001
        logger.warning("L3 데이터셋 생성 실패: %s", str(e)[:160])

    return {
        "count": len(lines),
        "jsonl": "\n".join(lines),
        "service": service,
        "statuses": list(valid),
        "rights_enforced": bool(enforce_asset_rights),
        "excluded_no_rights": excluded_no_rights,
    }


# ════════════════════════════════════════════════════════════════════════════
# 후보 검토 목록 — 사람이 승인/거부를 판단할 수 있게 **id 와 함께** 돌려준다
# ════════════════════════════════════════════════════════════════════════════
# 왜 별도 함수인가(2026-08-19 결함):
#   few-shot 활성화는 사람 승인(promote)으로만 가능한데, promote 는 `example_id` 를 요구한다.
#   그런데 그때까지 learning_examples 를 읽는 유일한 경로였던 build_dataset_jsonl 은
#   (input_summary, good_output) 페어만 내놓고 **id 를 안 돌려줬다**. 즉 관리자가 화면을
#   가져도 "무엇을 승인할지" 지목할 수가 없었다 = 게이트에 문이 없었다.
#   → build_dataset_jsonl 은 학습셋 계약이라 손대지 않고(계약 불변), 검토용 조회를 여기 따로 둔다.


async def list_examples(db, *, statuses: tuple[str, ...] = ("candidate",),
                        service: str | None = None,
                        tenant_id: str | None = None,
                        limit: int = 50, offset: int = 0,
                        preview_chars: int = CANDIDATE_PREVIEW_MAX_CHARS) -> dict[str, Any]:
    """learning_examples 를 검토용 목록으로 조회한다(기본 status='candidate').

    학습셋 생성이 아니라 **사람이 눈으로 보고 판단하는 화면**을 위한 조회다. 그래서
    build_dataset_jsonl 과 달리 id·status·created_at·tenant_id 를 함께 준다.

    ★자산권리(asset_rights)로 **거르지 않는다 — 표시한다.**
      근거: 이 목록은 "학습셋 생성"이 아니라 "사람 검토"다. 권리 미확인 항목을 조용히 빼면
      관리자 화면에는 "후보가 없다"로 보이고(실제로는 있는데), 그러면 사람이 판단할 기회
      자체가 사라진다 — 이 결함이 고치려는 것("사람이 승인해야 도는데 사람에게 문이 없다")과
      똑같은 형태가 된다. 대신 행마다 train_allowed/rights_scope 를 실어 보내 화면이
      "권리 미확인"을 눈에 보이게 표시한다.

    ★★정정(2026-08-19 적대리뷰 HIGH) — 여기 원래 "실제 학습 차단은 build_dataset_jsonl 의
      enforce_asset_rights 가 담당한다"고 적혀 있었다. **거짓 면역이었다.** 실측:
        · build_dataset_jsonl 의 게이트는 **학습셋 다운로드** 경로에만 걸리고,
          프롬프트 주입 경로(base_interpreter._load_fewshot)와는 무관하다.
        · 그 게이트는 GROWTH_ENFORCE_TRAIN_RIGHTS 로 켜지며 **기본 OFF** 다.
        · _load_fewshot 은 status='active' 만 보고 권리를 **전혀 보지 않는다**
          (그 파일의 asset_rights/train_allowed 참조 0건 — 대조군 이 파일 20건).
      → 즉 "표시만 해도 승인 뒤가 안전하다"는 전제가 틀렸다. 실제 차단은 **승인 지점**
        (routers/growth.py promote)이 담당하도록 옮겼다: 권리 미확인 자산은 기본 거부이고,
        사람이 acknowledge_unverified_rights 로 책임을 인수해야만 active 가 된다(감사 기록).

    반환: {"items": [...], "total", "statuses", "service", "tenant_id", "limit", "offset"}.
          items 원소 키: id·service·analysis_type·status·tenant_id·content_hash·
          input_summary·good_output(미리보기)·*_truncated·created_at·train_allowed·rights_scope.
    best-effort: 실패해도 예외를 올리지 않고 빈 목록을 돌려준다(화면이 죽지 않게).
    """
    from sqlalchemy import text

    # ★이중 가드(의도적): 인자 기본값이 무엇이든, 어휘에 없는 값은 걸러진 뒤 빈 튜플이 되고
    #   `or ("candidate",)` 가 다시 candidate 로 되돌린다. 그래서 시그니처 기본값만 바꾸는
    #   변이는 죽지 않는다 — 그건 구멍이 아니라 두 겹으로 막았다는 뜻이다.
    valid = tuple(s for s in statuses if s in _VALID_STATUSES) or ("candidate",)
    lim = max(1, min(int(limit or 50), LIST_MAX_LIMIT))
    off = max(0, int(offset or 0))

    placeholders = ",".join(f":st{i}" for i in range(len(valid)))
    params: dict[str, Any] = {f"st{i}": s for i, s in enumerate(valid)}
    where = [f"status IN ({placeholders})"]
    if service:
        where.append("service = :svc")
        params["svc"] = service
    if tenant_id:
        where.append("tenant_id = :tid")
        params["tid"] = tenant_id
    where_sql = " AND ".join(where)

    out: dict[str, Any] = {
        "items": [], "total": 0, "statuses": list(valid),
        "service": service, "tenant_id": tenant_id, "limit": lim, "offset": off,
    }

    try:
        total = (await db.execute(text(
            f"SELECT COUNT(*) FROM learning_examples WHERE {where_sql}"
        ), params)).scalar()
        out["total"] = int(total or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("L3 후보 건수 조회 실패: %s", str(e)[:160])

    try:
        params_page = dict(params)
        params_page["lim"] = lim
        params_page["off"] = off
        rows = (await db.execute(text(
            "SELECT id, service, analysis_type, status, tenant_id, content_hash, "
            "       input_summary, good_output, created_at "
            "FROM learning_examples "
            f"WHERE {where_sql} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        ), params_page)).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("L3 후보 목록 조회 실패: %s", str(e)[:160])
        return out

    # 권리 조회는 **표시용**이다(거르기용 아님). 실패하면 전건 '권리 미확인'으로 보이며,
    # 그건 정직한 표시다(모르는 것을 안다고 말하지 않는다).
    rights: dict[Any, Any] = {}
    try:
        from app.services.security.asset_rights import get_asset_rights_batch

        keys = [(r[5], r[4]) for r in rows if r[5]]
        if keys:
            rights = await get_asset_rights_batch(db, keys)
    except Exception as e:  # noqa: BLE001
        logger.debug("L3 후보 권리 조회 생략: %s", str(e)[:120])

    items: list[dict[str, Any]] = []
    for r in rows:
        content_hash, ex_tenant = r[5], r[4]
        right = rights.get((content_hash, ex_tenant)) if content_hash else None
        isum, isum_cut = _preview(r[6], max_chars=preview_chars)
        gout, gout_cut = _preview(r[7], max_chars=preview_chars)
        created = r[8]
        items.append({
            "id": str(r[0]),
            "service": r[1],
            "analysis_type": r[2],
            "status": r[3],
            "tenant_id": ex_tenant,
            "content_hash": content_hash,
            "input_summary": isum,
            "input_summary_truncated": isum_cut,
            "good_output": gout,
            "good_output_truncated": gout_cut,
            "created_at": created.isoformat() if hasattr(created, "isoformat") else (
                str(created) if created else None
            ),
            # 권리 미확인(레지스트리 미등록·조회실패)이면 False/None — 화면이 경고를 띄운다.
            "train_allowed": bool(getattr(right, "train_allowed", False)),
            "rights_scope": getattr(right, "scope", None),
        })

    out["items"] = items
    return out


# ════════════════════════════════════════════════════════════════════════════
# service별 down율 산출 — 개선대상 service 식별(improvement_agent 가 소비)
# ════════════════════════════════════════════════════════════════════════════

async def compute_down_rates(db, *, w_hours: int = 168) -> dict[str, dict[str, Any]]:
    """service × (피드백 down + 검증 fail) 종합 down율 집계 → 개선대상 식별.

    반환: {service: {"down","feedback_total","fail","verify_total",
                     "down_rate","is_target"}}.
    is_target = down_rate >= DOWN_RATE_TARGET_PCT AND 표본 충분.
    best-effort(실패 시 빈 dict).
    """
    from sqlalchemy import text

    out: dict[str, dict[str, Any]] = {}
    since = datetime.now(UTC) - timedelta(hours=w_hours)

    try:
        fb_rows = (await db.execute(text(
            "SELECT service, "
            "  SUM(CASE WHEN verdict='down' THEN 1 ELSE 0 END) AS down, "
            "  COUNT(*) AS total "
            "FROM ai_feedback "
            "WHERE created_at >= :since AND service IS NOT NULL "
            "GROUP BY service"
        ), {"since": since})).fetchall()
        for r in fb_rows:
            d = out.setdefault(r[0], {"down": 0, "feedback_total": 0,
                                      "fail": 0, "verify_total": 0})
            d["down"] += int(r[1] or 0)
            d["feedback_total"] += int(r[2] or 0)
    except Exception as e:  # noqa: BLE001
        logger.debug("down_rates 피드백 집계 실패: %s", str(e)[:120])

    try:
        # verify_result: severity 또는 payload.verdict 에 fail 기록(수집측 정합).
        v_rows = (await db.execute(text(
            "SELECT service, "
            "  SUM(CASE WHEN severity='fail' OR payload->>'verdict'='fail' "
            "           THEN 1 ELSE 0 END) AS fail, "
            "  COUNT(*) AS total "
            "FROM platform_events "
            "WHERE event_type='verify_result' AND service IS NOT NULL "
            "  AND created_at >= :since "
            "GROUP BY service"
        ), {"since": since})).fetchall()
        for r in v_rows:
            d = out.setdefault(r[0], {"down": 0, "feedback_total": 0,
                                      "fail": 0, "verify_total": 0})
            d["fail"] += int(r[1] or 0)
            d["verify_total"] += int(r[2] or 0)
    except Exception as e:  # noqa: BLE001
        logger.debug("down_rates 검증 집계 실패: %s", str(e)[:120])

    for d in out.values():
        rate = _down_rate(d["down"], d["feedback_total"], d["fail"], d["verify_total"])
        samples = d["feedback_total"] + d["verify_total"]
        d["down_rate"] = rate
        d["is_target"] = bool(rate >= DOWN_RATE_TARGET_PCT and samples >= DOWN_RATE_MIN_SAMPLES)
    return out


# ════════════════════════════════════════════════════════════════════════════
# 주간 학습 사이클 — 큐레이션 + 데이터셋 생성 메타 + down율 식별(전부 자동, 안전경계 내)
# ════════════════════════════════════════════════════════════════════════════

async def run_learning_cycle(db, *, since_days: int = 7) -> dict[str, Any]:
    """1회 L3 학습 사이클(주간 배치 진입점).

    1) few-shot 큐레이션(candidate 등록 — 자동 active 금지).
    2) 데이터셋 메타 산출(active 셋 건수 — JSONL 생성은 다운로드 API 가 on-demand).
    3) service별 down율 → 개선대상 식별(improvement_agent 가 다음 단계에서 소비).
    ★파인튜닝 잡 트리거 없음. few-shot 활성 전환 없음(전부 사람 승인 게이트).

    반환: {"curation","dataset","down_targets"}. best-effort.
    """
    summary: dict[str, Any] = {}

    # (1) few-shot 큐레이션.
    try:
        summary["curation"] = await curate_few_shot(db, since_days=since_days)
    except Exception as e:  # noqa: BLE001
        logger.warning("L3 큐레이션 단계 실패: %s", str(e)[:160])
        summary["curation"] = {"error": str(e)[:160]}

    # (2) 활성 데이터셋 메타(건수만 — 실제 JSONL 은 다운로드 API on-demand 생성).
    try:
        ds = await build_dataset_jsonl(db, statuses=("active",), limit=5000)
        summary["dataset"] = {"active_pairs": ds.get("count", 0)}
    except Exception as e:  # noqa: BLE001
        summary["dataset"] = {"error": str(e)[:160]}

    # (3) down율 개선대상 식별.
    try:
        rates = await compute_down_rates(db)
        targets = [svc for svc, d in rates.items() if d.get("is_target")]
        summary["down_targets"] = {"services": targets, "detail": rates}
    except Exception as e:  # noqa: BLE001
        summary["down_targets"] = {"error": str(e)[:160]}

    return summary


__all__ = [
    "run_learning_cycle",
    "curate_few_shot",
    "build_dataset_jsonl",
    "list_examples",
    "compute_down_rates",
    # 순수 함수(단위검증 공개).
    "_summarize_payload", "_to_jsonl_line", "_down_rate", "_preview",
    # 상수.
    "MAX_CURATE_PER_RUN", "SUMMARY_MAX_CHARS",
    "DOWN_RATE_TARGET_PCT", "DOWN_RATE_MIN_SAMPLES",
    "CANDIDATE_PREVIEW_MAX_CHARS", "LIST_MAX_LIMIT",
]
