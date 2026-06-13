"""표준설계 참조 라이브러리(P7) — 관리자가 올린 CAD/도면 사례를 저장·검색.

관리자가 도면 파일(DXF/PDF/이미지) + 메타(용도·용도지역·면적·세대·층·평형)를 업로드하면
라이브러리에 적재하고, 설계 생성 시 '유사 사례'를 메타 유사도(결정론)로 검색해 참고로 제공한다.
임베딩 기반 검색은 후속 확장 — 1차는 결정론 메타 스코어링(가짜 추천 없음).

파일은 Supabase Storage(public 버킷 propai-design-refs)에 저장하고 DB엔 메타+URL만 보관.

U3 확장(템플릿 조립): 표준 기하(geometry_json)·스펙·요약·썸네일 컬럼을 런타임 DDL로
추가(additive·멱등). 법규 인지 유사도 similarity_v2(분해 근거 포함)와 상세 조회
get_reference/기하 부착 set_geometry를 제공한다 — 기존 _similarity/호출부는 불변.
"""

from __future__ import annotations

import json
import math
import uuid
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .design_reference_geometry import GeometryError, mass_dims, normalize_geometry
from .design_spec import legal_limits_for

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
    # U3: 템플릿 조립 — 기하·스펙·요약 컬럼(이 테이블 관행 = 런타임 DDL, additive·멱등)
    "ALTER TABLE design_references ADD COLUMN IF NOT EXISTS geometry_json jsonb",
    "ALTER TABLE design_references ADD COLUMN IF NOT EXISTS design_spec_json jsonb",
    "ALTER TABLE design_references ADD COLUMN IF NOT EXISTS summary_json jsonb",
    "ALTER TABLE design_references ADD COLUMN IF NOT EXISTS geometry_source text",
    "ALTER TABLE design_references ADD COLUMN IF NOT EXISTS design_version_id uuid",
    "ALTER TABLE design_references ADD COLUMN IF NOT EXISTS thumbnail_svg text",
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
        # U3 additive — 목록엔 무거운 geometry_json 대신 보유 여부·썸네일만 노출
        "geometry_source": r[13], "thumbnail_svg": r[14], "has_geometry": bool(r[15]),
    }


_COLS = ("id, title, building_use, zone_code, area_sqm, total_units, floors, "
         "unit_types, file_url, file_type, source, note, created_at, "
         "geometry_source, thumbnail_svg, (geometry_json IS NOT NULL) AS has_geometry")

# 상세 조회 전용 — 목록(_COLS)엔 싣지 않는 무거운 컬럼 포함
_FULL_COLS = _COLS + ", geometry_json, design_spec_json, summary_json, design_version_id"


def _dump_json(v: dict[str, Any] | list[Any] | None) -> str | None:
    """jsonb 파라미터 직렬화(None 보존 — CAST(NULL AS jsonb) 허용)."""
    return json.dumps(v, ensure_ascii=False) if v is not None else None


def _load_json(v: Any) -> Any:
    """jsonb 컬럼 역직렬화 — 드라이버가 str로 줄 수도, dict로 줄 수도 있다."""
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        logger.warning("design_reference_jsonb_parse_failed")
        return None


async def add_reference(db: AsyncSession, *, user_id: Any, title: str, building_use: str | None,
                        zone_code: str | None, area_sqm: float | None, total_units: int | None,
                        floors: int | None, unit_types: list[str], file_url: str | None,
                        file_type: str | None, source: str | None, note: str | None,
                        geometry_json: dict[str, Any] | None = None,
                        design_spec_json: dict[str, Any] | None = None,
                        summary_json: dict[str, Any] | None = None,
                        geometry_source: str | None = None,
                        design_version_id: str | None = None,
                        thumbnail_svg: str | None = None) -> dict[str, Any]:
    await ensure_schema(db)
    rid = str(uuid.uuid4())
    await db.execute(
        text("INSERT INTO design_references(id, title, building_use, zone_code, area_sqm, "
             "total_units, floors, unit_types, file_url, file_type, source, note, uploaded_by, "
             "geometry_json, design_spec_json, summary_json, geometry_source, "
             "design_version_id, thumbnail_svg) "
             "VALUES (:i,:t,:bu,:z,:a,:tu,:f,:ut,:url,:ft,:s,:n,:u,"
             "CAST(:gj AS jsonb),CAST(:dsj AS jsonb),CAST(:smj AS jsonb),:gs,"
             "CAST(:dvi AS uuid),:th)"),
        {"i": rid, "t": (title or "설계 사례").strip()[:120], "bu": building_use, "z": zone_code,
         "a": area_sqm, "tu": total_units, "f": floors, "ut": unit_types or [],
         "url": file_url, "ft": file_type, "s": source, "n": note, "u": str(user_id),
         "gj": _dump_json(geometry_json), "dsj": _dump_json(design_spec_json),
         "smj": _dump_json(summary_json), "gs": geometry_source,
         "dvi": design_version_id, "th": thumbnail_svg},
    )
    await db.commit()
    return {"ok": True, "id": rid}


async def set_geometry(db: AsyncSession, ref_id: str, *,
                       geometry_json: dict[str, Any],
                       design_spec_json: dict[str, Any] | None = None,
                       summary_json: dict[str, Any] | None = None,
                       geometry_source: str | None = None,
                       design_version_id: str | None = None,
                       thumbnail_svg: str | None = None) -> dict[str, Any]:
    """기존 사례에 표준 기하를 부착한다(None 인자는 기존값 보존 — COALESCE)."""
    await ensure_schema(db)
    await db.execute(
        text("UPDATE design_references SET "
             "geometry_json=CAST(:gj AS jsonb), "
             "design_spec_json=COALESCE(CAST(:dsj AS jsonb), design_spec_json), "
             "summary_json=COALESCE(CAST(:smj AS jsonb), summary_json), "
             "geometry_source=COALESCE(:gs, geometry_source), "
             "design_version_id=COALESCE(CAST(:dvi AS uuid), design_version_id), "
             "thumbnail_svg=COALESCE(:th, thumbnail_svg) "
             "WHERE id=:i"),
        {"i": ref_id, "gj": _dump_json(geometry_json), "dsj": _dump_json(design_spec_json),
         "smj": _dump_json(summary_json), "gs": geometry_source,
         "dvi": design_version_id, "th": thumbnail_svg},
    )
    await db.commit()
    return {"ok": True, "id": ref_id}


async def get_reference(db: AsyncSession, ref_id: str) -> dict[str, Any] | None:
    """사례 1건 상세(geometry_json 등 무거운 컬럼 포함). 없으면 None."""
    await ensure_schema(db)
    row = (await db.execute(
        text(f"SELECT {_FULL_COLS} FROM design_references WHERE id=:i"), {"i": ref_id}
    )).first()
    if row is None:
        return None
    out = _row(row)
    out["geometry_json"] = _load_json(row[16])
    out["design_spec_json"] = _load_json(row[17])
    out["summary_json"] = _load_json(row[18])
    out["design_version_id"] = str(row[19]) if row[19] else None
    return out


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


# ── U3 R3: similarity_v2 — 법규 인지 유사도(분해 근거 포함, 결정론) ──

# 용도지역 코드 지역군(국토계획법 대분류 단순화 — 정확 일치 10 / 동일군 5)
_ZONE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"1R", "2R", "3R", "QR"}),  # 주거계
    frozenset({"GC", "NC"}),              # 상업계
    frozenset({"QI"}),                    # 공업계
)

_AREA_BAND = (0.7, 1.3)        # 면적 대지비 허용 밴드(밖 0점)
_ASSUMED_FLOOR_HEIGHT_M = 3.0  # ref 층수→높이 환산 가정 층고(근거에 정직 표기)


def _zone_group(code: str | None) -> frozenset[str] | None:
    if not code:
        return None
    return next((g for g in _ZONE_GROUPS if code in g), None)


def similarity_v2(ref: dict[str, Any], *, building_use: str | None, zone_code: str | None,
                  area_sqm: float | None, unit_types: list[str],
                  setback_m: float | None = None) -> tuple[float, list[dict[str, Any]]]:
    """법규 인지 유사도 v2(0~100) + 분해 근거.

    배점: 용도25 + 면적20(대지비 0.7~1.3 밖 0) + 평형자카드15 + 지역군10
          + 법규적합20(legal_limits_for SSOT 대비 ref BCR/FAR/층수) + footprint수용10.
    불변식: score == round(sum(b["score"] for b in breakdown), 1),
            sum(b["max"]) == 100. 데이터 없는 요인은 0점 + 사유 정직 표기(가짜 가점 금지).
    """
    breakdown: list[dict[str, Any]] = []
    summary = ref.get("summary_json") or {}
    limits = legal_limits_for(zone_code) if zone_code else None

    # 1) 용도 일치(25)
    if building_use and ref.get("building_use") == building_use:
        breakdown.append({"factor": "용도", "score": 25.0, "max": 25,
                          "basis": f"건축물 용도 일치({building_use})"})
    else:
        breakdown.append({"factor": "용도", "score": 0.0, "max": 25,
                          "basis": f"용도 불일치 또는 미제공(대상 {building_use or '-'} / "
                                   f"사례 {ref.get('building_use') or '-'})"})

    # 2) 면적 근접(20) — 대지비 0.7~1.3 밴드 안에서만 비례 점수, 밖이면 0
    ref_area = ref.get("area_sqm")
    if area_sqm and ref_area:
        ratio = ref_area / area_sqm
        if _AREA_BAND[0] <= ratio <= _AREA_BAND[1]:
            s = round(20.0 * (1.0 - abs(ratio - 1.0) / (_AREA_BAND[1] - 1.0)), 1)
            breakdown.append({"factor": "면적", "score": s, "max": 20,
                              "basis": f"대지면적비 {ratio:.2f}(허용 {_AREA_BAND[0]}~{_AREA_BAND[1]})"})
        else:
            breakdown.append({"factor": "면적", "score": 0.0, "max": 20,
                              "basis": f"대지면적비 {ratio:.2f} — 허용 밴드 "
                                       f"{_AREA_BAND[0]}~{_AREA_BAND[1]} 밖"})
    else:
        breakdown.append({"factor": "면적", "score": 0.0, "max": 20,
                          "basis": "대지면적 정보 없음"})

    # 3) 평형 자카드(15)
    if unit_types and ref.get("unit_types"):
        a, b = set(unit_types), set(ref["unit_types"])
        jac = len(a & b) / len(a | b) if (a | b) else 0.0
        breakdown.append({"factor": "평형", "score": round(15.0 * jac, 1), "max": 15,
                          "basis": f"평형 자카드 {jac:.2f}(교집합 {sorted(a & b)})"})
    else:
        breakdown.append({"factor": "평형", "score": 0.0, "max": 15,
                          "basis": "평형 정보 없음"})

    # 4) 지역군(10) — 정확 일치 10 / 동일 대분류군 5 / 그 외 0
    ref_zone = ref.get("zone_code")
    if zone_code and ref_zone == zone_code:
        breakdown.append({"factor": "지역군", "score": 10.0, "max": 10,
                          "basis": f"용도지역 일치({zone_code})"})
    elif zone_code and ref_zone and _zone_group(zone_code) is not None \
            and _zone_group(zone_code) == _zone_group(ref_zone):
        breakdown.append({"factor": "지역군", "score": 5.0, "max": 10,
                          "basis": f"동일 지역군({zone_code}↔{ref_zone})"})
    else:
        breakdown.append({"factor": "지역군", "score": 0.0, "max": 10,
                          "basis": f"지역군 불일치 또는 미제공(대상 {zone_code or '-'} / "
                                   f"사례 {ref_zone or '-'})"})

    # 5) 법규적합(20) — 대상 용도지역 SSOT 한도 대비 사례 BCR/FAR/층수 적합 비율
    checks: list[tuple[str, bool]] = []
    if limits is not None:
        bcr = summary.get("bcr_percent")
        far = summary.get("far_percent")
        floors = ref.get("floors")
        if bcr is not None:
            checks.append((f"BCR {bcr:.1f}%≤{limits.building_coverage_ratio * 100:.0f}%",
                           float(bcr) <= limits.building_coverage_ratio * 100 + 0.5))
        if far is not None:
            checks.append((f"FAR {far:.1f}%≤{limits.floor_area_ratio * 100:.0f}%",
                           float(far) <= limits.floor_area_ratio * 100 + 0.5))
        if floors:
            if limits.max_height_m > 0:
                h = floors * _ASSUMED_FLOOR_HEIGHT_M
                checks.append((f"층수 {floors}층×{_ASSUMED_FLOOR_HEIGHT_M}m={h:.0f}m"
                               f"≤{limits.max_height_m:.0f}m(가정층고)",
                               h <= limits.max_height_m + 0.05))
            else:
                checks.append((f"층수 {floors}층 — 높이 무제한 지역", True))
    if checks:
        passed = sum(1 for _, ok in checks if ok)
        s = round(20.0 * passed / len(checks), 1)
        breakdown.append({"factor": "법규적합", "score": s, "max": 20,
                          "basis": "; ".join(f"{'OK' if ok else 'NG'} {label}"
                                             for label, ok in checks)})
    else:
        breakdown.append({"factor": "법규적합", "score": 0.0, "max": 20,
                          "basis": "용도지역 미제공 또는 사례 BCR/FAR/층수 정보 없음"})

    # 6) footprint 수용(10) — 사례 건축면적이 대상 대지의 건폐 가능 면적에 들어가는가
    fp = summary.get("building_area_sqm")
    if limits is not None and area_sqm and fp:
        capacity = area_sqm * limits.building_coverage_ratio
        if setback_m is not None and setback_m > 0:
            side = math.sqrt(area_sqm)
            eff_side = max(0.0, side - 2.0 * setback_m)
            capacity = min(capacity, eff_side * eff_side)
        if float(fp) <= capacity + 1e-9:
            breakdown.append({"factor": "footprint수용", "score": 10.0, "max": 10,
                              "basis": f"사례 건축면적 {fp:.0f}㎡ ≤ 수용한도 {capacity:.0f}㎡"})
        elif capacity > 0:
            s = round(10.0 * capacity / float(fp), 1)
            breakdown.append({"factor": "footprint수용", "score": s, "max": 10,
                              "basis": f"사례 건축면적 {fp:.0f}㎡ > 수용한도 {capacity:.0f}㎡(비례 감점)"})
        else:
            breakdown.append({"factor": "footprint수용", "score": 0.0, "max": 10,
                              "basis": "수용한도 0㎡(세트백으로 유효면적 소진)"})
    else:
        breakdown.append({"factor": "footprint수용", "score": 0.0, "max": 10,
                          "basis": "사례 건축면적(summary) 또는 대지면적·용도지역 정보 없음"})

    score = round(sum(b["score"] for b in breakdown), 1)
    return score, breakdown


async def find_similar(db: AsyncSession, *, building_use: str | None, area_sqm: float | None,
                       unit_types: list[str], k: int = 5,
                       zone_code: str | None = None) -> list[dict[str, Any]]:
    """유사 사례 Top-K(결정론 메타 스코어링).

    zone_code 미지정 시 기존 v1 정렬·필터 그대로(하위호환), 지정 시 similarity_v2
    기준 정렬. similarity_v2/similarity_breakdown 필드는 항상 additive 제공.
    """
    await ensure_schema(db)
    # 후보: 동일 용도 우선, 없으면 전체(최근 200)
    rows = (await db.execute(
        text(f"SELECT {_COLS} FROM design_references ORDER BY created_at DESC LIMIT 200")
    )).all()
    cands = [_row(r) for r in rows]
    scored: list[dict[str, Any]] = []
    for c in cands:
        v2, breakdown = similarity_v2(c, building_use=building_use, zone_code=zone_code,
                                      area_sqm=area_sqm, unit_types=unit_types)
        scored.append({**c,
                       "similarity": _similarity(c, building_use=building_use,
                                                 area_sqm=area_sqm, unit_types=unit_types),
                       "similarity_v2": v2, "similarity_breakdown": breakdown})
    if zone_code is not None:
        scored = [s for s in scored if s["similarity_v2"] > 0]
        scored.sort(key=lambda x: (x["similarity_v2"], x["similarity"]), reverse=True)
    else:
        scored = [s for s in scored if s["similarity"] > 0]
        scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]


async def derive_reference_mass_hint(
    db: AsyncSession, *, site_area_sqm: float | None, zone_code: str | None,
    building_use: str | None, unit_types: list[str], k: int = 5,
) -> dict[str, Any]:
    """유사 사례 Top-K 중 '기하 보유·치수 유효' 최상위 사례의 종횡비를 매스 힌트로 도출한다.

    §4-B 참조설계 피드백 — AutoDesignEngine 합성 경로(generate)에 주입할 결정론 힌트를
    만든다. find_similar(법규 인지 v2 정렬) 결과를 순위대로 순회하며, 기하가 없는
    (has_geometry False)·정규화 실패·치수 무효(폭/깊이 ≤ 0) 사례는 건너뛰어 다음 후보로
    재탐색한다(handoff '조립실패 시 더 타이트한 필터로 재탐색'의 결정론 구현 — footprint
    수용도는 similarity_v2의 footprint 인자로 이미 순위에 반영됨). 사용 가능한 사례가
    없으면 used=False + 정직 사유(가짜 추천 금지).

    Returns:
        {used, hint, ref, note, candidates}
        - hint: 엔진 SiteInput.reference_mass로 그대로 주입하는 dict(또는 None) —
          {aspect, ref_id, title, similarity, source, basis}.
        - ref: 선택된 사례 요약(없으면 None). candidates: 기하 보유 후보 수.
    """
    cands = await find_similar(db, building_use=building_use, area_sqm=site_area_sqm,
                               unit_types=unit_types, k=k, zone_code=zone_code)
    with_geo = [c for c in cands if c.get("has_geometry")]
    skipped = 0
    for c in with_geo:
        full = await get_reference(db, c["id"])
        raw = full.get("geometry_json") if full else None
        if not raw:
            skipped += 1
            continue
        try:
            dims = mass_dims(normalize_geometry(raw))
        except (GeometryError, ValueError, KeyError, TypeError):
            skipped += 1
            continue
        ref_w = dims["building_width_m"]
        ref_d = dims["building_depth_m"]
        if ref_w <= 0 or ref_d <= 0:
            skipped += 1
            continue
        aspect = round(ref_w / ref_d, 3)
        sim = c.get("similarity_v2")
        if sim is None:
            sim = c.get("similarity")
        return {
            "used": True,
            "hint": {
                "aspect": aspect,
                "ref_id": c["id"],
                "title": c.get("title"),
                "similarity": sim,
                "source": "design_reference",
                "basis": f"유사 사례 '{c.get('title') or c['id']}' 기하 종횡비 "
                         f"{aspect:.2f}(전면 {ref_w:.1f}m / 깊이 {ref_d:.1f}m)로 매스 편향",
            },
            "ref": {
                "id": c["id"], "title": c.get("title"),
                "similarity_v2": c.get("similarity_v2"),
                "area_sqm": c.get("area_sqm"), "floors": c.get("floors"),
                "building_width_m": ref_w, "building_depth_m": ref_d,
            },
            "note": (f"기하 보유 후보 {len(with_geo)}개 중 최상위 적합 사례 적용"
                     + (f"({skipped}개 정규화/치수 무효로 건너뜀)" if skipped else "")),
            "candidates": len(with_geo),
        }

    # 사용 가능한 기하 사례 없음 — 정직 표기(가짜 추천 금지)
    if with_geo:
        note = f"기하 보유 {len(with_geo)}개 모두 정규화/치수 무효로 참조 미적용"
    elif cands:
        note = "유사 사례는 있으나 기하(geometry) 보유분이 없어 참조 미적용"
    else:
        note = "유사 사례 라이브러리에 부합 사례 없음"
    return {"used": False, "hint": None, "ref": None, "note": note,
            "candidates": len(with_geo)}
