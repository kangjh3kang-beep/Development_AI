"""L3-B — 시뮬 오케스트레이션. 입력(LegalQuantity+SemanticElement+PreflightContext) → SimMetric[].

결정론 모델(LLM 미사용) → 동일 입력+스냅샷 동일 결과. method_trace 동반, 필수 결손 시 UNAVAILABLE.
"""
from __future__ import annotations

from app.contracts.sim_metric import SimMetric
from app.services.sim import egress, parking_flow, sunlight, view_skyline
from app.services.sim.sim_params import SimParamSource


class SimEngine:
    def __init__(self, params: dict | None = None) -> None:
        self.params = SimParamSource(overrides=params)

    def run_sunlight(self, site: dict, snapshot=None) -> SimMetric:
        return sunlight.run(site, self.params)

    def run_egress(self, plan: dict, snapshot=None) -> SimMetric:
        return egress.run(plan, self.params)

    def run_parking(self, parking: dict, snapshot=None) -> SimMetric:
        return parking_flow.run(parking, self.params)

    def run_view(self, streetscape: dict, snapshot=None) -> SimMetric:
        return view_skyline.run(streetscape)
