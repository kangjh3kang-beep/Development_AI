"""L3-B — 조망/스카이라인 시뮬. 가로 대비 입면 점유율/통경축 차폐율 정량화.

입면폭/가로폭은 입력. 비율 지표는 결정론. (정성 판단 아님 — 정량 공학 지표.)
"""
from __future__ import annotations

from app.contracts.sim_metric import MethodTrace, MetricStatus, SimMetric, emit
from app.core.confidence import clamp01

_BASIS = "경관법§9"  # 경관계획·경관심의(resolve_text 해소 가능 — legal_refs 등록). 정량 입면점유 지표의 법적 맥락


def run(streetscape: dict) -> SimMetric:
    geom_conf = float(streetscape.get("geom_confidence", 1.0))
    facade_width = streetscape.get("facade_width")
    street_width = streetscape.get("street_width")

    if not facade_width or not street_width:
        return SimMetric(
            metric_id="facade_occupancy_ratio", value=None, unit="ratio",
            status=MetricStatus.UNAVAILABLE, confidence=geom_conf,
            method_trace=MethodTrace(model="skyline_ratio", assumptions=["입면/가로폭 결손"], inputs={}),
            flags=["missing_dimensions"],
        )

    occupancy = clamp01(float(facade_width) / float(street_width))
    trace = MethodTrace(
        model="skyline_ratio",
        assumptions=[
            "입면폭/가로폭 단일 단면 비율 — 통경축 차폐율·시점 위치 미반영(docstring상 통경축 차폐는 별도 미산출)",
            "clamp01로 1.0 상한 절단(초과 점유는 1.0으로 포화)",
        ],
        inputs={"facade_width": facade_width, "street_width": street_width},
        basis_article=_BASIS,
    )
    return emit(SimMetric(
        metric_id="facade_occupancy_ratio", value=occupancy, unit="ratio",
        status=MetricStatus.OK, confidence=geom_conf, method_trace=trace,
    ))
