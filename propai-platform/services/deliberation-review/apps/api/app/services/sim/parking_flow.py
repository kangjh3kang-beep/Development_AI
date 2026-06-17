"""L3-B — 주차 동선 시뮬. 회전반경/통로폭/단부거리 기하검증(주차장법 지표). 임계는 param."""
from __future__ import annotations

from app.contracts.sim_metric import MethodTrace, MetricStatus, SimMetric, emit
from app.services.sim.sim_params import SimParamSource

_BASIS = "주차장법 시행규칙"


def run(parking: dict, params: SimParamSource) -> SimMetric:
    geom_conf = float(parking.get("geom_confidence", 1.0))
    turn_radius = parking.get("turn_radius")

    if turn_radius is None:
        return SimMetric(
            metric_id="parking_turn_radius", value=None, unit="m",
            status=MetricStatus.UNAVAILABLE, confidence=geom_conf,
            method_trace=MethodTrace(model="parking_geometry", assumptions=["회전반경 입력 결손"], inputs={}),
            flags=["missing_turn_radius"],
        )

    turn_radius = float(turn_radius)
    required = params.get("parking_min_turn_radius_m")
    flags = ["turn_radius_below_min"] if turn_radius < required else []

    trace = MethodTrace(
        model="parking_geometry",
        assumptions=["회전반경 최소기준 비교"],
        inputs={"turn_radius": turn_radius},
        basis_article=_BASIS,
    )
    return emit(SimMetric(
        metric_id="parking_turn_radius", value=turn_radius, unit="m",
        status=MetricStatus.OK, confidence=geom_conf, method_trace=trace,
        flags=flags, required=required,
    ))
