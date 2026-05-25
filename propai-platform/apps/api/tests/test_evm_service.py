"""EVM 공정 관리 테스트 (PMBOK 7th)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.lifecycle.construction.supervision_service import SupervisionService


class TestEVMCalculation:
    """EVM 지표 계산."""

    def setup_method(self):
        self.svc = SupervisionService()

    def test_evm_basic(self):
        """기본 EVM 계산: EV = BAC × pct/100."""
        result = self.svc.calculate_evm(
            bac_krw=10_000_000_000, pv_krw=5_000_000_000,
            ev_pct=50, ac_krw=4_500_000_000,
        )
        assert result["ev_krw"] == 5_000_000_000
        assert result["method"] == "EVM (PMBOK 7th Edition)"

    def test_schedule_variance(self):
        """SV = EV - PV."""
        result = self.svc.calculate_evm(
            bac_krw=10_000_000_000, pv_krw=6_000_000_000,
            ev_pct=50, ac_krw=5_000_000_000,
        )
        assert result["sv_krw"] == -1_000_000_000  # 지연

    def test_cost_variance(self):
        """CV = EV - AC."""
        result = self.svc.calculate_evm(
            bac_krw=10_000_000_000, pv_krw=5_000_000_000,
            ev_pct=50, ac_krw=6_000_000_000,
        )
        assert result["cv_krw"] == -1_000_000_000  # 초과

    def test_cpi_spi(self):
        """CPI = EV/AC, SPI = EV/PV."""
        result = self.svc.calculate_evm(
            bac_krw=10_000_000_000, pv_krw=5_000_000_000,
            ev_pct=50, ac_krw=5_000_000_000,
        )
        assert result["cpi"] == pytest.approx(1.0, abs=0.01)
        assert result["spi"] == pytest.approx(1.0, abs=0.01)

    def test_on_schedule_status(self):
        """SPI ≈ 1.0 → 정상."""
        result = self.svc.calculate_evm(
            bac_krw=10_000_000_000, pv_krw=5_000_000_000,
            ev_pct=50, ac_krw=5_000_000_000,
        )
        assert result["schedule_status"] == "정상"

    def test_delayed_schedule_status(self):
        """SPI < 0.95 → 지연."""
        result = self.svc.calculate_evm(
            bac_krw=10_000_000_000, pv_krw=8_000_000_000,
            ev_pct=50, ac_krw=5_000_000_000,
        )
        assert result["schedule_status"] == "지연"

    def test_eac_calculation(self):
        """EAC = BAC / CPI."""
        result = self.svc.calculate_evm(
            bac_krw=10_000_000_000, pv_krw=5_000_000_000,
            ev_pct=50, ac_krw=6_000_000_000,
        )
        expected_cpi = 5_000_000_000 / 6_000_000_000
        expected_eac = 10_000_000_000 / expected_cpi
        assert result["eac_krw"] == pytest.approx(expected_eac, rel=0.01)
