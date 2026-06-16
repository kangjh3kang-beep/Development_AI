"""P5 — 원장 read 기반 staleness/재분석 제안(분석루프 폐쇄).

get_latest/get_history를 소비해 (a)시간경과(staleness) (b)변경감지(contradiction)로
'재분석 권장'을 결정론으로 산출한다. 원장·산출 수치 불변(read·표면화 전용).
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_MAX_AGE_DAYS = 90


def _recommend(*, age_days: float | None, max_age_days: int, changed: bool) -> dict[str, Any]:
    """순수 임계 로직 — stale(시간) 또는 changed(내용)면 재분석 권장. (무 DB·결정론)"""
    stale = age_days is not None and age_days > max_age_days
    reasons: list[str] = []
    if stale:
        reasons.append("stale")
    if changed:
        reasons.append("changed")
    return {"stale": stale, "changed": changed,
            "recommend_reanalysis": bool(stale or changed), "reasons": reasons}


async def _age_days(
    *, analysis_type: str, tenant_id: str | None, pnu: str | None,
    address: str | None, project_id: str | None,
) -> float | None:
    """최신 버전의 now()-created_at(일)을 DB에서 직접 산출(파싱·tz 이슈 회피)."""
    from sqlalchemy import text

    from app.core.database import async_session_factory
    from app.services.ledger.analysis_ledger_service import _chain_where, _ensure, _norm_addr
    async with async_session_factory() as db:
        await _ensure(db)
        key_sql, params = _chain_where(pnu, _norm_addr(address), project_id)
        params.update({"tid": tenant_id, "atype": analysis_type})
        tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
        row = (await db.execute(text(
            f"SELECT EXTRACT(EPOCH FROM (now() - created_at)) / 86400.0 "
            f"FROM analysis_ledger WHERE {tenant_sql} AND {key_sql} AND analysis_type = :atype "
            f"ORDER BY version DESC LIMIT 1"), params)).first()
        return float(row[0]) if row and row[0] is not None else None


async def check_staleness(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None,
    current: dict[str, Any] | None = None, max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """동일 체인 최신 분석의 age + (current 제공 시) 변경 → 재분석 제안.

    - prior 없음: recommend_reanalysis=False, reason='no_prior'(정직).
    - age_days: DB에서 now()-created_at(일).
    - changed: detect_contradictions(prior, current).has_contradiction.
    """
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        prior = await ledger.get_latest(analysis_type=analysis_type, tenant_id=tenant_id,
                                        pnu=pnu, address=address, project_id=project_id)
        if not prior:
            return {"analysis_type": analysis_type, "prior_version": None, "age_days": None,
                    "recommend_reanalysis": False, "reason": "no_prior",
                    "stale": False, "changed": False, "reasons": []}
        age_days = await _age_days(analysis_type=analysis_type, tenant_id=tenant_id,
                                   pnu=pnu, address=address, project_id=project_id)
        changed = False
        max_sev = None
        if current is not None:
            from app.services.ledger.contradiction import detect_contradictions
            contra = detect_contradictions(prior, current)
            changed = bool(contra.get("has_contradiction"))
            max_sev = contra.get("max_severity")
        rec = _recommend(age_days=age_days, max_age_days=max_age_days, changed=changed)
        return {"analysis_type": analysis_type, "prior_version": prior.get("version"),
                "age_days": age_days, "max_severity": max_sev, "reason": "ok", **rec}
    except Exception as e:  # noqa: BLE001
        logger.warning("staleness 점검 실패(graceful)", analysis_type=analysis_type, err=str(e)[:160])
        return {"analysis_type": analysis_type, "recommend_reanalysis": False,
                "reason": "error", "message": str(e)[:160],
                "stale": False, "changed": False, "reasons": []}


async def staleness_report(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """get_history 소비 — 버전 타임라인 요약(재분석 추세 판단용)."""
    from app.services.ledger import analysis_ledger_service as ledger
    hist = await ledger.get_history(analysis_type=analysis_type, tenant_id=tenant_id,
                                    pnu=pnu, address=address, project_id=project_id, limit=limit)
    return {"analysis_type": analysis_type, "versions": len(hist),
            "latest_version": hist[0]["version"] if hist else 0, "history": hist}
