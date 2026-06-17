"""3D 일조/그림자 정밀 시뮬 — shapely 기하. 주변 건물 footprint+층수 → 매스 압출 → 그림자 투영.

동지(최악) 9~15시 태양위치별로 주변 건물 그림자 폴리곤을 생성·합집합하고, 대상 대지와의 교차로
일영 비율·연속 일조시간을 산정(건축법 일조권 판정 기초). 위경도→로컬 미터 평면 근사(소영역 정확).
결정론(고정 동지 적위·시각). shapely 미설치/결손 시 graceful.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.contracts.rationale import Rationale, RationaleInput
from app.services.explain.legal_refs import refs

if TYPE_CHECKING:
    from app.services.sim.sim_params import SimParamSource

_DECL_WINTER = -23.44   # 동지 적위(deg) — 천문 상수
_LAT_M_PER_DEG = 110540.0  # 위도 1도≈미터(WGS84) — 측지 상수
_LON_M_PER_DEG = 111320.0  # 경도 1도≈미터(적도) — 측지 상수
# 표준 층고(층수→높이 근사)는 법규성 파라미터 → 모듈 상수 아닌 함수 인자로 주입(INV-20).


def _to_local_m(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """위경도 → 대상지 중심 기준 로컬 미터(x=동, y=북)."""
    x = (lon - lon0) * _LON_M_PER_DEG * math.cos(math.radians(lat0))
    y = (lat - lat0) * _LAT_M_PER_DEG
    return x, y


def _ring_to_local(coords, lon0: float, lat0: float):
    return [_to_local_m(c[0], c[1], lon0, lat0) for c in coords]


def _geom_to_polygon(geometry: dict, lon0: float, lat0: float):
    """GeoJSON Polygon/MultiPolygon → shapely(로컬 미터). 실패 None."""
    try:
        from shapely.geometry import MultiPolygon, Polygon
    except ImportError:
        return None
    if not geometry:
        return None
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    try:
        if gtype == "Polygon":
            return Polygon(_ring_to_local(coords[0], lon0, lat0))
        if gtype == "MultiPolygon":
            return MultiPolygon([Polygon(_ring_to_local(poly[0], lon0, lat0)) for poly in coords])
    except Exception:  # noqa: BLE001
        return None
    return None


def building_shadow(footprint, height_m: float, sun_alt_deg: float, sun_azim_deg: float):
    """건물 footprint(shapely, 미터) → 그림자 폴리곤. 태양 반대로 길이만큼 투영한 매스의 convex hull."""
    if sun_alt_deg <= 0 or height_m <= 0:
        return None
    from shapely.affinity import translate
    length = height_m / math.tan(math.radians(sun_alt_deg))
    rad = math.radians(sun_azim_deg + 180.0)  # 그림자 방향=태양 반대
    dx = length * math.sin(rad)
    dy = length * math.cos(rad)
    moved = translate(footprint, xoff=dx, yoff=dy)
    return footprint.union(moved).convex_hull


def sunlight_analysis(target_geometry: dict, buildings: list[dict], latitude: float,
                      params: SimParamSource | None = None) -> dict | None:
    """대상 대지 + 주변 건물 → 동지 시각별 일영 비율 + 일조시각 수(건축법 일조권 기초) + rationale. 결손 None.

    params: 시뮬 파라미터 소스(SimParamSource, INV-20). 표준 층고/일영 임계/관측 시각창은 sim_params.json
            SSOT에서 주입(코드 내 법규 리터럴 0건). None이면 기본 데이터셋.
    """
    from app.services.sim.sim_params import SimParamSource
    params = params or SimParamSource()
    floor_height_m = params.get("shadow3d_floor_height_m")          # 층수→높이 환산 표준 층고(height_m 우선)
    sunlight_threshold = params.get("shadow3d_sunlight_threshold")  # 일영비율 이 값 미만이면 '과반 일조'로 계상
    h0 = int(params.get("shadow3d_obs_hour_start"))
    h1 = int(params.get("shadow3d_obs_hour_end"))
    hours = tuple(range(h0, h1 + 1))                                # 동지 관측 시각창(비법정 근사)
    try:
        from shapely.ops import unary_union
    except ImportError:
        return None
    # 대상지 중심을 로컬 원점으로
    tcoords = (target_geometry or {}).get("coordinates")
    if not tcoords:
        return None
    flat = tcoords[0] if (target_geometry.get("type") == "Polygon") else tcoords[0][0]
    lon0 = sum(c[0] for c in flat) / len(flat)
    lat0 = sum(c[1] for c in flat) / len(flat)
    target = _geom_to_polygon(target_geometry, lon0, lat0)
    if target is None or target.area <= 0:
        return None

    masses = []
    for b in buildings:
        poly = _geom_to_polygon(b.get("geometry"), lon0, lat0)
        if poly is None or poly.area <= 0:
            continue
        h = b.get("height_m") or 0.0
        if not h:
            h = (b.get("floors") or 0) * floor_height_m
        if h > 0:
            masses.append((poly, h))

    per_hour = []
    sunny_hours = 0.0
    for hour in hours:
        ha = (hour - 12) * 15.0
        alt, az = _sun(latitude, ha)
        if alt <= 0:
            per_hour.append({"hour": hour, "shaded_ratio": 1.0, "sun_alt": round(alt, 1)})
            continue
        shadows = [s for (fp, h) in masses if (s := building_shadow(fp, h, alt, az)) is not None]
        shaded_ratio = 0.0
        if shadows:
            shadow_union = unary_union(shadows)
            inter = target.intersection(shadow_union)
            shaded_ratio = round(inter.area / target.area, 3) if not inter.is_empty else 0.0
        if shaded_ratio < sunlight_threshold:  # 과반 일조 시 '일조시각'으로 계상
            sunny_hours += 1.0
        per_hour.append({"hour": hour, "shaded_ratio": shaded_ratio, "sun_alt": round(alt, 1)})

    rationale = Rationale(
        summary=(f"동지 9~15시 중 과반일조(일영<{sunlight_threshold}) {sunny_hours:.0f}/{len(hours)}시각 "
                 f"— 주변 매스 {len(masses)}동 그림자 기준"),
        formula=(f"시각별 일영비율=대지∩그림자합집합÷대지면적; 일조시각=일영<{sunlight_threshold}인 시각 수; "
                 f"그림자길이=높이÷tan(태양고도)"),
        inputs=[
            RationaleInput(name="대지면적(㎡,로컬평면근사)", value=round(target.area, 1),
                           source="VWORLD 필지 geometry(WGS84 미터근사)"),
            RationaleInput(name="주변 매스 수", value=len(masses),
                           source="VWORLD lt_c_bldginfo 높이/층수×층고"),
            RationaleInput(name="위도(°)", value=round(latitude, 4)),
            RationaleInput(name="동지 적위(°)", value=_DECL_WINTER, source="천문 상수(IAU 황도경사)"),
            RationaleInput(name="과반일조 임계", value=sunlight_threshold),
            RationaleInput(name="표준 층고(m)", value=floor_height_m),
        ],
        legal_basis=refs("건축법§61", "건축법시행령§86"),
        caveats=[
            "동지(최악) 기준 — 타 절기는 일조 양호",
            "sunny_hours_9to15는 '연속'이 아닌 과반일조 시각의 총합 — 건축법 시행령 §86의 "
            "'연속 일조시간' 판정과 별개(연속성 미검증)",
            "대지면적은 위경도→로컬미터 평면 근사(지적면적 아님)",
            "그림자는 footprint 압출 매스 — 실 입면 형상·발코니 등 미반영",
        ],
    )
    return {
        "latitude": latitude,
        "lot_area_m2": round(target.area, 1),
        "nearby_masses": len(masses),
        "per_hour": per_hour,
        "sunny_hours_9to15": sunny_hours,
        "method": f"동지 9~15시 그림자 투영(shapely), 일영<{sunlight_threshold} 시각을 일조시각 계상, 층수×{floor_height_m}m 매스",
        "rationale": rationale.model_dump(),
    }


def _sun(latitude: float, hour_angle_deg: float) -> tuple[float, float]:
    from app.adapters.solar.sun_position import sun_altitude_azimuth
    return sun_altitude_azimuth(latitude, _DECL_WINTER, hour_angle_deg)


def sunlight_metric(sun: dict | None, params: SimParamSource | None = None):
    """sunlight_analysis 결과 → SimMetric(emit 게이트로 근거 강제·일조 미달 flag). 결손 None.

    params: 시뮬 파라미터 소스(SimParamSource, INV-20). 일조시각 최소기준은 sim_params.json SSOT에서 주입
            (코드 내 법규 리터럴 0건). 미달 시 flag로 '확인 필요' 표면화.
    """
    if sun is None:
        return None
    from app.services.sim.sim_params import SimParamSource
    params = params or SimParamSource()
    min_hours = params.get("shadow3d_min_sunny_hours")
    from app.contracts.sim_metric import MethodTrace, MetricStatus, SimMetric, emit
    r = sun.get("rationale", {})
    val = sun.get("sunny_hours_9to15")
    flags = ["sunlight_below_min"] if (val is not None and val < min_hours) else []
    return emit(SimMetric(
        metric_id="sunlight_3d", value=val, unit="hours",
        status=MetricStatus.OK if val is not None else MetricStatus.UNAVAILABLE,
        method_trace=MethodTrace(
            model="shadow_3d_winter_9to15",
            assumptions=r.get("caveats", []),
            inputs={i["name"]: i["value"] for i in r.get("inputs", [])},
            basis_article="건축법 제61조(관련) — 비법정 근사(정북이격 판정 아님)"),
        flags=flags, required=min_hours,
    ))
