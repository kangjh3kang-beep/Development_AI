"""L3-B — 일조 시뮬(태양궤도 근사). 동지 연속일조시간 + 인접대지 차폐(건축법 제61조 연계).

위도/기하는 입력(PreflightContext/SemanticElement), 기준시간/모델상수는 param. 입력 신뢰도 전파.
"""
from __future__ import annotations

from app.adapters.solar.sun_position import (
    shadow_length,
    solar_noon_altitude,
    winter_daylight_hours,
)
from app.contracts.sim_metric import MethodTrace, MetricStatus, SimMetric, emit
from app.core.confidence import clamp01
from app.services.sim.sim_params import SimParamSource

_BASIS = "건축법 제61조"


def run(site: dict, params: SimParamSource) -> SimMetric:
    geom_conf = float(site.get("geom_confidence", 1.0))

    required_keys = ("latitude", "building_height", "adjacent_distance")
    if any(site.get(k) is None for k in required_keys):
        return SimMetric(
            metric_id="continuous_sunlight_hours", value=None, unit="hours",
            status=MetricStatus.UNAVAILABLE, confidence=geom_conf,
            method_trace=MethodTrace(model="solar_orbit_approx", assumptions=["필수 입력 결손"], inputs={}),
            flags=["missing_geometry"],
        )

    tilt = params.get("solar_axial_tilt_deg")
    dph = params.get("degrees_per_hour")
    lat = float(site["latitude"])
    bh = float(site["building_height"])
    adj = float(site["adjacent_distance"])

    noon_alt = solar_noon_altitude(lat, tilt)
    daylight = winter_daylight_hours(lat, tilt, dph)
    shadow = shadow_length(bh, noon_alt)
    exposure = clamp01(adj / shadow) if shadow > 0 else 1.0
    continuous = exposure * daylight

    min_hours = params.get("sunlight_min_continuous_hours")
    flags = ["sunlight_below_min"] if continuous < min_hours else []

    trace = MethodTrace(
        model="solar_orbit_approx",
        assumptions=[
            "동지 정오 태양고도 단일 그림자 근사(일중 시간별 변화 미반영) — 보수적 추정",
            "인접건물 단일 차폐, 지형/식재 무시",
            "노출비례 선형 근사",
            f"axial_tilt={tilt}",
        ],
        inputs={"latitude": lat, "building_height": bh, "adjacent_distance": adj},
        basis_article=_BASIS,
    )
    return emit(SimMetric(
        metric_id="continuous_sunlight_hours", value=continuous, unit="hours",
        status=MetricStatus.OK, confidence=geom_conf, method_trace=trace,
        flags=flags, required=min_hours,
    ))
