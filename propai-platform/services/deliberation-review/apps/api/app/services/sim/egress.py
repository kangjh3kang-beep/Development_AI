"""L3-B — 피난 시뮬(SFPE 계열). 거실→직통계단 보행거리/피난시간. 보행속도/유동계수는 param.

직통계단(CORE_STAIR) 미식별 → status=UNAVAILABLE(무음 추정 금지, INV-21).
"""
from __future__ import annotations

from app.contracts.sim_metric import MethodTrace, MetricStatus, SimMetric, emit
from app.services.sim.sim_params import SimParamSource

_BASIS = "건축법 시행령(피난 보행거리 한도 참고) — 보행시간은 비법정 근사(SFPE 유동모델 아님)"


def _has_core_stair(elements: list) -> bool:
    return any(str(getattr(e, "value", e)) == "CORE_STAIR" for e in elements)


def run(plan: dict, params: SimParamSource) -> SimMetric:
    geom_conf = float(plan.get("geom_confidence", 1.0))
    elements = plan.get("elements", [])

    if not _has_core_stair(elements):
        return SimMetric(
            metric_id="egress_time", value=None, unit="s",
            status=MetricStatus.UNAVAILABLE, confidence=geom_conf,
            method_trace=MethodTrace(model="walking_time_approx", assumptions=["직통계단 필요"], inputs={}),
            flags=["missing_core_stair"],
        )

    if plan.get("travel_distance") is None:
        # 보행거리 결손 — 크래시/추정 금지, 확인 불가로 표면화(INV-21).
        return SimMetric(
            metric_id="egress_time", value=None, unit="s",
            status=MetricStatus.UNAVAILABLE, confidence=geom_conf,
            method_trace=MethodTrace(model="walking_time_approx", assumptions=["보행거리 입력 결손"], inputs={}),
            flags=["missing_travel_distance"],
        )

    travel_distance = float(plan["travel_distance"])
    walk_speed = params.get("egress_walk_speed_mps")
    flow = params.get("egress_flow_coefficient")
    if walk_speed <= 0 or flow <= 0:
        # 피난 파라미터 비양수(오주입) — 0division(500)/음수시간 무음 오판 차단, 확인불가로 표면화(INV-21).
        return SimMetric(
            metric_id="egress_time", value=None, unit="s",
            status=MetricStatus.UNAVAILABLE, confidence=geom_conf,
            method_trace=MethodTrace(
                model="walking_time_approx",
                assumptions=[f"피난 파라미터 비양수(walk_speed={walk_speed}, flow={flow}) — 계산 불가"], inputs={}),
            flags=["invalid_egress_params"],
        )
    egress_time = (travel_distance / walk_speed) * flow

    required = params.get("egress_max_travel_distance_m")
    flags = ["travel_distance_exceeded"] if travel_distance > required else []

    trace = MethodTrace(
        model="walking_time_approx",
        assumptions=[
            "⚠️ SFPE 유동모델(재실인원·유효폭·비유동 persons/m/s) 미구현 — 보행거리÷속도 근사. "
            "flow_coefficient는 병목 보정 배수일 뿐 대기·합류 미반영(엄밀 SFPE 아님)",
            "보행거리 한도는 기저값(시행령 §34) 적용 — 주요구조부 내화/불연 50m·공동주택 16층↑ 75m 조건 "
            "미반영(보수적, 실제 한도 상향 가능 — 거짓 부적합 주의)",
            f"walk_speed={walk_speed}", f"flow_coefficient={flow}",
        ],
        inputs={"travel_distance": travel_distance},
        basis_article=_BASIS,
    )
    return emit(SimMetric(
        metric_id="egress_time", value=egress_time, unit="s",
        status=MetricStatus.OK, confidence=geom_conf, method_trace=trace,
        flags=flags, required=required,
    ))
