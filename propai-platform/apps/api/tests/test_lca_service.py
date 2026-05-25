"""LCA 탄소 자동 계산 테스트 (ISO 14040, IPCC AR6)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.esg.lca_service import LCAService, IPCC_AR6_EMISSION_FACTORS


class TestA1A3Calculation:
    """A1-A3 자재 생산 단계 GWP 계산."""

    def setup_method(self):
        self.svc = LCAService()

    def test_single_material_gwp(self):
        """단일 자재 GWP = 수량 × 배출계수."""
        result = self.svc.calculate_a1_a3({"concrete_C25": 1000})
        expected_gwp = 1000 * 0.159  # concrete_C25 EF = 0.159
        assert result["total_gwp_kgco2e"] == pytest.approx(expected_gwp, rel=0.01)
        assert result["standard"] == "ISO 14040:2006"

    def test_multiple_materials(self, sample_materials):
        """다중 자재 GWP 합산."""
        result = self.svc.calculate_a1_a3(sample_materials)
        assert result["total_gwp_kgco2e"] > 0
        assert len(result["breakdown"]) == len(sample_materials)

    def test_unknown_material_uses_default_ef(self):
        """미등록 자재 → 기본 배출계수 0.5 적용."""
        result = self.svc.calculate_a1_a3({"unknown_material": 100})
        expected = 100 * 0.5
        assert result["total_gwp_kgco2e"] == pytest.approx(expected, rel=0.01)

    def test_emission_factor_ipcc_ar6(self):
        """IPCC AR6 배출계수 13개 자재 등록 확인."""
        assert len(IPCC_AR6_EMISSION_FACTORS) == 13
        assert "concrete_C25" in IPCC_AR6_EMISSION_FACTORS
        assert "steel_rebar" in IPCC_AR6_EMISSION_FACTORS

    def test_empty_materials_zero_gwp(self):
        """자재 없으면 GWP = 0."""
        result = self.svc.calculate_a1_a3({})
        assert result["total_gwp_kgco2e"] == 0.0


class TestB6OperationalEnergy:
    """B6 운영 에너지 GWP 계산."""

    def setup_method(self):
        self.svc = LCAService()

    def test_b6_calculation(self):
        """B6 GWP = 면적 × 에너지강도 × 배출계수 × 50년."""
        result = self.svc.calculate_b6_operational_energy(1000.0)
        annual_energy = 1000 * 120.0
        annual_gwp = annual_energy * 0.4781
        assert result["annual_energy_kwh"] == pytest.approx(annual_energy, rel=0.01)
        assert result["lifecycle_gwp_50yr_kgco2e"] == pytest.approx(annual_gwp * 50, rel=0.01)

    def test_korea_grid_emission_factor(self):
        """한국 전력 배출계수 0.4781 기본값."""
        result = self.svc.calculate_b6_operational_energy(100.0)
        assert result["grid_emission_factor_kgco2e_per_kwh"] == 0.4781


class TestTotalLCA:
    """전체 LCA 합산."""

    def setup_method(self):
        self.svc = LCAService()

    def test_total_lca_sum(self, sample_materials):
        """전체 LCA = A1-A3 + B6."""
        result = self.svc.calculate_total_lca(sample_materials, 5000.0)
        assert result["total_gwp_kgco2e"] > 0
        assert "a1_a3" in result
        assert "b6" in result
        assert result["ipcc_version"] == "AR6 2021"

    def test_gwp_per_sqm(self, sample_materials):
        """단위면적당 GWP 계산."""
        area = 5000.0
        result = self.svc.calculate_total_lca(sample_materials, area)
        expected_per_sqm = result["total_gwp_kgco2e"] / area
        assert result["gwp_per_sqm_kgco2e"] == pytest.approx(expected_per_sqm, rel=0.01)
