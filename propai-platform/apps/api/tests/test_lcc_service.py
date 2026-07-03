"""LCC 생애주기비용 분석 테스트 (ISO 15686-5)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.esg.lcc_service import LCCService


class TestLCCCalculation:
    """LCC 계산 테스트."""

    def setup_method(self):
        self.svc = LCCService()

    def test_basic_lcc(self):
        """기본 LCC 계산 필수 필드 확인."""
        result = self.svc.calculate_lcc(
            construction_cost_krw=50_000_000_000,
            annual_maintenance_krw=500_000_000,
            annual_energy_krw=300_000_000,
        )
        assert result["construction_cost_krw"] == 50_000_000_000
        assert result["total_lcc_krw"] > result["construction_cost_krw"]
        assert result["standard"] == "ISO 15686-5:2017"

    def test_real_discount_rate(self):
        """실질 할인율 = (1+명목)/(1+인플레) - 1."""
        result = self.svc.calculate_lcc(
            construction_cost_krw=10_000_000_000,
            annual_maintenance_krw=100_000_000,
            annual_energy_krw=50_000_000,
            discount_rate=0.05,
            inflation_rate=0.02,
        )
        expected_real_rate = (1.05 / 1.02) - 1
        assert result["real_discount_rate"] == pytest.approx(expected_real_rate, abs=0.001)

    def test_replacement_at_intervals(self):
        """15/25/35/45년 교체비용 포함."""
        result = self.svc.calculate_lcc(
            construction_cost_krw=10_000_000_000,
            annual_maintenance_krw=100_000_000,
            annual_energy_krw=50_000_000,
        )
        assert result["pv_replacement_krw"] > 0

    def test_zero_maintenance(self):
        """유지비 0이면 PV 유지비도 0."""
        result = self.svc.calculate_lcc(
            construction_cost_krw=10_000_000_000,
            annual_maintenance_krw=0,
            annual_energy_krw=50_000_000,
        )
        assert result["pv_maintenance_krw"] == 0

    def test_lifecycle_50_years_default(self):
        """기본 분석 기간 50년."""
        result = self.svc.calculate_lcc(
            construction_cost_krw=10_000_000_000,
            annual_maintenance_krw=100_000_000,
            annual_energy_krw=50_000_000,
        )
        assert result["lifecycle_years"] == 50
