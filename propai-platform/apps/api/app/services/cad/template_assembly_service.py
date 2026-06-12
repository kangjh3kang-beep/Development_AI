"""템플릿 조립(U3 R4) — 참조설계 기하를 대상 스펙에 결정론 변환·재검증.

설계 철학(기존 커널 패턴 — design_spec.py 참조):
  참조 사례의 geometry를 대상 대지에 맞춰 ① 균등 스케일(0.7~1.3 가드)
  ② 0°/90° 회전 2후보 중 적합 선택 ③ 층수 법규 클램프로 변환하고,
  세대 배분(compute_unit_layout)·요약 지표는 변환된 치수로 전부 '재계산'한다
  (원본 summary 복사 금지 — 가짜 지표 차단). 최종 결과는
  validate_spec/validate_geometry 하드게이트를 통과해야 passed=True.

LLM·외부호출 없이 순수 결정론으로 동작한다(동일 입력 = 동일 출력).
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from .auto_design_engine import AutoDesignEngineService
from .design_reference_geometry import GeometryError, mass_dims, normalize_geometry
from .design_spec import DesignSpec, has_errors, validate_geometry, validate_spec

logger = structlog.get_logger(__name__)

# 균등 스케일 가드 — 이 범위 밖 변형은 평면 비례를 깨므로 클램프(왜곡 금지)
SCALE_MIN = 0.7
SCALE_MAX = 1.3
_PX = 10.0  # 표준 스케일(1m = 10px) — design_reference_geometry.STANDARD_SCALE_PX_PER_M 동일


def _transform_points(points: list[dict[str, Any]], bbox: dict[str, float], *,
                      rotation_deg: int, scale: float,
                      offset_x_px: float, offset_y_px: float) -> list[dict[str, Any]]:
    """bbox 원점 기준 회전(0/90°)→균등 스케일→세트백 오프셋 평행이동(결정론)."""
    min_x, min_y = bbox["min_x"], bbox["min_y"]
    width_px = bbox["max_x"] - bbox["min_x"]
    out: list[dict[str, Any]] = []
    for p in points:
        lx = float(p["x"]) - min_x
        ly = float(p["y"]) - min_y
        if rotation_deg == 90:
            lx, ly = ly, width_px - lx  # -90° 회전(행렬식 +1 — 반사 아님)
        out.append({
            "id": p["id"],
            "x": round(lx * scale + offset_x_px, 1),
            "y": round(ly * scale + offset_y_px, 1),
        })
    return out


def assemble_from_reference(ref: dict[str, Any], spec: DesignSpec) -> dict[str, Any]:
    """참조 사례 기하를 대상 스펙(DesignSpec)에 맞춰 조립한다.

    Returns:
        {design_payload, summary, violations, passed, adaptations, reference}
        — summary는 변환 치수로 전부 재계산(원본 복사 금지),
          passed는 validate_spec+validate_geometry 하드게이트 결과.

    Raises:
        ValueError: 참조에 geometry가 없거나 치수가 유효하지 않은 경우(명시 오류).
        GeometryError: geometry 정규화 실패.
    """
    raw_geometry = ref.get("geometry_json")
    if not raw_geometry:
        raise ValueError(
            "참조 사례에 geometry가 없습니다 — DXF 업로드 또는 플랫폼 설계 저장 후 조립할 수 있습니다.")
    geometry = normalize_geometry(raw_geometry)  # 멱등 재정규화(라운드트립 안전)
    dims = mass_dims(geometry)
    ref_w = dims["building_width_m"]
    ref_d = dims["building_depth_m"]
    if ref_w <= 0 or ref_d <= 0:
        raise ValueError(f"참조 geometry 치수가 유효하지 않습니다(폭 {ref_w}m × 깊이 {ref_d}m).")

    adaptations: list[dict[str, Any]] = []
    engine = AutoDesignEngineService()
    legal = engine.get_legal_limits(spec.zone_code)
    site = spec.to_site_input()
    effective = engine.compute_effective_site(site)
    eff_w = effective["effective_width_m"]
    eff_d = effective["effective_depth_m"]
    max_footprint = min(spec.site_area_sqm * legal["max_bcr_percent"] / 100.0,
                        effective["effective_area_sqm"])

    # ── ② 0°/90° 회전 2후보: 더 큰 적합 스케일을 허용하는 방향 선택 ──
    candidates: list[dict[str, Any]] = []
    for deg, (w, d) in ((0, (ref_w, ref_d)), (90, (ref_d, ref_w))):
        fit = min(eff_w / w if w > 0 else 0.0, eff_d / d if d > 0 else 0.0)
        by_bcr = math.sqrt(max_footprint / (w * d)) if w * d > 0 and max_footprint > 0 else 0.0
        candidates.append({"rotation_deg": deg, "w": w, "d": d,
                           "scale_raw": min(fit, by_bcr)})
    best = max(candidates, key=lambda c: c["scale_raw"])
    rotation_deg = best["rotation_deg"]
    if rotation_deg == 90:
        adaptations.append({
            "type": "rotate", "value": 90,
            "basis": f"유효 대지 {eff_w:.1f}×{eff_d:.1f}m에 90° 회전이 더 큰 배치 허용",
        })

    # ── ① 균등 스케일(0.7~1.3 가드) — 비례 왜곡 금지, 가드 밖은 클램프 후 게이트가 판정 ──
    scale_raw = best["scale_raw"]
    scale = min(max(scale_raw, SCALE_MIN), SCALE_MAX)
    adaptations.append({
        "type": "scale", "value": round(scale, 3), "raw": round(scale_raw, 3),
        "clamped": abs(scale - scale_raw) > 1e-9,
        "basis": f"균등 스케일 가드 {SCALE_MIN}~{SCALE_MAX}"
                 f"(필요 {scale_raw:.3f} → 적용 {scale:.3f})",
    })

    new_w = round(best["w"] * scale, 1)
    new_d = round(best["d"] * scale, 1)
    footprint = round(new_w * new_d, 2)

    # ── ③ 층수 클램프(높이·FAR 법규 한도) ──
    ref_floors = int(ref.get("floors") or geometry.get("floor_count") or 1)
    desired_floors = int(spec.num_floors or ref_floors)
    max_by_height = (int(legal["max_height_m"] / spec.floor_height_m)
                     if legal["max_height_m"] > 0 else 10 ** 6)
    far_cap_area = spec.site_area_sqm * legal["max_far_percent"] / 100.0
    max_by_far = int(far_cap_area / footprint) if footprint > 0 else 1
    num_floors = max(1, min(desired_floors, max_by_height, max_by_far))
    if num_floors != desired_floors:
        adaptations.append({
            "type": "floors_clamp", "value": num_floors, "raw": desired_floors,
            "basis": f"법규 클램프 — 높이한도 {max_by_height}층 / FAR한도 {max_by_far}층"
                     f"(요청 {desired_floors}층 → 적용 {num_floors}층)",
        })

    total_floor_area = round(footprint * num_floors, 2)
    building_height = round(num_floors * spec.floor_height_m, 2)
    bcr_pct = round(footprint / spec.site_area_sqm * 100, 2) if spec.site_area_sqm > 0 else 0.0
    far_pct = (round(total_floor_area / spec.site_area_sqm * 100, 2)
               if spec.site_area_sqm > 0 else 0.0)

    # ── 세대·코어 재계산(compute_unit_layout 재사용 — 원본 복사 금지) ──
    mass = {
        "building_width_m": new_w,
        "building_depth_m": new_d,
        "building_footprint_sqm": footprint,
        "num_floors": num_floors,
        "floor_height_m": spec.floor_height_m,
        "building_height_m": building_height,
        "total_floor_area_sqm": total_floor_area,
        "bcr_pct": bcr_pct,
        "far_pct": far_pct,
    }
    core_layout = engine.compute_core_layout(mass, spec.building_use)
    unit_layout = engine.compute_unit_layout(
        mass, core_layout, spec.target_unit_types or [], spec.building_use)

    # ── 기하 변환 → design_payload(프론트 CAD 스토어 호환) ──
    sb = spec.setback_m
    offset_x = sb.west * _PX
    offset_y = sb.north * _PX
    points = _transform_points(geometry["points"], geometry["bbox"],
                               rotation_deg=rotation_deg, scale=scale,
                               offset_x_px=offset_x, offset_y_px=offset_y)
    design_payload = {
        "points": points,
        "lines": [dict(ln) for ln in geometry.get("lines", [])],
        "surfaces": [dict(sf) for sf in geometry.get("surfaces", [])],
        "floor_count": num_floors,
        "building_height_m": building_height,
        "scale": _PX,
    }

    # ── 요약(변환 후 재계산값만 — 원본 summary 복사 금지) ──
    summary: dict[str, Any] = {
        "building_area_sqm": footprint,
        "total_floor_area_sqm": total_floor_area,
        "num_floors": num_floors,
        "building_height_m": building_height,
        "bcr_percent": bcr_pct,
        "far_percent": far_pct,
        "total_units": unit_layout["total_units"],
        "parking_count": unit_layout["parking_required"],
        "core_count": core_layout["num_cores"],
        "units_feasible": unit_layout.get("units_feasible", True),
        "source": "template_assembly",
        "reference_id": ref.get("id"),
    }
    if not unit_layout.get("units_feasible", True):
        summary["units_note"] = unit_layout.get("infeasible_reason", "세대 성립 불가")

    # ── 하드게이트: 스펙 + 변환 기하 법규 재검증(가짜 통과 금지) ──
    violations = validate_spec(spec) + validate_geometry(
        spec, bcr_pct=bcr_pct, far_pct=far_pct, building_height_m=building_height)
    passed = not has_errors(violations)

    logger.info(
        "template_assembly_done",
        ref_id=ref.get("id"), rotation=rotation_deg, scale=round(scale, 3),
        floors=num_floors, bcr=bcr_pct, far=far_pct, passed=passed,
    )
    return {
        "design_payload": design_payload,
        "summary": summary,
        "violations": [v.model_dump() for v in violations],
        "passed": passed,
        "adaptations": adaptations,
        "reference": {
            "id": ref.get("id"), "title": ref.get("title"),
            "building_use": ref.get("building_use"), "zone_code": ref.get("zone_code"),
            "area_sqm": ref.get("area_sqm"), "floors": ref.get("floors"),
            "source": ref.get("source"), "geometry_source": ref.get("geometry_source"),
        },
    }


__all__ = ["assemble_from_reference", "GeometryError", "SCALE_MIN", "SCALE_MAX"]
