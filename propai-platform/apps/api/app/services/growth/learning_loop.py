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
3) compute_down_rates: service별 down율(ai_feedback down% + verify fail%) → 개선대상 식별.

순수 함수(DB·LLM 무의존)는 단위검증 가능하게 분리:
  _summarize_payload / _to_jsonl_line / _down_rate.
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


# ════════════════════════════════════════════════════════════════════════════
# 순수 함수군 (DB/LLM 무의존 — inline 단위검증 대상)
# ════════════════════════════════════════════════════════════════════════════

def _summarize_payload(payload: Any, *, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    """analysis_ledger payload(dict/str)를 PII 마스킹 + 요약 문자열로 변환한다.

    - capture_service.mask_pii 로 민감 키/값(이메일·전화·주민번호·주소 등) 제거.
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
                              limit: int = 5000) -> dict[str, Any]:
    """learning_examples 의 (input_summary, good_output) 페어를 JSONL 문자열로 생성.

    ★생성까지만 — 파인튜닝 잡은 절대 트리거하지 않는다(사람 승인 후 수동 실행).
    기본은 status='active'(사람이 promote 한 것)만. 옵션으로 candidate 포함 가능.
    service 필터 지정 시 해당 service 만.

    반환: {"count","jsonl","service","statuses"}. jsonl 은 '\n' 구분 문자열.
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
    try:
        rows = (await db.execute(text(
            "SELECT input_summary, good_output FROM learning_examples "
            f"WHERE {where_sql} ORDER BY created_at DESC LIMIT :lim"
        ), params)).fetchall()
        for r in rows:
            lines.append(_to_jsonl_line(r[0] or "", r[1] or ""))
    except Exception as e:  # noqa: BLE001
        logger.warning("L3 데이터셋 생성 실패: %s", str(e)[:160])

    return {
        "count": len(lines),
        "jsonl": "\n".join(lines),
        "service": service,
        "statuses": list(valid),
    }


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
    "compute_down_rates",
    # 순수 함수(단위검증 공개).
    "_summarize_payload", "_to_jsonl_line", "_down_rate",
    # 상수.
    "MAX_CURATE_PER_RUN", "SUMMARY_MAX_CHARS",
    "DOWN_RATE_TARGET_PCT", "DOWN_RATE_MIN_SAMPLES",
]
