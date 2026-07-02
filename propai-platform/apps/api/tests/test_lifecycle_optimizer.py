"""생애주기 최적화 테스트 (ISO 15686-1)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.lifecycle_opt.lifecycle_optimizer import LifecycleOptimizer


class TestReplacementSchedule:
    """교체 스케줄 최적화."""

    def setup_method(self):
        self.svc = LifecycleOptimizer()

    def test_10_components(self):
        """10개 구성요소 스케줄."""
        result = self.svc.optimize_replacement_schedule(50_000_000_000)
        assert len(result["replacement_schedule"]) == 10

    def test_replacement_years_within_lifespan(self):
        """교체 연도가 건물 수명 내."""
        result = self.svc.optimize_replacement_schedule(50_000_000_000, 50)
        for _comp, info in result["replacement_schedule"].items():
            for year in info["replacement_years"]:
                assert 0 < year < 50

    def test_pv_cost_decreases_over_time(self):
        """현가는 시간이 갈수록 감소."""
        result = self.svc.optimize_replacement_schedule(50_000_000_000, 50)
        roof = result["replacement_schedule"]["지붕방수"]
        if len(roof["pv_replacement_costs"]) >= 2:
            assert roof["pv_replacement_costs"][0]["pv_cost_krw"] > roof["pv_replacement_costs"][-1]["pv_cost_krw"]

    def test_total_pv_positive(self):
        """총 현가 > 0."""
        result = self.svc.optimize_replacement_schedule(50_000_000_000)
        assert result["total_pv_replacement_krw"] > 0

    def test_standard_iso_15686(self):
        """ISO 15686-1 표준."""
        result = self.svc.optimize_replacement_schedule(50_000_000_000)
        assert result["standard"] == "ISO 15686-1"

    def test_default_50_year_lifespan(self):
        """기본 건물 수명 50년."""
        result = self.svc.optimize_replacement_schedule(50_000_000_000)
        assert result["building_lifespan_years"] == 50
