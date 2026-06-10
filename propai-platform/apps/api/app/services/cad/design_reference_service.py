"""표준설계 참조 라이브러리(P7) — 관리자가 올린 CAD/도면 사례를 저장·검색.

관리자가 도면 파일(DXF/PDF/이미지) + 메타(용도·용도지역·면적·세대·층·평형)를 업로드하면
라이브러리에 적재하고, 설계 생성 시 '유사 사례'를 메타 유사도(결정론)로 검색해 참고로 제공한다.
임베딩 기반 검색은 후속 확장 — 1차는 결정론 메타 스코어링(가짜 추천 없음).

파일은 Supabase Storage(public 버킷 propai-design-refs)에 저장하고 DB엔 메타+URL만 보관.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

_DDL = [
    """CREATE TABLE IF NOT EXISTS design_references (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        title text NOT NULL,
        building_use text,
        zone_code text,
        area_sqm numeric(14,2),
        total_units int,
        floors int,
        unit_types text[] DEFAULT '{}',
        file_url text,
        file_type text,
        source text,
        note text,
        uploaded_by uuid,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_design_ref_use ON design_references(building_use)",
]


async def ensure_schema(db: AsyncSession) -> None:
    for ddl in _DDL:
        await db.execute(text(ddl))
    await db.commit()


def _row(r: Any) -> dict[str, Any]:
    return {
        "id": str(r[0]), "title": r[1], "building_use": r[2], "zone_code": r[3],
        "area_sqm": float(r[4]) if r[4] is not None else None,
        "total_units": int(r[5]) if r[5] is not None else None,
        "floors": int(r[6]) if r[6] is not None else None,
        "unit_types": list(r[7] or []), "file_url": r[8], "file_type": r[9],
        "source": r[10], "note": r[11],
        "created_at": r[12].isoformat() if r[12] else None,
    }


_COLS = ("id, title, building_use, zone_code, area_sqm, total_units, floors, "
         "unit_types, file_url, file_type, source, note, created_at")


async def add_reference(db: AsyncSession, *, user_id: Any, title: str, building_use: str | None,
                        zone_code: str | None, area_sqm: float | None, total_units: int | None,
                        floors: int | None, unit_types: list[str], file_url: str | None,
                        file_type: str | None, source: str | None, note: str | None) -> dict[str, Any]:
    await ensure_schema(db)
    rid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO design_references(id, title, building_use, zone_code, area_sqm, "
             "total_units, floors, unit_types, file_url, file_type, source, note, uploaded_by) "
             "VALUES (:i,:t,:bu,:z,:a,:tu,:f,:ut,:url,:ft,:s,:n,:u)"),
        {"i": rid, "t": (title or "설계 사례").strip()[:120], "bu": building_use, "z": zone_code,
         "a": area_sqm, "tu": total_units, "f": floors, "ut": unit_types or [],
         "url": file_url, "ft": file_type, "s": source, "n": note, "u": str(user_id)},
    )
    await db.commit()
    return {"ok": True, "id": rid}


async def list_references(db: AsyncSession, building_use: str | None = None,
                          limit: int = 100) -> list[dict[str, Any]]:
    await ensure_schema(db)
    q = f"SELECT {_COLS} FROM design_references "
    p: dict[str, Any] = {"l": int(limit)}
    if building_use:
        q += "WHERE building_use=:bu "
        p["bu"] = building_use
    q += "ORDER BY created_at DESC LIMIT :l"
    rows = (await db.execute(text(q), p)).all()
    return [_row(r) for r in rows]


async def delete_reference(db: AsyncSession, ref_id: str) -> dict[str, Any]:
    await ensure_schema(db)
    await db.execute(text("DELETE FROM design_references WHERE id=:i"), {"i": ref_id})
    await db.commit()
    return {"ok": True}


def _similarity(ref: dict[str, Any], *, building_use: str | None, area_sqm: float | None,
                unit_types: list[str]) -> int:
    """결정론 메타 유사도(0~100). 용도40 + 면적근접30 + 평형겹침30."""
    score = 0.0
    if building_use and ref.get("building_use") == building_use:
        score += 40
    if area_sqm and ref.get("area_sqm"):
        ratio = min(area_sqm, ref["area_sqm"]) / max(area_sqm, ref["area_sqm"])
        score += 30 * ratio  # 면적 비율(가까울수록 1)
    if unit_types and ref.get("unit_types"):
        a, b = set(unit_types), set(ref["unit_types"])
        overlap = len(a & b) / len(a | b) if (a | b) else 0
        score += 30 * overlap
    return round(score)


async def find_similar(db: AsyncSession, *, building_use: str | None, area_sqm: float | None,
                       unit_types: list[str], k: int = 5) -> list[dict[str, Any]]:
    """유사 사례 Top-K(결정론 메타 스코어링)."""
    await ensure_schema(db)
    # 후보: 동일 용도 우선, 없으면 전체(최근 200)
    rows = (await db.execute(
        text(f"SELECT {_COLS} FROM design_references ORDER BY created_at DESC LIMIT 200")
    )).all()
    cands = [_row(r) for r in rows]
    scored = [{**c, "similarity": _similarity(c, building_use=building_use, area_sqm=area_sqm,
                                              unit_types=unit_types)} for c in cands]
    scored = [s for s in scored if s["similarity"] > 0]
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]
