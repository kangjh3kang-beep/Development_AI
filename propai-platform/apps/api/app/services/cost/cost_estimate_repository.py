"""원가계산서(BOQ) 영속화·조회 — cost_estimate / cost_estimate_item.

analysis_ledger_service 와 동일한 세션 획득(async_session_factory) + lazy _ensure 패턴.
실패해도 산정 결과 반환은 호출부에서 graceful 처리(여기선 예외를 흡수하고 ok=False).
"""

from __future__ import annotations

import json
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def save_estimate(
    *,
    project_id: str | None,
    tenant_id: str | None,
    header: dict[str, Any],
    items: list[dict[str, Any]],
    summary: dict[str, Any],
    badges: dict[str, Any],
    created_by: str | None = None,
) -> dict[str, Any]:
    """BOQ 헤더+항목을 영속화하고 estimate_id 를 반환한다."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        from app.services.cost.cost_tables_bootstrap import _ensure_cost_tables

        async with async_session_factory() as db:
            await _ensure_cost_tables(db)
            row = (await db.execute(text(
                "INSERT INTO cost_estimate"
                "(project_id, tenant_id, building_type, structure_type, total_gfa_sqm,"
                " direct_won, indirect_won, total_won, confidence_grade, qto_source, summary, badges, created_by)"
                " VALUES (:pid,:tid,:bt,:st,:gfa,:d,:i,:t,:cg,:qs,CAST(:sm AS jsonb),CAST(:bg AS jsonb),:cb)"
                " RETURNING id"), {
                "pid": project_id, "tid": tenant_id,
                "bt": header.get("building_type"), "st": header.get("structure_type"),
                "gfa": header.get("total_gfa_sqm"),
                "d": summary.get("direct", 0), "i": summary.get("indirect", 0), "t": summary.get("total", 0),
                "cg": summary.get("confidence_grade"), "qs": header.get("qto_source"),
                "sm": json.dumps(summary, ensure_ascii=False, default=str),
                "bg": json.dumps(badges, ensure_ascii=False, default=str),
                "cb": created_by,
            })).first()
            estimate_id = str(row[0])
            ins = text(
                "INSERT INTO cost_estimate_item"
                "(estimate_id, code, name, work_type, quantity, unit, unit_price, amount,"
                " price_source, price_basis_year, qto_source, market_unit_price, actual_unit_price, sort_order)"
                " VALUES (:eid,:code,:name,:wt,:qty,:unit,:up,:amt,:ps,:pby,:qs,:mup,:aup,:so)")
            for idx, it in enumerate(items):
                await db.execute(ins, {
                    "eid": estimate_id, "code": it.get("code"), "name": it.get("name"),
                    "wt": it.get("work_type"), "qty": it.get("quantity", 0), "unit": it.get("unit"),
                    "up": it.get("unit_price", 0), "amt": it.get("amount", 0),
                    "ps": it.get("price_source"), "pby": it.get("price_basis_year"),
                    "qs": it.get("qto_source"),
                    "mup": it.get("market_unit_price"), "aup": it.get("actual_unit_price"),
                    "so": idx,
                })
            await db.commit()
            return {"ok": True, "estimate_id": estimate_id}
    except Exception as e:  # noqa: BLE001
        logger.warning("BOQ 영속화 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}


async def get_estimate(estimate_id: str) -> dict[str, Any] | None:
    """estimate_id 로 BOQ 헤더+항목 조회."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        from app.services.cost.cost_tables_bootstrap import _ensure_cost_tables

        async with async_session_factory() as db:
            await _ensure_cost_tables(db)
            h = (await db.execute(text(
                "SELECT id, project_id, building_type, structure_type, total_gfa_sqm,"
                " direct_won, indirect_won, total_won, confidence_grade, qto_source, summary, badges, created_at"
                " FROM cost_estimate WHERE id = :eid"), {"eid": estimate_id})).first()
            if not h:
                return None
            items = (await db.execute(text(
                "SELECT code, name, work_type, quantity, unit, unit_price, amount,"
                " price_source, price_basis_year, qto_source, market_unit_price, actual_unit_price"
                " FROM cost_estimate_item WHERE estimate_id = :eid ORDER BY sort_order"),
                {"eid": estimate_id})).all()
            return {
                "estimate_id": str(h[0]), "project_id": h[1],
                "building_type": h[2], "structure_type": h[3], "total_gfa_sqm": float(h[4] or 0),
                "summary": h[10] or {}, "badges": h[11] or {},
                "qto_source": h[9], "created_at": str(h[12]),
                "items": [{
                    "code": r[0], "name": r[1], "work_type": r[2],
                    "quantity": float(r[3] or 0), "unit": r[4],
                    "unit_price": float(r[5] or 0), "amount": float(r[6] or 0),
                    "price_source": r[7], "price_basis_year": r[8], "qto_source": r[9],
                    "market_unit_price": float(r[10]) if r[10] is not None else None,
                    "actual_unit_price": float(r[11]) if r[11] is not None else None,
                } for r in items],
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("BOQ 조회 실패", err=str(e)[:160])
        return None


async def list_estimates(project_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """프로젝트의 BOQ 목록(최신순)."""
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory
        from app.services.cost.cost_tables_bootstrap import _ensure_cost_tables

        async with async_session_factory() as db:
            await _ensure_cost_tables(db)
            rows = (await db.execute(text(
                "SELECT id, building_type, structure_type, total_gfa_sqm, total_won, confidence_grade, created_at"
                " FROM cost_estimate WHERE project_id = :pid ORDER BY created_at DESC LIMIT :lim"),
                {"pid": project_id, "lim": limit})).all()
            return [{
                "estimate_id": str(r[0]), "building_type": r[1], "structure_type": r[2],
                "total_gfa_sqm": float(r[3] or 0), "total_won": float(r[4] or 0),
                "confidence_grade": r[5], "created_at": str(r[6]),
            } for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("BOQ 목록 실패", err=str(e)[:160])
        return []
