"""동호 3소스 생성 — OUTLINE(건축개요)/DRAWING_UPLOAD(도면)/DESIGN_AI(설계산출물).

OUTLINE 은 완전 동작. DRAWING_UPLOAD/DESIGN_AI 는 파서 인터페이스를 제공하되
실제 파싱(ezdxf/PyMuPDF/ifcopenshell, 설계 산출물 조인)은 후속 보강(현재 빈 그리드 반환).
계약/홀드 호는 재생성 시 보호(덮어쓰지 않음).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.sales.units_pricing import (
    SalesUnitBlock, SalesUnitGeneration, SalesUnitInventory, SalesUnitType,
)
from app.services.sales.harness.outbox import emit_outbox


def _pick_type(b: dict, u: int) -> str:
    types = b.get("types") or [{"name": "TYPE_A"}]
    return types[(u - 1) % len(types)]["name"]


def expand_outline(params: dict) -> list[dict]:
    rows: list[dict] = []
    for b in (params or {}).get("blocks", []):
        for f in range(1, int(b["floors"]) + 1):
            for u in range(1, int(b["units_per_floor"]) + 1):
                rows.append({
                    "dong": b["name"], "ho": f"{f * 100 + u}", "floor": f, "line": f"{u:02d}",
                    "aspect": b.get("aspect"), "type_name": _pick_type(b, u),
                })
    return rows


def parse_drawing(source_ref: str) -> list[dict]:
    """도면 파싱(후속 보강). 현재는 빈 그리드 — 미지원 확장자는 ValueError."""
    ext = (source_ref or "").rsplit(".", 1)[-1].lower()
    if ext in ("dxf", "pdf", "ifc", "ifczip"):
        return []  # TODO(Part 후속): ezdxf/PyMuPDF/ifcopenshell 실파싱
    raise ValueError(f"unsupported drawing: {ext}")


async def map_from_design(db: AsyncSession, source_ref: str) -> list[dict]:
    """설계 AI 산출물(layout/floor_plan/3d/quantity)에서 세대 메타 매핑(후속 보강)."""
    return []


async def generate_units(db: AsyncSession, site_id: uuid.UUID, gen: SalesUnitGeneration) -> int:
    st = gen.source_type
    if st == "OUTLINE":
        grid = expand_outline(gen.params or {})
    elif st == "DRAWING_UPLOAD":
        grid = parse_drawing(gen.source_ref)
    else:
        grid = await map_from_design(db, gen.source_ref)

    # 타입 upsert
    type_ids: dict[str, uuid.UUID] = {}
    for tname in {g["type_name"] for g in grid if g.get("type_name")}:
        t = (await db.execute(select(SalesUnitType).where(
            SalesUnitType.site_id == site_id, SalesUnitType.type_name == tname))).scalar_one_or_none()
        if not t:
            t = SalesUnitType(site_id=site_id, type_name=tname)
            db.add(t)
            await db.flush()
        type_ids[tname] = t.id

    # 블록 upsert
    block_ids: dict[str, uuid.UUID] = {}
    for dong in {g["dong"] for g in grid}:
        b = (await db.execute(select(SalesUnitBlock).where(
            SalesUnitBlock.site_id == site_id, SalesUnitBlock.block_name == dong))).scalar_one_or_none()
        if not b:
            b = SalesUnitBlock(site_id=site_id, block_name=dong)
            db.add(b)
            await db.flush()
        block_ids[dong] = b.id

    created = 0
    for g in grid:
        exists = (await db.execute(select(SalesUnitInventory).where(
            SalesUnitInventory.site_id == site_id, SalesUnitInventory.dong == g["dong"],
            SalesUnitInventory.ho == g["ho"], SalesUnitInventory.deleted_at.is_(None)))).scalar_one_or_none()
        if exists:  # 계약/홀드 호 보호: 재생성 시 덮어쓰지 않음
            continue
        db.add(SalesUnitInventory(
            site_id=site_id, block_id=block_ids[g["dong"]], type_id=type_ids.get(g.get("type_name")),
            dong=g["dong"], ho=g["ho"], floor=g.get("floor"), line=g.get("line"),
            aspect=g.get("aspect"), status="AVAILABLE",
        ))
        created += 1

    gen.status = "DONE"
    gen.generated_count = created
    await emit_outbox(db, site_id, "UnitInventoryGenerated", {"count": created})
    await db.flush()
    return created
