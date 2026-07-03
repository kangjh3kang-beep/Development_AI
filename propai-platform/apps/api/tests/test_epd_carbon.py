"""EPD 탄소발자국 추적 테스트 (ISO 21930)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.esg.epd_carbon_service import EPD_KOREA_DATABASE, EPDCarbonService


class TestEPDDatabase:
    """EPD Korea 데이터베이스 검증."""

    def test_database_has_entries(self):
        """EPD 데이터베이스에 자재 등록 확인."""
        assert len(EPD_KOREA_DATABASE) > 10

    def test_clt_negative_carbon(self):
        """CLT 구조목은 탄소 흡수 (음수 GWP)."""
        clt = EPD_KOREA_DATABASE.get("CLT 구조목")
        assert clt is not None
        assert clt["epd_kgco2e"] < 0


class TestMaterialCarbon:
    """자재별 탄소발자국 계산."""

    def setup_method(self):
        self.svc = EPDCarbonService()

    def test_calculate_material_carbon(self, sample_epd_materials):
        """자재 탄소발자국 계산."""
        result = self.svc.calculate_material_carbon(sample_epd_materials)
        assert result["total_carbon_footprint_kgco2e"] > 0
        assert result["material_count"] == 3
        assert result["standard"] == "ISO 21930:2017"

    def test_unknown_material_skipped(self):
        """미등록 자재 → breakdown에 미포함."""
        result = self.svc.calculate_material_carbon([
            {"name": "존재하지않는자재", "quantity_kg": 1000}
        ])
        assert result["material_count"] == 0
        assert result["total_carbon_footprint_kgco2e"] == 0.0

    def test_carbon_formula_correct(self):
        """CF = 수량 × EPD 배출계수."""
        materials = [{"name": "일반 콘크리트 (C25)", "quantity_kg": 10000}]
        result = self.svc.calculate_material_carbon(materials)
        expected = 10000 * 0.159
        assert result["total_carbon_footprint_kgco2e"] == pytest.approx(expected, rel=0.01)


class TestLowCarbonAlternatives:
    """저탄소 대안 추천."""

    def setup_method(self):
        self.svc = EPDCarbonService()

    def test_recommend_alternatives(self):
        """일반 콘크리트 → 저탄소 콘크리트 추천."""
        result = self.svc.recommend_low_carbon_alternatives(
            "일반 콘크리트 (C25)", 500000
        )
        assert result["original_material"] == "일반 콘크리트 (C25)"
        assert len(result["alternatives"]) > 0

    def test_alternatives_have_positive_reduction(self):
        """대안은 양의 탄소 감소율."""
        result = self.svc.recommend_low_carbon_alternatives(
            "고강도 콘크리트 (C35)", 100000
        )
        for alt in result["alternatives"]:
            assert alt["carbon_reduction_pct"] > 0

    def test_max_3_alternatives(self):
        """최대 3개 대안."""
        result = self.svc.recommend_low_carbon_alternatives(
            "철근 (SD500)", 50000
        )
        assert len(result["alternatives"]) <= 3
