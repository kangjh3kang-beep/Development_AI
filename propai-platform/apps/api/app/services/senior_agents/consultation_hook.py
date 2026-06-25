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
from typing import Any

logger = logging.getLogger(__name__)

# 평가 종합 최악판정(나쁠수록 큼) — 다도메인 종합 verdict 산정용.
_VERDICT_RANK = {"unavailable": -1, None: 0, "PASS": 1, "WARN": 2, "BLOCK": 3}


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
    return {
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
    }


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
) -> dict[str, Any]:
    """다도메인 시니어 자문(예: 종합분석=urban+legal) → 표준 evidence 계약(절대 raise 안 함)."""
    try:
        from app.services.senior_agents.orchestrator import senior_orchestrator
    except Exception as e:  # noqa: BLE001 — 엔진 import 실패는 graceful 미가용
        logger.info("senior consultation 엔진 import 생략: %s", str(e)[:120])
        return _unavailable()

    ctx = {"inputs": inputs} if isinstance(inputs, dict) else {}
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
