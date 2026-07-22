"""시니어 자문 공용 훅(모세혈관 배선 표준계약).

메인 분석 플로우(종합분석·수지·인허가·시장·규제)가 시니어 전문가 자문을 결과에
첨부할 때 쓰는 단일 진입점. SeniorOrchestrator.consult를 호출해 결과를 표준 evidence
계약(verdict·evaluations·citations·needs_expert_review·honest_notes)으로 정규화한다.

★무회귀 핵심: 절대 raise 하지 않는다. 엔진 미가용/예외/미등록 도메인은 모두
graceful unavailable 블록을 반환해, 시니어 자문 실패가 메인 분석을 깨뜨리지 못하게 한다.
무목업: 미가용은 정직 표기(verdict='unavailable')하고 전문가 검토 필요로 강등한다.

사용:
    from app.services.senior_agents.consultation_hook import attach_senior_consultation
    result["senior_consultation"] = attach_senior_consultation("urban", inputs)
    # 또는 다도메인:
    result["senior_consultation"] = attach_senior_consultation_multi(["urban", "legal"], inputs)
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

# 평가 종합 최악판정(나쁠수록 큼) — 다도메인 종합 verdict 산정용.
_VERDICT_RANK = {"unavailable": -1, None: 0, "PASS": 1, "WARN": 2, "BLOCK": 3}


def _finite(v: Any) -> float | None:
    """유한 수치만 추출(bool·NaN/inf·비수치 → None). 입력 정규화 공용."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def build_compliance_inputs(
    *,
    far_actual: Any = None,
    far_limit: Any = None,
    bcr_actual: Any = None,
    bcr_limit: Any = None,
    height_actual: Any = None,
    height_limit: Any = None,
    road_width_actual: Any = None,
    road_width_required: Any = None,
) -> dict[str, float]:
    """건폐/용적/높이/접도 적합성(심의 CSP) 평가 입력 빌더(공용·DRY).

    심의위원 evaluator(delib.multi_clause_csp)는 actual/limit(또는 required) 쌍을 받아
    actual≤limit(건폐/용적/높이) 또는 actual≥required(접도)로 PASS/BLOCK을 산출한다.
    한도(limit/required)가 0·음수·결측이면 해당 조항은 자동 생략(거짓 위반 방지·무목업).

    ★일상 부지 자급평가 패턴: 분석이 가정한 실효값(actual)과 한도(limit)가 같으면 PASS(준수),
    제안값이 한도를 초과하면 BLOCK(위반). actual 미지정 시 limit을 actual로 간주(준수 자급평가).
    유한 수치만 채택(NaN/inf/None/비수치는 키 생략 — evaluator가 결측으로 안전 생략).
    """
    out: dict[str, float] = {}
    for a_key, a_val, l_key, l_val, actual_defaults_to_limit in (
        ("far_actual", far_actual, "far_limit", far_limit, True),
        ("bcr_actual", bcr_actual, "bcr_limit", bcr_limit, True),
        ("height_actual", height_actual, "height_limit", height_limit, True),
        ("road_width_actual", road_width_actual, "road_width_required", road_width_required, False),
    ):
        lim = _finite(l_val)
        if lim is None or lim <= 0:
            continue  # 한도 미확보 → 조항 생략(evaluator와 동일 정책)
        act = _finite(a_val)
        if act is None and actual_defaults_to_limit:
            act = lim  # 제안값 미상 → 한도 준수로 자급평가(actual=limit → PASS)
        if act is None:
            continue
        out[a_key] = act
        out[l_key] = lim
    return out


def _unavailable(note: str = "시니어 자문 미가용") -> dict[str, Any]:
    """엔진 미가용/예외 시 graceful 블록(정직 표기·전문가 검토 필요)."""
    return {
        "verdict": "unavailable",
        "evaluations": [],
        "citations": [],
        "needs_expert_review": True,
        "honest_notes": note,
        "consultations": [],
    }


def _normalize_one(consultation: Any) -> dict[str, Any]:
    """SeniorConsultation → 표준 계약 1건 dict(verdict·evaluations·citations·notes 포함)."""
    d = consultation.to_dict()
    out = {
        "agent_key": d.get("agent_key"),
        "name_ko": d.get("name_ko"),
        "maturity": d.get("maturity"),
        "verdict": d.get("overall_verdict"),       # PASS/WARN/BLOCK(정량입력 시)·없으면 None
        "decision_framework": d.get("decision_framework", []),
        "evaluations": d.get("evaluations", []),
        "citations": d.get("citations", []),
        "confidence": d.get("confidence"),
        "confidence_label": d.get("confidence_label"),
        "needs_expert_review": bool(d.get("needs_expert_review")),
        "high_risk": bool(d.get("high_risk")),
        "license_gate": d.get("license_gate"),
        "honest_notes": d.get("honest_notes", []),
        # 풍성화(additive): 시니어가 경계하는 실패모드·점검 체크리스트 — 프론트 카드가 렌더.
        "risk_warnings": d.get("risk_warnings", []),
        "checklist": d.get("checklist", []),
    }
    # IRAC 추론 체인(include_reasoning 시에만 존재) — 쟁점→규칙(법령 근거)→적용→결론.
    # prompt(FinCoT 원문)는 감사·재현용 내부 필드라 API 응답에서 제외(페이로드·노출 최소화).
    reasoning = d.get("reasoning")
    if isinstance(reasoning, dict) and reasoning.get("irac_steps"):
        out["reasoning"] = {
            "mode": reasoning.get("mode"),
            "irac_steps": reasoning.get("irac_steps", []),
        }
    return out


def _aggregate(consults: list[dict[str, Any]]) -> dict[str, Any]:
    """다건 자문을 표준 evidence 계약으로 종합(최악 verdict·근거 합집합·전문가검토 OR)."""
    if not consults:
        return _unavailable("적용 가능한 시니어 도메인 없음")
    overall: str | None = None
    citations: list[str] = []
    notes: list[str] = []
    needs_review = False
    for c in consults:
        v = c.get("verdict")
        if _VERDICT_RANK.get(v, 0) > _VERDICT_RANK.get(overall, 0):
            overall = v
        for cit in c.get("citations", []):
            if cit and cit not in citations:
                citations.append(cit)
        for n in c.get("honest_notes", []):
            if n and n not in notes:
                notes.append(n)
        needs_review = needs_review or bool(c.get("needs_expert_review"))
    return {
        "verdict": overall,
        "evaluations": [e for c in consults for e in c.get("evaluations", [])],
        "citations": citations,
        "needs_expert_review": needs_review,
        "honest_notes": " · ".join(notes) if notes else "",
        "consultations": consults,
    }


def attach_senior_consultation(
    domain: str,
    inputs: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """단일 도메인 시니어 자문 → 표준 evidence 계약 dict(절대 raise 안 함).

    Args:
        domain: 도메인(한/영) 또는 에이전트 키(예: 'urban'·'금융'·'senior_legal_scrivener').
        inputs: 정량 평가 입력(없으면 프레임워크·근거만). evaluator가 PASS/WARN/BLOCK 산출.
        result: (선택) 향후 result 기반 입력 보강용 자리표시 — 현재 미사용(시그니처 호환).

    Returns:
        {verdict, evaluations, citations, needs_expert_review, honest_notes, consultations}.
        미가용/예외 시 verdict='unavailable'·needs_expert_review=True(정직·무목업).
    """
    return attach_senior_consultation_multi([domain], inputs, result)


def attach_senior_consultation_multi(
    domains: list[str],
    inputs: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    *,
    include_reasoning: bool = False,
    context_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """다도메인 시니어 자문(예: 종합분석=urban+legal) → 표준 evidence 계약(절대 raise 안 함).

    include_reasoning=True면 각 자문에 IRAC 추론 체인(쟁점→규칙[법령 근거]→적용→결론)을
    동봉한다(결정론·무LLM — 지연/비용 0). context_signals로 confidence 신호
    (data_completeness/rag_strength 등 [0,1])를 주입할 수 있다(미지정=기존 중립).
    """
    try:
        from app.services.senior_agents.orchestrator import senior_orchestrator
    except Exception as e:  # noqa: BLE001 — 엔진 import 실패는 graceful 미가용
        logger.info("senior consultation 엔진 import 생략: %s", str(e)[:120])
        return _unavailable()

    ctx: dict[str, Any] = {"inputs": inputs} if isinstance(inputs, dict) else {}
    if isinstance(context_signals, dict):
        # inputs 키는 위 계약이 소유 — 신호가 덮어쓰지 못하게 방어.
        ctx.update({k: v for k, v in context_signals.items() if k != "inputs"})
    if include_reasoning:
        ctx["include_reasoning"] = True
    consults: list[dict[str, Any]] = []
    seen: set[str] = set()
    for domain in domains:
        try:
            key = senior_orchestrator.route(domain)
            if key is None or key in seen:
                continue  # 미해당 도메인·중복 에이전트 무시(무목업)
            seen.add(key)
            c = senior_orchestrator.consult(key, context=ctx)
            consults.append(_normalize_one(c))
        except Exception as e:  # noqa: BLE001 — 도메인 1건 실패가 전체를 깨면 안 됨
            logger.info("senior consultation(%s) 생략: %s", domain, str(e)[:120])
            continue
    if not consults:
        return _unavailable()
    return _aggregate(consults)
