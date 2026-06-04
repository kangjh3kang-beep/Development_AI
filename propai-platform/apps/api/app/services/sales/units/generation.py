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
        floors_spec = b.get("floors_spec")
        if floors_spec:
            # 상가 등 층별 가변 호수: [{floor, units, type_name?}]
            for fs in floors_spec:
                f = int(fs["floor"])
                units = int(fs.get("units") or 0)
                tname = fs.get("type_name") or b.get("type_name")
                for u in range(1, units + 1):
                    rows.append({
                        "dong": b["name"], "ho": f"{f * 100 + u}", "floor": f, "line": f"{u:02d}",
                        "aspect": b.get("aspect"), "type_name": tname or _pick_type(b, u),
                    })
        else:
            # 균일 그리드(아파트/오피스텔/지산): floors × units_per_floor
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


async def map_from_design(db: AsyncSession, site_id: uuid.UUID, source_ref: str | None) -> list[dict]:
    """설계 AI 산출물(AutoDesignEngine compute_unit_layout) → 동·호표 그리드.

    현장의 project_id로 최신 DesignVersion(design_data_json)을 읽어 num_floors·세대평형배분
    (units[{type,count_per_floor}])·동수로 그리드를 구성. 구조 미흡 시 floor_count+면적 폴백.
    """
    from sqlalchemy import text

    from apps.api.database.models.sales.site_org import SalesSite

    site = (await db.execute(select(SalesSite).where(SalesSite.id == site_id))).scalar_one_or_none()
    project_id = source_ref or (str(site.project_id) if site and site.project_id else None)
    if not project_id:
        return []
    row = (await db.execute(text(
        "SELECT floor_count, total_floor_area_sqm, design_data_json FROM design_versions "
        "WHERE project_id = :pid ORDER BY version_number DESC LIMIT 1"),
        {"pid": project_id})).first()
    if not row:
        return []
    floor_count, total_area, dj = int(row[0] or 0), float(row[1] or 0), (row[2] or {})
    mass = dj.get("mass") or {}
    num_floors = int(mass.get("num_floors") or floor_count or 0)
    building_count = int(dj.get("building_count") or mass.get("building_count") or 1)
    # 세대 평형 배분: design_data_json.unit_layout/units 또는 mass 하위
    layout = dj.get("unit_layout") or dj.get("units") or (dj.get("unit_layout") if isinstance(dj.get("unit_layout"), list) else None)
    units_spec = layout if isinstance(layout, list) else (layout.get("units") if isinstance(layout, dict) else None)

    # 층당 (type,count) 시퀀스 구성
    seq: list[str] = []
    if units_spec:
        for u in units_spec:
            t = u.get("type") or u.get("type_name") or "TYPE_A"
            cpf = int(u.get("count_per_floor") or u.get("count") or 1)
            seq.extend([t] * max(1, cpf))
    if not seq:
        # 폴백: 기준층 순면적/84㎡ 추정
        per_floor = max(1, int((total_area / max(1, num_floors) / 84))) if (total_area and num_floors) else 4
        seq = ["84A"] * per_floor
    if not num_floors:
        return []

    rows: list[dict] = []
    for b in range(building_count):
        dong = str(101 + b)
        for f in range(1, num_floors + 1):
            for i, t in enumerate(seq, start=1):
                rows.append({"dong": dong, "ho": f"{f * 100 + i}", "floor": f,
                             "line": f"{i:02d}", "aspect": None, "type_name": t})
    return rows


async def generate_units(db: AsyncSession, site_id: uuid.UUID, gen: SalesUnitGeneration) -> int:
    st = gen.source_type
    if st == "OUTLINE":
        grid = expand_outline(gen.params or {})
    elif st == "DRAWING_UPLOAD":
        grid = parse_drawing(gen.source_ref)
    else:
        grid = await map_from_design(db, site_id, gen.source_ref)

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
