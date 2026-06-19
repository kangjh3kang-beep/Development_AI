"""한국 정북일조 빌더블 인벨로프(베팅 D) — 실제 건축가능 최대 볼륨·층수 산정.

건축법 시행령 제86조(정북방향 일조 확보 이격):
 - 전용/일반주거지역: 높이 9m 이하 부분은 정북 인접대지경계에서 1.5m 이상,
   9m 초과 부분은 그 부분 높이의 1/2 이상 이격.  → 거리 d에서 최대높이 H(d)=max(9, 2·(d−1.5)+9)? 보수적으로 H≤2d.
정북사선을 남북깊이에 대해 스트립 적분해 '일조로 실제 지을 수 있는' 최대 연면적을 구하고,
용적률(FAR) 한도와 비교해 '바인딩 제약'과 '일조 손실률'을 제시한다.

한계(v1 근사): 직사각형 대지 가정(W×D, 정북=깊이방향), 단일 매스, 측면이격 간이.
글로벌 툴(Forma/Zoneomics)이 모르는 '한국 정북일조'를 정량화하는 것이 핵심 차별점.
향후: VWorld 실측 PARCEL 폴리곤(shapely)·도로사선·인동간격·IFC 결합으로 정밀화.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.permit.building_code_rules import ZONE_DEFAULTS

# 정북일조 적용 용도지역(전용/일반주거). 준주거·상업·공업은 통상 미적용/완화.
_NORTH_LIGHT_ZONES = ("전용주거", "일반주거", "1종", "2종", "3종", "제1종", "제2종", "제3종")


def dims_from_polygon(geometry: dict[str, Any] | None) -> dict[str, Any] | None:
    """VWorld 필지 GeoJSON(geometry)에서 실측 남북깊이·동서폭·면적 도출.

    경위도(EPSG:4326)를 중심위도 기준 등거리 근사로 미터 변환 →
    bbox로 N-S 깊이(정북일조 핵심축)·E-W 폭, shapely로 실면적 산출.
    """
    if not geometry:
        return None
    try:
        from shapely.geometry import shape

        geom = shape(geometry)
        if geom.is_empty:
            return None
        minx, miny, maxx, maxy = geom.bounds  # lon/lat
        lat0 = (miny + maxy) / 2.0
        m_per_deg_lat = 110540.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
        width_m = (maxx - minx) * m_per_deg_lon     # 동서(E-W)
        depth_m = (maxy - miny) * m_per_deg_lat      # 남북(N-S) — 정북일조 축
        # 실면적: 경위도 폴리곤을 미터 평면으로 스케일 후 area
        from shapely.affinity import scale as _scale
        geom_m = _scale(geom, xfact=m_per_deg_lon, yfact=m_per_deg_lat, origin=(minx, miny))
        area_sqm = abs(geom_m.area)
        if depth_m <= 0 or width_m <= 0:
            return None
        return {
            "width_m": round(width_m, 2), "depth_m": round(depth_m, 2),
            "area_sqm": round(area_sqm, 1),
            "irregularity": round(1 - area_sqm / (width_m * depth_m), 3) if width_m * depth_m else 0,
        }
    except Exception:  # noqa: BLE001
        return None


# 시도별 대표 위도(동지 일영 계산용)
_LAT_BY_SIDO = {
    "서울": 37.55, "경기": 37.4, "인천": 37.45, "강원": 37.8,
    "충북": 36.8, "충남": 36.5, "대전": 36.35, "세종": 36.5,
    "전북": 35.8, "전남": 34.9, "광주": 35.16, "경북": 36.4,
    "대구": 35.87, "경남": 35.2, "부산": 35.18, "울산": 35.54, "제주": 33.5,
}


def _latitude(address: str, fallback: float = 37.5) -> float:
    for sido, lat in _LAT_BY_SIDO.items():
        if sido in (address or ""):
            return lat
    return fallback


def shadow_analysis(height_m: float, latitude: float = 37.5) -> dict[str, Any]:
    """동지(δ=-23.44°) 9·12·15시 태양고도→그림자 길이(L=H/tanθ). 일조권 영향 정량.

    태양고도 sin(alt)=sinφ·sinδ + cosφ·cosδ·cos(h), h=시각각(정오 0, ±15°/h).
    """
    if height_m <= 0:
        return {}
    decl = math.radians(-23.44)
    lat = math.radians(latitude)
    out: dict[str, Any] = {}
    hours = {"09시": -45.0, "정오": 0.0, "15시": 45.0}
    for label, ha_deg in hours.items():
        ha = math.radians(ha_deg)
        sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
        alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
        if alt <= 0.5:
            out[label] = {"solar_altitude_deg": round(alt, 1), "shadow_len_m": None}
        else:
            L = height_m / math.tan(math.radians(alt))
            out[label] = {"solar_altitude_deg": round(alt, 1), "shadow_len_m": round(L, 1)}
    noon_alt = out["정오"]["solar_altitude_deg"]
    max_shadow = max((v["shadow_len_m"] or 0) for v in out.values())
    return {
        "winter_solstice": out,
        "noon_altitude_deg": noon_alt,
        "max_shadow_len_m": round(max_shadow, 1),
        "latitude": latitude,
        "note": f"동지 정오 태양고도 {noon_alt}° 기준 그림자 최대 {round(max_shadow,1)}m. "
                "인접대지 일조 영향·인동간격 검토에 활용(정밀 3D 일영은 BIM 매스 결합 시).",
    }


def _zone_limits(zone: str) -> dict[str, Any]:
    for k, v in ZONE_DEFAULTS.items():
        if k in (zone or "") or (zone or "") in k:
            return v
    return {"max_bcr": 60, "max_far": 250, "max_height": 0}


def compute_buildable_envelope(
    *,
    land_area_sqm: float,
    zone: str = "",
    land_width_m: float | None = None,
    land_depth_m: float | None = None,
    floor_height_m: float = 3.0,
    bcr_limit_pct: float | None = None,
    far_limit_pct: float | None = None,
    side_setback_m: float = 0.5,
    latitude: float = 37.5,
) -> dict[str, Any]:
    """정북일조 인벨로프 기반 최대 건축가능 연면적·층수·볼륨과 용적률 대비 손실 산정."""
    if land_area_sqm <= 0:
        return {"error": "대지면적이 필요합니다."}

    lim = _zone_limits(zone)
    bcr = (bcr_limit_pct if bcr_limit_pct is not None else lim.get("max_bcr", 60)) / 100.0
    far = (far_limit_pct if far_limit_pct is not None else lim.get("max_far", 250)) / 100.0
    fh = max(2.4, floor_height_m)

    # 대지 치수: 미입력 시 정사각형 가정(정북=깊이 D)
    if not land_width_m or not land_depth_m:
        side = math.sqrt(land_area_sqm)
        W = land_width_m or side
        D = land_depth_m or side
    else:
        W, D = land_width_m, land_depth_m

    far_gfa = land_area_sqm * far               # 용적률 허용 연면적
    bcr_footprint = land_area_sqm * bcr          # 건폐율 허용 1층 바닥면적

    applies = any(k in (zone or "") for k in _NORTH_LIGHT_ZONES)

    if not applies:
        # 정북일조 미적용(준주거·상업 등) → 용적률·건폐율로 층수. ceil=FAR 담는 최소 층수(round 내림 과소산정 방지).
        floors = max(1, math.ceil(far / bcr)) if bcr > 0 else 1
        return {
            "applies_north_light": False,
            "zone": zone, "bcr_pct": round(bcr * 100, 1), "far_pct": round(far * 100, 1),
            "far_gfa_sqm": round(far_gfa), "envelope_gfa_sqm": round(far_gfa),
            "effective_gfa_sqm": round(far_gfa), "binding": "용적률",
            "daylight_loss_pct": 0.0,
            "max_height_m": round(floors * fh, 1), "max_floors": floors,
            "note": "정북일조 미적용 용도지역 — 용적률/건폐율이 한도. (정밀 높이는 가로구역 최고높이 별도 확인)",
            "approximation": "far-bcr-only",
            "assumptions": [
                "정북일조 미적용 용도지역 — 용적률/건폐율만 적용",
                "가로구역별 최고높이 별도 확인 필요",
            ],
        }

    # ── 정북일조 스트립 적분 ──
    usable_W = max(0.0, W - 2 * side_setback_m)
    strips = 200
    dz = D / strips
    envelope_volume = 0.0
    max_h = 0.0
    for i in range(strips):
        d = (i + 0.5) * dz  # 정북 경계로부터 거리
        if d < 1.5:
            h = 0.0
        else:
            # 9m 초과는 H/2 이격 → H ≤ 2d (보수적). 9m 이하는 1.5m 이격으로 허용.
            h = max(9.0, 2.0 * d)
        max_h = max(max_h, h)
        envelope_volume += usable_W * dz * h

    # 인벨로프 연면적(전부 채움 가정) = 볼륨/층고. 건폐율로 층당 바닥 상한 반영(개략).
    envelope_gfa = envelope_volume / fh
    effective_gfa = min(envelope_gfa, far_gfa)
    binding = "정북일조" if envelope_gfa < far_gfa else "용적률"
    loss = max(0.0, 1 - envelope_gfa / far_gfa) * 100 if far_gfa > 0 else 0.0
    # 현실 층수: 유효 연면적 ÷ 건폐율 바닥(전층 동일 가정 근사). ★ceil — 연면적을 '담는 데 필요한' 최소 층수
    # (round 내림 시 4.167→4층이 되어 표시 연면적을 담지 못하는 과소산정. 올림이어야 5층이 effective_gfa 수용).
    realistic_floors = max(1, math.ceil(effective_gfa / bcr_footprint)) if bcr_footprint > 0 else 1
    daylight_ceiling_floors = max(1, int(max_h / fh))

    # 공동주택 인동간격(채광 방향): 건축법 시행령 §86② — 통상 0.8H(무창벽 0.5H).
    realistic_height = realistic_floors * fh
    min_spacing_080 = round(0.8 * realistic_height, 1)
    min_spacing_050 = round(0.5 * realistic_height, 1)
    shadow = shadow_analysis(realistic_height, latitude)  # 동지 일영(그림자) 분석

    return {
        "applies_north_light": True,
        "min_building_spacing_m": min_spacing_080,        # 동간 채광거리 권고(0.8H)
        "min_building_spacing_blank_wall_m": min_spacing_050,  # 무창벽 0.5H
        "shadow_analysis": shadow,                         # 동지 9·12·15시 그림자 길이
        "row_distance_rule": "건축법 시행령 §86② 채광 인동간격 0.8H(무창벽 0.5H) — 공동주택 다동 배치 시 적용",
        "zone": zone, "bcr_pct": round(bcr * 100, 1), "far_pct": round(far * 100, 1),
        "lot_width_m": round(W, 1), "lot_depth_m": round(D, 1),
        "far_gfa_sqm": round(far_gfa),
        "envelope_gfa_sqm": round(envelope_gfa),
        "effective_gfa_sqm": round(effective_gfa),
        "binding": binding,
        "daylight_loss_pct": round(loss, 1),
        "buildable_volume_m3": round(envelope_volume),
        "daylight_ceiling_m": round(max_h, 1),            # 정북일조 사선 최고선
        "daylight_ceiling_floors": daylight_ceiling_floors,
        "max_floors": realistic_floors,                    # 용적률·건폐율 기준 현실 층수
        "max_height_m": round(realistic_floors * fh, 1),
        "bcr_footprint_sqm": round(bcr_footprint),
        "note": (
            "정북일조 사선(9m↓ 1.5m·9m↑ H/2 이격) 남북깊이 적분 최대 연면적. "
            f"공동주택 다동 배치 시 동간 채광거리 {min_spacing_080}m(0.8H) 확보 필요. "
            "도로사선제한은 2015년 폐지(가로구역별 최고높이로 대체)되어 미적용. "
            "직사각형 대지 근사(v1)."
            + (f" 일조로 용적률 대비 약 {round(loss,1)}% 건축면적 손실." if binding == "정북일조" else " 용적률이 한도(일조 여유).")
        ),
        "approximation": "rectangular-lot-strip-integration",
        "assumptions": [
            "직사각형 대지(W×D, 정북=깊이축) 가정",
            "단일 매스·측면 이격 간이(side_setback)",
            "9m 초과 H≤2d 보수 근사·도로사선 미적용",
        ],
    }
