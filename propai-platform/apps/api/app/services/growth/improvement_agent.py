"""자가성장 엔진 Phase 4 — L2 자가개선 제안 에이전트(설계서 §6.3).

recommended_action='propose_pr' 인 critical 인사이트 + 관련 스택트레이스 + 관련
소스(읽기 전용)로 **진단 + 패치 제안**을 LLM 으로 생성하고, 그 결과를
**제안 아티팩트**로 platform_insights 에 저장한다(insight_type='improvement_proposal').

안전경계(절대 준수 — 설계 §6.3, §1.3):
- L2 는 **제안만**. 절대 자동 머지/배포/스키마 변경 금지.
- 이 모듈은 코드를 직접 commit/merge 하지 않는다(아티팩트 생성까지만).
  실제 Draft PR 생성은 growth_pr_task 가 GH_TOKEN 있을 때만 별도 수행(graceful).
- 변경파일 화이트리스트(ALLOWED_PATH_PREFIXES) 밖이거나 금지경로(DENY: 마이그레이션/
  배포스크립트/시크릿)면 제안 자체를 거부한다.
- phase_f DomainAgentTask(confidence_score/requires_approval) 승인게이팅 패턴을 차용:
  제안 아티팩트에 confidence/requires_approval=True 메타를 박아 사람 승인 필수임을 명시.
- LLM 비용가드: 1배치당 최대 제안 수 캡 + base_interpreter 패턴(키 없으면 graceful skip).

best-effort: 어떤 예외도 호출경로(배치)를 죽이지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ACTOR = "growth_engine"

# 1배치당 최대 제안 생성 수(LLM 비용 폭증 방지 — 설계 §8.1).
MAX_PROPOSALS_PER_RUN = 3

# 제안 아티팩트로 저장할 인사이트 타입.
INSIGHT_PROPOSAL = "improvement_proposal"

# Phase 5(L3) — 프롬프트 개선후보 아티팩트 인사이트 타입.
INSIGHT_PROMPT_CANDIDATE = "prompt_candidate"

# 1배치당 최대 프롬프트 개선후보 생성 수(LLM 비용가드).
MAX_PROMPT_CANDIDATES_PER_RUN = 3

# 프롬프트 개선후보 버전 레이블 접두(기본 v2 와 구분되는 후보군 표기).
PROMPT_CANDIDATE_PREFIX = "cand-"

# ── 변경파일 화이트리스트/금지경로(설계 §6.3 가드) ──────────────────────────
# 제안이 건드릴 수 있는 경로 접두사(소스만). PR 봇도 같은 화이트리스트를 강제한다.
ALLOWED_PATH_PREFIXES = (
    "apps/api/app/",
    "apps/api/routers/",
    "apps/api/integrations/",
    "apps/web/components/",
    "apps/web/lib/",
    "apps/web/hooks/",
    "apps/web/app/",
)
# ★절대 금지(자동 코드변경 악용 방지): 마이그레이션·배포·시크릿·CI·인프라.
DENY_PATH_PATTERNS = (
    "migrations/", "alembic/", "deploy", ".env", "secret", "secrets",
    ".github/", "docker", "compose", "Caddyfile", "nginx", "requirements",
    "pyproject", "package.json", "package-lock", "yarn.lock",
)


def is_path_allowed(path: str) -> bool:
    """변경 대상 경로가 화이트리스트 ∈ AND 금지패턴 ∉ 인지 판정(순수 함수)."""
    if not path:
        return False
    p = path.strip().lstrip("/").replace("\\", "/")
    low = p.lower()
    if any(d in low for d in DENY_PATH_PATTERNS):
        return False
    return any(p.startswith(prefix) for prefix in ALLOWED_PATH_PREFIXES)


def _llm_enabled() -> bool:
    """제안 LLM 활성 여부. 키 없으면 비활성(graceful — 규칙기반 진단만 저장)."""
    try:
        from app.services.ai.key_sanitizer import get_clean_env_key

        return bool(get_clean_env_key("ANTHROPIC_API_KEY"))
    except Exception:  # noqa: BLE001
        return bool(os.getenv("ANTHROPIC_API_KEY"))


def _safe_read_source(rel_path: str, max_chars: int = 6000) -> str | None:
    """관련 소스를 읽기 전용으로 읽어 LLM 컨텍스트에 제공(화이트리스트 내만)."""
    if not is_path_allowed(rel_path):
        return None
    try:
        # apps/api 기준 상대경로를 워크트리 루트 기준으로 해석(best-effort).
        here = os.path.dirname(os.path.abspath(__file__))  # .../apps/api/app/services/growth
        root = os.path.abspath(os.path.join(here, "..", "..", "..", "..", ".."))
        full = os.path.join(root, rel_path)
        if not os.path.isfile(full):
            return None
        with open(full, encoding="utf-8") as f:
            return f.read()[:max_chars]
    except Exception as e:  # noqa: BLE001
        logger.debug("소스 읽기 실패(%s): %s", rel_path, str(e)[:120])
        return None


def _guess_source_path(metrics: dict[str, Any]) -> str | None:
    """인사이트 metrics(route/signature/sample)에서 관련 소스 경로 후보를 추정.

    route 가 API 경로면 routers/ 후보, 그 외엔 None(LLM 이 진단만). 추정 실패는 None.
    """
    route = (metrics.get("route") or "").strip()
    sample = str(metrics.get("sample") or "")
    # 스택트레이스 sample 에서 'apps/...py' 파일경로가 보이면 그걸 우선.
    m = re.search(r"(apps/[\w./\-]+\.py)", sample)
    if m and is_path_allowed(m.group(1)):
        return m.group(1)
    # route 가 /api/v1/<resource>/... 면 라우터 파일 추정.
    if route.startswith("/api/"):
        parts = [p for p in route.split("/") if p and not p.startswith("{")]
        # /api/v1/<resource> → routers/<resource>.py 후보.
        if len(parts) >= 3:
            cand = f"apps/api/routers/{parts[2]}.py"
            if is_path_allowed(cand):
                return cand
    return None


def _rule_diagnosis(insight: dict[str, Any]) -> str:
    """LLM 없이도 항상 채워지는 규칙기반 진단(한국어)."""
    m = insight.get("metrics_json") or {}
    itype = insight.get("insight_type")
    if itype == "error_cluster":
        return (f"반복 오류 군집(시그니처 {m.get('signature')}) — route={m.get('route')} "
                f"status={m.get('status_code')}, 시간당 {m.get('per_hour')}건. "
                f"해당 라우터/핸들러의 예외처리·입력검증 점검 필요.")
    if itype == "heal_escalation":
        return (f"자동치유 무효 에스컬레이션({m.get('action_type')}/{m.get('trigger_key')}) — "
                f"근본원인 수동 점검 필요(반복 조치로 해소 안 됨).")
    return f"critical 인사이트({itype}) — 사람 진단 필요."


async def _llm_proposal(insight: dict[str, Any], source_path: str | None,
                        source_text: str | None) -> dict[str, Any] | None:
    """LLM 1콜로 진단+패치제안 생성(base_interpreter LLM 경로 재사용). 실패 시 None."""
    try:
        from app.services.ai.llm_provider import get_llm

        llm = get_llm(timeout=40, max_tokens=1500)
        ctx = {
            "insight_type": insight.get("insight_type"),
            "severity": insight.get("severity"),
            "metrics": insight.get("metrics_json") or {},
            "source_path": source_path,
        }
        prompt = (
            "너는 시니어 백엔드 엔지니어다. 아래 운영 인사이트와 관련 소스를 근거로 "
            "진단과 **최소 변경** 패치 제안을 작성하라. 추측 금지, 근거 기반만.\n"
            "출력은 JSON: {\"diagnosis\": str, \"root_cause\": str, "
            "\"proposed_change\": str, \"affected_files\": [str], \"risk\": str, "
            "\"test_suggestion\": str, \"confidence\": number(0~1)}\n\n"
            f"[인사이트]\n{json.dumps(ctx, ensure_ascii=False, default=str)}\n\n"
            + (f"[관련 소스: {source_path}]\n{source_text}\n" if source_text else "[관련 소스 없음]\n")
        )
        resp = llm.invoke(prompt)
        raw = getattr(resp, "content", None) or str(resp)
        raw = str(raw).strip()
        # ```json 블록 제거(base_interpreter 파서와 동일 관용구).
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        bs, be = raw.find("{"), raw.rfind("}")
        if bs != -1 and be != -1:
            return json.loads(raw[bs:be + 1])
    except Exception as e:  # noqa: BLE001
        logger.debug("L2 LLM 제안 폴백: %s", str(e)[:120])
    return None


async def _store_proposal(db, insight_id: str | None, proposal: dict[str, Any]) -> str | None:
    """제안 아티팩트를 platform_insights 에 INSERT(requires_approval=True). 반환: 새 id."""
    from sqlalchemy import text

    # 변경파일이 전부 화이트리스트 통과해야 제안 저장(하나라도 위반 시 거부).
    files = [f for f in (proposal.get("affected_files") or []) if isinstance(f, str)]
    if files and not all(is_path_allowed(f) for f in files):
        logger.info("L2 제안 거부 — 화이트리스트 밖 파일 포함: %s", files)
        return None

    # phase_f 승인게이팅 패턴: confidence + requires_approval 메타 부착.
    artifact = {
        "source_insight_id": insight_id,
        "requires_approval": True,   # ★사람 승인 필수(자동 머지 절대 금지).
        "auto_merge": False,
        "confidence": float(proposal.get("confidence") or 0.0),
        "affected_files": files,
        "proposal": proposal,
        "pr_status": "draft_only",   # PR 봇이 갱신(GH_TOKEN 없으면 'artifact_only').
    }
    try:
        row = (await db.execute(text(
            "INSERT INTO platform_insights "
            "(insight_type, metrics_json, severity, narrative, recommended_action, status) "
            "VALUES (:it, CAST(:m AS jsonb), 'warn', :narr, 'propose_pr', 'open') "
            "RETURNING id"
        ), {
            "it": INSIGHT_PROPOSAL,
            "m": json.dumps(artifact, ensure_ascii=False, default=str),
            "narr": (proposal.get("diagnosis") or "L2 개선 제안 아티팩트")[:1000],
        })).fetchone()
        await db.commit()
        new_id = str(row[0]) if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning("L2 제안 저장 실패: %s", str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None

    # 감사: 제안 생성도 growth_engine 조치로 기록.
    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=_ACTOR, actor_role="system",
            action="growth.improve.propose", target=new_id or (insight_id or ""),
            detail={"source_insight_id": insight_id, "files": files,
                    "confidence": artifact["confidence"], "requires_approval": True},
        )
    except Exception:  # noqa: BLE001
        pass
    return new_id


async def generate_proposals(db, *, max_proposals: int = MAX_PROPOSALS_PER_RUN,
                             now: datetime | None = None) -> dict[str, Any]:
    """propose_pr critical 인사이트 → 진단+패치 제안 아티팩트 생성·저장.

    LLM 키 없으면 규칙기반 진단만 담아 제안 저장(graceful). 반환:
    {"candidates","proposed","artifacts":[{insight_id,proposal_id,source_path}]}.
    best-effort.
    """
    from sqlalchemy import text

    now = now or datetime.now(timezone.utc)
    summary: dict[str, Any] = {"candidates": 0, "proposed": 0, "artifacts": []}

    try:
        rows = (await db.execute(text(
            "SELECT id, insight_type, severity, metrics_json FROM platform_insights "
            "WHERE recommended_action='propose_pr' AND severity='critical' "
            "  AND status='open' AND insight_type <> :proposal "
            "  AND created_at >= :since "
            "ORDER BY created_at DESC LIMIT 50"
        ), {"proposal": INSIGHT_PROPOSAL, "since": now - timedelta(days=1)})).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("L2 후보 조회 실패: %s", str(e)[:160])
        return summary

    summary["candidates"] = len(rows)
    use_llm = _llm_enabled()

    for r in rows:
        if summary["proposed"] >= max_proposals:
            break
        ins = {"insight_type": r[1], "severity": r[2],
               "metrics_json": r[3] if isinstance(r[3], dict) else {}}
        insight_id = str(r[0])
        source_path = _guess_source_path(ins["metrics_json"])
        source_text = _safe_read_source(source_path) if source_path else None

        proposal: dict[str, Any] | None = None
        if use_llm:
            proposal = await _llm_proposal(ins, source_path, source_text)
        if not proposal:
            # graceful: LLM 미사용/실패 시 규칙기반 진단만(패치는 사람이 작성).
            proposal = {
                "diagnosis": _rule_diagnosis(ins),
                "root_cause": "데이터 부족(규칙기반 진단) — 사람 점검 필요",
                "proposed_change": "수동 진단 필요(LLM 비활성 또는 실패)",
                "affected_files": [source_path] if source_path else [],
                "risk": "unknown", "test_suggestion": "", "confidence": 0.2,
            }
        pid = await _store_proposal(db, insight_id, proposal)
        if pid:
            summary["proposed"] += 1
            summary["artifacts"].append({
                "insight_id": insight_id, "proposal_id": pid,
                "source_path": source_path,
            })
    if summary["proposed"]:
        logger.info("growth L2 제안 %d건 생성(아티팩트 저장, PR 미생성)", summary["proposed"])
    return summary


# ════════════════════════════════════════════════════════════════════════════
# Phase 5(L3) — 프롬프트 자가튜닝: 개선후보 생성 → A/B 후보군 등록(자동 채택 금지)
# ════════════════════════════════════════════════════════════════════════════
# down율 높은 service 의 실패사례(verify fail·feedback down·correction)를 LLM 이
# 분석해 **프롬프트 개선안 후보**를 생성한다. 결과는:
#  (a) platform_insights(insight_type='prompt_candidate') 아티팩트로 저장(사람 검토용).
#  (b) platform_settings('prompt_candidates.<service>') 에 후보 버전 레이블을 **등록**한다.
# ★자동 채택 아님 — 설계 §6.2 안전장치(사전등록 후보군) 하에서만 이후 A/B 가 채택.
#   임의 자동 적용 금지: 이 함수는 후보군에 등록만 하고, 실제 프롬프트 버전 전환(채택)은
#   feature_flags.evaluate(품질지표 기반·가드·감사) 또는 사람 승인을 거친다.

def _new_candidate_label(existing: list[str] | None) -> str:
    """기존 후보 레이블 목록을 보고 새 'cand-N' 레이블을 만든다(순수 함수).

    'cand-1','cand-2',… 의 최대 N+1. 비면 'cand-1'. 임의 버전 텍스트 생성이 아니라
    후보군 슬롯 레이블(추적용)일 뿐, 채택은 별도 안전장치가 통제.
    """
    nums = []
    for v in (existing or []):
        if isinstance(v, str) and v.startswith(PROMPT_CANDIDATE_PREFIX):
            tail = v[len(PROMPT_CANDIDATE_PREFIX):]
            if tail.isdigit():
                nums.append(int(tail))
    nxt = (max(nums) + 1) if nums else 1
    return f"{PROMPT_CANDIDATE_PREFIX}{nxt}"


async def _failure_samples(db, service: str, *, limit: int = 8) -> dict[str, Any]:
    """service 의 최근 실패신호(feedback down·correction + verify fail) 표본 수집."""
    from sqlalchemy import text

    out: dict[str, Any] = {"corrections": [], "down": 0, "fail": 0}
    try:
        rows = (await db.execute(text(
            "SELECT correction FROM ai_feedback "
            "WHERE service = :svc AND verdict='down' AND correction IS NOT NULL "
            "ORDER BY created_at DESC LIMIT :lim"
        ), {"svc": service, "lim": limit})).fetchall()
        # correction 은 사용자 자유 입력 → PII 마스킹 후 표본화.
        from app.services.growth import capture_service
        out["corrections"] = [capture_service._mask_str(str(r[0]))[:500]
                              for r in rows if r[0]]
    except Exception as e:  # noqa: BLE001
        logger.debug("프롬프트후보 실패표본 수집 실패(%s): %s", service, str(e)[:120])
    return out


async def _llm_prompt_candidate(service: str, samples: dict[str, Any]) -> dict[str, Any] | None:
    """LLM 1콜로 프롬프트 개선안 후보를 생성(실패 시 None)."""
    try:
        from app.services.ai.llm_provider import get_llm

        llm = get_llm(timeout=40, max_tokens=1200)
        prompt = (
            "너는 LLM 프롬프트 엔지니어다. 아래 service 의 분석 출력이 사용자 교정·검증 "
            "실패로 품질이 낮다. 실패 표본을 근거로 **프롬프트 개선안 후보**를 작성하라. "
            "추측 금지, 표본 근거만. 출력은 JSON: "
            "{\"diagnosis\": str, \"improved_prompt_addendum\": str, "
            "\"rationale\": str, \"confidence\": number(0~1)}\n\n"
            f"[service]\n{service}\n\n"
            f"[실패 표본(교정 텍스트, PII 마스킹됨)]\n"
            f"{json.dumps(samples.get('corrections') or [], ensure_ascii=False)}\n"
        )
        resp = llm.invoke(prompt)
        raw = getattr(resp, "content", None) or str(resp)
        raw = str(raw).strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
        bs, be = raw.find("{"), raw.rfind("}")
        if bs != -1 and be != -1:
            return json.loads(raw[bs:be + 1])
    except Exception as e:  # noqa: BLE001
        logger.debug("프롬프트후보 LLM 폴백: %s", str(e)[:120])
    return None


async def _register_candidate(db, service: str, label: str,
                              proposal: dict[str, Any]) -> bool:
    """platform_settings('prompt_candidates.<service>') 후보군에 레이블을 등록(채택 아님)."""
    from app.services.growth import schema_guard

    key = f"prompt_candidates.{service}"
    cur = await schema_guard.get_setting(db, key)
    existing: list[str] = []
    if isinstance(cur, dict) and isinstance(cur.get("candidates"), list):
        existing = [str(v) for v in cur["candidates"]]
    if label in existing:
        return True
    existing.append(label)
    value = {
        "candidates": existing,
        # ★active=False: 등록만, 자동 채택 금지(설계 §6.2). 채택은 별도 안전장치.
        "active": False,
        "last_proposal": {
            "label": label,
            "diagnosis": (proposal.get("diagnosis") or "")[:500],
            "rationale": (proposal.get("rationale") or "")[:500],
            "confidence": float(proposal.get("confidence") or 0.0),
        },
    }
    return await schema_guard.set_setting(db, key, value, scope="global",
                                          updated_by=_ACTOR)


async def _store_prompt_candidate(db, service: str, label: str,
                                  proposal: dict[str, Any]) -> str | None:
    """프롬프트 개선후보 아티팩트를 platform_insights 에 INSERT(requires_approval=True)."""
    from sqlalchemy import text

    artifact = {
        "service": service,
        "candidate_label": label,
        "requires_approval": True,   # ★사람 승인/안전장치 하에서만 채택(자동 적용 금지).
        "auto_adopt": False,
        "confidence": float(proposal.get("confidence") or 0.0),
        "proposal": proposal,
    }
    try:
        row = (await db.execute(text(
            "INSERT INTO platform_insights "
            "(insight_type, metrics_json, severity, narrative, recommended_action, status) "
            "VALUES (:it, CAST(:m AS jsonb), 'warn', :narr, 'register_prompt_candidate', 'open') "
            "RETURNING id"
        ), {
            "it": INSIGHT_PROMPT_CANDIDATE,
            "m": json.dumps(artifact, ensure_ascii=False, default=str),
            "narr": (proposal.get("diagnosis") or f"{service} 프롬프트 개선후보")[:1000],
        })).fetchone()
        await db.commit()
        new_id = str(row[0]) if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning("프롬프트후보 저장 실패: %s", str(e)[:160])
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None

    try:
        from app.core.audit import audit_admin_action

        await audit_admin_action(
            actor_id=_ACTOR, actor_role="system",
            action="growth.improve.prompt_candidate", target=new_id or service,
            detail={"service": service, "label": label,
                    "confidence": artifact["confidence"], "requires_approval": True},
        )
    except Exception:  # noqa: BLE001
        pass
    return new_id


async def generate_prompt_candidates(
    db, *, target_services: list[str] | None = None,
    max_candidates: int = MAX_PROMPT_CANDIDATES_PER_RUN,
    now: datetime | None = None,
) -> dict[str, Any]:
    """down율 높은 service → 프롬프트 개선후보 생성 → A/B 후보군 등록(채택 아님).

    target_services 미지정 시 learning_loop.compute_down_rates 로 직접 식별한다.
    LLM 키 없으면 규칙기반 진단만 담아 후보 등록(graceful). 1배치 캡으로 비용가드.
    ★자동 채택/적용 절대 없음 — platform_settings 후보군 등록 + 아티팩트 저장만.

    반환: {"targets","registered","artifacts":[{service,label,insight_id}]}.
    best-effort.
    """
    now = now or datetime.now(timezone.utc)
    summary: dict[str, Any] = {"targets": [], "registered": 0, "artifacts": []}

    try:
        services = list(target_services or [])
        if not services:
            from app.services.growth import learning_loop
            rates = await learning_loop.compute_down_rates(db)
            services = [s for s, d in rates.items() if d.get("is_target")]
        summary["targets"] = services
    except Exception as e:  # noqa: BLE001
        logger.warning("프롬프트후보 대상 식별 실패: %s", str(e)[:160])
        return summary

    use_llm = _llm_enabled()
    for service in services:
        if summary["registered"] >= max_candidates:
            break
        if not service:
            continue
        try:
            samples = await _failure_samples(db, service)
            proposal: dict[str, Any] | None = None
            if use_llm and samples.get("corrections"):
                proposal = await _llm_prompt_candidate(service, samples)
            if not proposal:
                # graceful: LLM 미사용/표본부족 시 규칙기반 진단만(사람이 프롬프트 작성).
                proposal = {
                    "diagnosis": f"{service} 품질저하(down율 임계 초과) — 프롬프트 점검 필요",
                    "improved_prompt_addendum": "수동 작성 필요(LLM 비활성 또는 표본부족)",
                    "rationale": "데이터 기반 자동 개선안 미생성(graceful)",
                    "confidence": 0.2,
                }
            # 후보 레이블 채번 + 후보군 등록 + 아티팩트 저장.
            from app.services.growth import schema_guard
            cur = await schema_guard.get_setting(db, f"prompt_candidates.{service}")
            existing = (cur.get("candidates") if isinstance(cur, dict) else None) or []
            label = _new_candidate_label([str(v) for v in existing])
            reg = await _register_candidate(db, service, label, proposal)
            ins_id = await _store_prompt_candidate(db, service, label, proposal)
            if reg:
                summary["registered"] += 1
                summary["artifacts"].append(
                    {"service": service, "label": label, "insight_id": ins_id}
                )
        except Exception as e:  # noqa: BLE001
            logger.debug("프롬프트후보 생성 실패(%s): %s", service, str(e)[:120])

    if summary["registered"]:
        logger.info("growth L3: 프롬프트 개선후보 %d건 A/B 후보군 등록(채택 아님)",
                    summary["registered"])
    return summary


__all__ = [
    "generate_proposals",
    "generate_prompt_candidates",
    "is_path_allowed",
    "_new_candidate_label",
    "ALLOWED_PATH_PREFIXES", "DENY_PATH_PATTERNS",
    "INSIGHT_PROPOSAL", "MAX_PROPOSALS_PER_RUN",
    "INSIGHT_PROMPT_CANDIDATE", "MAX_PROMPT_CANDIDATES_PER_RUN",
    "PROMPT_CANDIDATE_PREFIX",
]
