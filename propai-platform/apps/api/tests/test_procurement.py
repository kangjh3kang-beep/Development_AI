"""자재 조달 최적화 테스트 (EOQ + PPI)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.procurement_opt.procurement_optimizer import ProcurementOptimizer


class TestEOQ:
    """EOQ 경제적 주문량."""

    def setup_method(self):
        self.svc = ProcurementOptimizer()

    def test_eoq_formula(self):
        """EOQ = sqrt(2*D*S/H)."""
        result = self.svc.calculate_eoq(
            annual_demand=10000, order_cost_krw=500000,
        )
        assert result["optimal_order_quantity_eoq"] > 0
        assert result["formula"] == "EOQ = sqrt(2*D*S/H)"

    def test_eoq_increases_with_demand(self):
        """수요 증가 → EOQ 증가."""
        low = self.svc.calculate_eoq(annual_demand=1000, order_cost_krw=500000)
        high = self.svc.calculate_eoq(annual_demand=10000, order_cost_krw=500000)
        assert high["optimal_order_quantity_eoq"] > low["optimal_order_quantity_eoq"]

    def test_order_frequency(self):
        """발주 빈도 = 수요 / EOQ."""
        result = self.svc.calculate_eoq(
            annual_demand=10000, order_cost_krw=500000,
        )
        assert result["order_frequency_per_year"] > 0

    def test_order_cycle_days(self):
        """발주 주기 (일) = 365 / 빈도."""
        result = self.svc.calculate_eoq(
            annual_demand=10000, order_cost_krw=500000,
        )
        assert 0 < result["order_cycle_days"] <= 365


class TestPPIPrediction:
    """PPI 기반 발주 시점 예측."""

    def setup_method(self):
        self.svc = ProcurementOptimizer()

    def test_price_increase_recommend_immediate(self):
        """PPI 10%+ 상승 → 즉시 발주."""
        base = ProcurementOptimizer.PPI_BASE_INDEX["시멘트"]
        high_ppi = base * 1.15  # 15% 상승
        result = self.svc.predict_optimal_order_timing("시멘트", high_ppi)
        assert "즉시" in result["order_recommendation"]

    def test_price_decrease_recommend_delay(self):
        """PPI 5%+ 하락 → 발주 지연."""
        base = ProcurementOptimizer.PPI_BASE_INDEX["철근"]
        low_ppi = base * 0.90  # 10% 하락
        result = self.svc.predict_optimal_order_timing("철근", low_ppi)
        assert "후" in result["order_recommendation"]

    def test_stable_price_regular_order(self):
        """PPI 안정 → 정기 발주."""
        base = ProcurementOptimizer.PPI_BASE_INDEX["레미콘"]
        result = self.svc.predict_optimal_order_timing("레미콘", base)
        assert "정기" in result["order_recommendation"]

    def test_data_source_bank_of_korea(self):
        """데이터 출처: 한국은행 PPI."""
        result = self.svc.predict_optimal_order_timing("시멘트", 150.0)
        assert result["data_source"] == "한국은행 PPI"
