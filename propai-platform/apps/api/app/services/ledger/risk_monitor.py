"""Phase 4 — 능동 위험감지(risk_monitor): 원장을 스캔해 위험 이벤트를 결정론으로 탐지.

Phase 2(contradiction/lineage)·P5(staleness)를 소비. 고심각 모순·판정 fail·staleness를 위험
이벤트로 표면화한다. 원장·수치 불변(read·표면화 전용), LLM 비개입.

실시간 이벤트: evaluate_chain_risk를 append 훅으로 호출하면 이벤트 구동(이 slice는 on-demand/scan
API; 이벤트 버스·push 채널은 후속 Phase 4.2).
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_LEVEL_ORDER = {"none": 0, "low": 1, "medium": 2, "high": 3}
_FAIL_VERDICTS = {"부적합", "fail", "위반", "escalate"}
_FAIL_STATUSES = {"fail", "부적합", "위반"}


def _is_fail_verdict(v: Any) -> bool:
    return isinstance(v, str) and v.strip().lower() in {x.lower() for x in _FAIL_VERDICTS}


def _has_fail_finding(latest: dict[str, Any]) -> bool:
    fb = (latest or {}).get("findings_brief")
    if isinstance(fb, list):
        for f in fb:
            if isinstance(f, dict) and str(f.get("status") or "").strip().lower() in _FAIL_STATUSES:
                return True
    return False


def classify_risks(*, latest: dict[str, Any] | None, contradictions: dict[str, Any] | None,
                   age_days: float | None, max_age_days: int = 90) -> list[dict[str, Any]]:
    """순수 결정론: latest payload + 모순 + age → 위험 이벤트 목록."""
    latest = latest or {}
    contradictions = contradictions or {}
    risks: list[dict[str, Any]] = []
    if contradictions.get("max_severity") == "high":
        n = (contradictions.get("counts") or {}).get("high", 0)
        risks.append({"type": "contradiction_high", "severity": "high",
                      "detail": f"직전 대비 고심각 모순 {n}건", "recommend": "재검토/재분석"})
    if _is_fail_verdict(latest.get("verdict")) or _has_fail_finding(latest):
        risks.append({"type": "status_fail", "severity": "high",
                      "detail": f"판정 위험: verdict={latest.get('verdict')}", "recommend": "검토 필요"})
    if age_days is not None and age_days > max_age_days:
        risks.append({"type": "stale", "severity": "medium",
                      "detail": f"{age_days:.0f}일 경과(>{max_age_days}일)", "recommend": "갱신 재분석"})
    return risks


def _risk_level(risks: list[dict[str, Any]]) -> str:
    level = "none"
    for r in risks:
        if _LEVEL_ORDER.get(r.get("severity"), 0) > _LEVEL_ORDER[level]:
            level = r["severity"]
    return level


async def evaluate_chain_risk(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None, max_age_days: int = 90,
) -> dict[str, Any]:
    """단일 체인 능동 위험평가 — get_latest + lineage 엣지(max_severity) + age → classify."""
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        from app.services.ledger import lineage
        from app.services.ledger.staleness import _age_days
        latest = await ledger.get_latest(analysis_type=analysis_type, tenant_id=tenant_id,
                                         pnu=pnu, address=address, project_id=project_id)
        if not latest:
            return {"analysis_type": analysis_type, "risks": [], "risk_level": "none", "reason": "no_data"}
        parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tenant_id)
        edge = parents[0] if parents else None
        ms = edge.get("max_severity") if edge else None
        contradictions = {"max_severity": ms,
                          "counts": {"high": int(edge.get("contradiction_count") or 0)} if ms == "high" else {}}
        age = await _age_days(analysis_type=analysis_type, tenant_id=tenant_id,
                              pnu=pnu, address=address, project_id=project_id)
        risks = classify_risks(latest=latest.get("payload") or {}, contradictions=contradictions,
                               age_days=age, max_age_days=max_age_days)
        return {"analysis_type": analysis_type, "version": latest.get("version"),
                "risks": risks, "risk_level": _risk_level(risks)}
    except Exception as e:  # noqa: BLE001
        logger.warning("risk 평가 실패(graceful)", analysis_type=analysis_type, err=str(e)[:160])
        return {"analysis_type": analysis_type, "risks": [], "risk_level": "none", "reason": "error"}


async def scan_project_risks(
    *, tenant_id: str | None = None, project_id: str | None = None, max_age_days: int = 90,
) -> dict[str, Any]:
    """프로젝트 전 체인 능동 스캔 — 위험 체인만 집계(능동 위험감지)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        from app.services.ledger.analysis_ledger_service import _ensure
        async with async_session_factory() as db:
            await _ensure(db)
            tsql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            psql = "project_id = :pid" if project_id else "project_id IS NULL"
            rows = (await db.execute(text(
                f"SELECT DISTINCT analysis_type, pnu, address_norm FROM analysis_ledger "
                f"WHERE {tsql} AND {psql}"), {"tid": tenant_id, "pid": project_id})).all()
        chains: list[dict[str, Any]] = []
        for atype, pnu, addr in rows:
            ev = await evaluate_chain_risk(analysis_type=atype, tenant_id=tenant_id,
                                           pnu=pnu, address=addr, project_id=project_id,
                                           max_age_days=max_age_days)
            if ev.get("risks"):
                chains.append(ev)
        level = "none"
        for c in chains:
            if _LEVEL_ORDER.get(c["risk_level"], 0) > _LEVEL_ORDER[level]:
                level = c["risk_level"]
        return {"project_id": project_id, "chains_at_risk": len(chains),
                "risk_level": level, "chains": chains}
    except Exception as e:  # noqa: BLE001
        logger.warning("risk 스캔 실패(graceful)", project_id=project_id, err=str(e)[:160])
        return {"project_id": project_id, "chains_at_risk": 0, "risk_level": "none", "reason": "error"}
