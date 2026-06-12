"""DA-2 — 설계 기하/파라미터 어댑터.

- params_from_ifc          : BIMIFCService.analyze_ifc 재사용 — IFC 물량을 설계 파라미터로 변환.
- design_payload_from_shapes: CAD 도형 페이로드 검증 패스스루(BuildingComplianceService
  design_raw 형식) — 기하 변형 없이 타입·참조만 검증하고 무효 항목은 사유와 함께 제외.
- merge_params             : 출처 우선순위 user > ifc > brief 병합 + 수치 5%+ 괴리 conflicts[].

정직성 원칙: 변환 실패·무효 데이터는 폐기 사유를 issues/note로 남기고,
임의 기본값·가짜 수치를 만들지 않는다.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

logger = structlog.get_logger()

# 출처 간 수치 괴리 임계(상대 5% 이상이면 conflicts에 기록).
_CONFLICT_THRESHOLD = 0.05

# 병합 우선순위(높은 순) — 사용자가 직접 입력한 값이 항상 최우선.
_SOURCE_PRIORITY = ("user", "ifc", "brief")


# ─────────────────────────────────────────────────────────────────────────────
# IFC → 설계 파라미터 (BIMIFCService.analyze_ifc 재사용)
# ─────────────────────────────────────────────────────────────────────────────
async def params_from_ifc(db: Any, project_id: Any, tenant_id: Any, file_url: str) -> dict[str, Any]:
    """IFC 파일 분석 결과(BIMIFCService.analyze_ifc)를 설계 파라미터로 변환한다.

    - 연면적(total_floor_area_sqm)은 IfcSlab 면적 합 기준 근사치만 제공한다
      (전체 element 면적 합은 벽체 포함이라 GFA가 아님 — 과대값 방지).
    - 분석 실패(라이브러리 미설치·파일 오류 등)는 available=False + note(예외 미전파).

    Returns:
        {"available": bool, "params": dict, "source": "bim_ifc",
         "ifc_version": str|None, "raw": dict|None, "note": str|None}
    """
    try:
        from apps.api.services.bim_ifc_service import BIMIFCService

        result = await BIMIFCService(db).analyze_ifc(
            project_id=project_id, tenant_id=tenant_id, file_url=file_url
        )
    except Exception as e:  # noqa: BLE001 — ifcopenshell/minio 부재 등은 정직한 빈 결과
        logger.warning("IFC 파라미터 변환 실패", error=str(e)[:160])
        return {
            "available": False, "params": {}, "source": "bim_ifc",
            "ifc_version": None, "raw": None,
            "note": f"IFC 분석 실패 — 파라미터 미산출(가짜값 금지): {str(e)[:160]}",
        }

    breakdown = result.material_breakdown or []
    slab_area: float | None = None
    for item in breakdown:
        if isinstance(item, dict) and item.get("type") == "IfcSlab":
            try:
                slab_area = float(item.get("area_sqm") or 0) or None
            except (TypeError, ValueError):
                slab_area = None
            break

    params: dict[str, Any] = {
        "total_volume_m3": result.total_volume_m3,
        "element_count": result.element_count,
    }
    note: str | None = None
    if slab_area:
        params["total_floor_area_sqm"] = round(slab_area, 2)
        note = "연면적은 IFC 슬라브(IfcSlab) 면적 합 기준 근사치(정밀 GFA 아님 — 설계도서 확인 필요)"
    else:
        note = "IFC에 슬라브 물량이 없어 연면적 미산출(벽체 포함 면적 합으로 대체하지 않음 — 정직)"

    return {
        "available": True,
        "params": params,
        "source": "bim_ifc",
        "ifc_version": result.ifc_version,
        "raw": {
            "total_area_sqm": result.total_area_sqm,
            "total_volume_m3": result.total_volume_m3,
            "element_count": result.element_count,
            "material_breakdown": breakdown,
        },
        "note": note,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CAD 도형 → 검증 패스스루 (BuildingComplianceService design_raw 형식)
# ─────────────────────────────────────────────────────────────────────────────
def _to_float(value: Any) -> float | None:
    """유한 실수만 통과(bool·NaN·inf·비수치 → None)."""
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def design_payload_from_shapes(shapes: dict[str, Any] | None) -> dict[str, Any]:
    """CAD 도형 페이로드를 검증해 BuildingComplianceService design_raw로 패스스루.

    - 기하를 변형하지 않는다. 타입 검증·참조 정합(점 ID 존재)만 수행한다.
    - 무효 항목은 제외하고 issues에 사유를 남긴다(조용한 무시 금지).
    - points 또는 surfaces가 비면 valid=False(법규 기하검증 불가 — 정직).

    Returns:
        {"valid": bool, "design": dict|None, "issues": list[str]}
    """
    issues: list[str] = []
    if not isinstance(shapes, dict) or not shapes:
        return {"valid": False, "design": None, "issues": ["도형 페이로드 없음 — 기하 검증 생략"]}

    points: list[dict[str, Any]] = []
    point_ids: set[str] = set()
    for p in shapes.get("points") or []:
        if not isinstance(p, dict):
            issues.append("point 무효(객체 아님) — 제외")
            continue
        x, y = _to_float(p.get("x")), _to_float(p.get("y"))
        pid = p.get("id")
        if pid is None or x is None or y is None:
            issues.append(f"point 무효(id/x/y 결손) — 제외: id={pid!r}")
            continue
        pid = str(pid)
        points.append({"id": pid, "x": x, "y": y})
        point_ids.add(pid)

    lines: list[dict[str, Any]] = []
    for ln in shapes.get("lines") or []:
        if not isinstance(ln, dict):
            issues.append("line 무효(객체 아님) — 제외")
            continue
        lid, sp, ep = ln.get("id"), ln.get("start_point_id"), ln.get("end_point_id")
        if lid is None or sp is None or ep is None:
            issues.append(f"line 무효(id/끝점 결손) — 제외: id={lid!r}")
            continue
        sp, ep = str(sp), str(ep)
        if sp not in point_ids or ep not in point_ids:
            issues.append(f"line 참조점 미존재 — 제외: id={lid!r}")
            continue
        lines.append({"id": str(lid), "start_point_id": sp, "end_point_id": ep})

    surfaces: list[dict[str, Any]] = []
    for s in shapes.get("surfaces") or []:
        if not isinstance(s, dict):
            issues.append("surface 무효(객체 아님) — 제외")
            continue
        sid = s.get("id")
        raw_ids = s.get("point_ids")
        if sid is None or not isinstance(raw_ids, list):
            issues.append(f"surface 무효(id/point_ids 결손) — 제외: id={sid!r}")
            continue
        valid_ids = [str(pid) for pid in raw_ids if str(pid) in point_ids]
        if len(valid_ids) < 3:
            issues.append(f"surface 유효 꼭짓점 3개 미만 — 제외: id={sid!r}")
            continue
        if len(valid_ids) != len(raw_ids):
            issues.append(f"surface 일부 참조점 미존재 — 유효 점만 통과: id={sid!r}")
        surfaces.append({"id": str(sid), "point_ids": valid_ids})

    floor_count = shapes.get("floor_count", 1)
    try:
        floor_count = max(1, int(floor_count))
    except (TypeError, ValueError):
        issues.append(f"floor_count 무효({shapes.get('floor_count')!r}) — 1층으로 처리")
        floor_count = 1

    height = _to_float(shapes.get("building_height_m"))
    if height is None or height < 0:
        if shapes.get("building_height_m") is not None:
            issues.append(f"building_height_m 무효({shapes.get('building_height_m')!r}) — 0으로 처리(높이검증 비활성)")
        height = 0.0

    scale = _to_float(shapes.get("scale"))
    if scale is None or scale <= 0:
        if shapes.get("scale") is not None:
            issues.append(f"scale 무효({shapes.get('scale')!r}) — 기본 10.0 적용")
        scale = 10.0

    design: dict[str, Any] = {
        "points": points,
        "lines": lines,
        "surfaces": surfaces,
        "floor_count": floor_count,
        "building_height_m": height,
        "scale": scale,
    }

    # 옵션 필드(있을 때만 패스스루) — 세트백·정북이격.
    setbacks = shapes.get("setback_distances")
    if isinstance(setbacks, dict):
        cleaned = {str(k): v for k, v in ((k, _to_float(v)) for k, v in setbacks.items()) if v is not None}
        if cleaned:
            design["setback_distances"] = cleaned
    north = _to_float(shapes.get("north_setback_m"))
    if north is not None and north >= 0:
        design["north_setback_m"] = north

    valid = bool(points) and bool(surfaces)
    if not valid:
        issues.append("유효한 점/면이 없어 기하 법규검증 불가(정직한 생략)")
    return {"valid": valid, "design": design if valid else None, "issues": issues}


# ─────────────────────────────────────────────────────────────────────────────
# 출처 병합 (user > ifc > brief)
# ─────────────────────────────────────────────────────────────────────────────
def _unwrap(value: Any) -> Any:
    """brief 필드({value, quote, confidence})는 value만 추출, 그 외는 그대로."""
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def merge_params(
    user: dict[str, Any] | None = None,
    ifc: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """설계 파라미터를 출처 우선순위(user > ifc > brief)로 병합한다.

    - brief 필드는 {value, quote, confidence} 래핑을 자동 해제한다.
    - 동일 키의 수치가 출처 간 상대 5% 이상 괴리면 conflicts[]에 기록한다
      (채택값은 우선순위 그대로 — 괴리는 숨기지 않고 표면화).
    - 문자열 필드는 우선순위 채택만 하고 수치 괴리 판정 대상이 아니다.

    Returns:
        {"params": dict, "param_sources": {key: 출처}, "conflicts": list[dict],
         "priority": "user > ifc > brief"}
    """
    sources: list[tuple[str, dict[str, Any]]] = [
        ("user", user if isinstance(user, dict) else {}),
        ("ifc", ifc if isinstance(ifc, dict) else {}),
        ("brief", brief if isinstance(brief, dict) else {}),
    ]

    # 키 순서: 우선순위 출처 등장 순(결정적).
    keys: list[str] = []
    for _name, data in sources:
        for key in data:
            if key not in keys:
                keys.append(key)

    merged: dict[str, Any] = {}
    origin: dict[str, str] = {}
    conflicts: list[dict[str, Any]] = []

    for key in keys:
        candidates: list[tuple[str, Any]] = []
        for name, data in sources:
            if key in data:
                value = _unwrap(data.get(key))
                if value is not None:
                    candidates.append((name, value))
        if not candidates:
            continue

        chosen_source, chosen_value = candidates[0]  # 우선순위 첫 후보
        merged[key] = chosen_value
        origin[key] = chosen_source

        # 수치 괴리 검사(유한 수치 2개 이상일 때만).
        numeric = [(name, _to_float(value)) for name, value in candidates]
        numeric = [(name, num) for name, num in numeric if num is not None]
        if len(numeric) < 2:
            continue
        values_by_source = dict(numeric)
        chosen_num = values_by_source.get(chosen_source)
        if chosen_num is None:
            continue
        base = max(abs(num) for _name, num in numeric)
        if base <= 0:
            continue
        max_deviation = max(abs(num - chosen_num) / base for _name, num in numeric)
        if max_deviation >= _CONFLICT_THRESHOLD:
            conflicts.append({
                "key": key,
                "values": values_by_source,
                "chosen_source": chosen_source,
                "chosen_value": chosen_num,
                "deviation_pct": round(max_deviation * 100, 1),
                "note": (
                    "출처 간 5% 이상 괴리 — 우선순위(user>ifc>brief)값을 채택했으나 "
                    "원천 데이터 확인 권장"
                ),
            })

    return {
        "params": merged,
        "param_sources": origin,
        "conflicts": conflicts,
        "priority": " > ".join(_SOURCE_PRIORITY),
    }
