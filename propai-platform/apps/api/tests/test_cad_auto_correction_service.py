"""CAD 파라메트릭 자동 보정 서비스 단위 테스트.

건축물 설계안의 법규 적합성 검증과 자동 보정 로직을 검증한다.
- 건폐율/용적률/높이 위반 감지
- 자동 보정 후 법규 적합 달성
- 보정 반복 횟수 및 보정 내역 기록
"""

import os
import sys

import pytest

# propai-platform 루트를 Python path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.cad_auto_correction_service import (
    BuildingModel,
    CadAutoCorrectionService,
    RegulationLimit,
)

# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _compliant_building() -> BuildingModel:
    """법규를 모두 충족하는 건물 모델."""
    return BuildingModel(
        site_area_sqm=1000.0,
        building_area_sqm=500.0,  # 건폐율 50%
        num_floors=3,  # 연면적 1500 → 용적률 150%
        floor_height_m=3.0,  # 높이 9m
    )


def _standard_regulation() -> RegulationLimit:
    """제1종일반주거지역 기준 (건폐율 60%, 용적률 200%, 높이 35m)."""
    return RegulationLimit(max_bcr=60.0, max_far=200.0, max_height_m=35.0)


# ──────────────────────────────────────────────
# 법규 적합성 검증 (check_compliance)
# ──────────────────────────────────────────────


class TestCheckCompliance:
    """CadAutoCorrectionService.check_compliance 검증."""

    def test_적합_건물_위반없음(self):
        """모든 기준을 충족하는 건물은 위반 0개."""
        building = _compliant_building()
        regulation = _standard_regulation()
        violations = CadAutoCorrectionService.check_compliance(building, regulation)
        assert len(violations) == 0

    def test_건폐율_초과_감지(self):
        """건폐율 초과 시 'bcr' 위반이 감지된다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=700.0,  # 건폐율 70% > 60%
            num_floors=1,
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        violations = CadAutoCorrectionService.check_compliance(building, regulation)
        bcr_v = [v for v in violations if v.item == "bcr"]
        assert len(bcr_v) == 1
        assert bcr_v[0].current_value == pytest.approx(70.0)
        assert bcr_v[0].excess == pytest.approx(10.0)

    def test_용적률_초과_감지(self):
        """용적률 초과 시 'far' 위반이 감지된다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=500.0,
            num_floors=5,  # 연면적 2500 → 용적률 250% > 200%
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        violations = CadAutoCorrectionService.check_compliance(building, regulation)
        far_v = [v for v in violations if v.item == "far"]
        assert len(far_v) == 1
        assert far_v[0].current_value == pytest.approx(250.0)
        assert far_v[0].excess == pytest.approx(50.0)

    def test_높이_초과_감지(self):
        """높이 초과 시 'height' 위반이 감지된다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=200.0,
            num_floors=13,  # 높이 39m > 35m
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        violations = CadAutoCorrectionService.check_compliance(building, regulation)
        h_v = [v for v in violations if v.item == "height"]
        assert len(h_v) == 1
        assert h_v[0].current_value == pytest.approx(39.0)
        assert h_v[0].excess == pytest.approx(4.0)

    def test_높이_제한_없음(self):
        """max_height_m=0이면 높이 제한을 적용하지 않는다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=200.0,
            num_floors=50,
            floor_height_m=3.5,  # 175m
        )
        regulation = RegulationLimit(max_bcr=60.0, max_far=1300.0, max_height_m=0)
        violations = CadAutoCorrectionService.check_compliance(building, regulation)
        h_v = [v for v in violations if v.item == "height"]
        assert len(h_v) == 0


# ──────────────────────────────────────────────
# 자동 보정 (auto_correct)
# ──────────────────────────────────────────────


class TestAutoCorrect:
    """CadAutoCorrectionService.auto_correct 검증."""

    def test_건폐율_자동보정(self):
        """건폐율 초과 시 건축면적이 축소된다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=800.0,  # 건폐율 80% > 60%
            num_floors=1,
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        # 보정 후 건축면적 = 60% * 1000 = 600
        assert result.corrected["building_area_sqm"] == pytest.approx(600.0)
        assert result.corrected["bcr"] <= 60.0

    def test_용적률_자동보정(self):
        """용적률 초과 시 층수가 감소한다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=500.0,
            num_floors=6,  # 용적률 300% > 200%
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert result.corrected["num_floors"] < 6
        assert result.corrected["far"] <= 200.0

    def test_높이_자동보정(self):
        """높이 초과 시 층수가 감소한다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=200.0,
            num_floors=15,  # 높이 45m > 35m
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert result.corrected["height_m"] <= 35.0
        assert result.corrected["num_floors"] <= 11  # 35/3=11.66 → 11층

    def test_복합위반_전부보정(self):
        """건폐율+용적률+높이 동시 위반 시 모두 보정된다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=800.0,  # 건폐율 80% > 60%
            num_floors=15,  # 높이 45m > 35m, 용적률 1200% > 200%
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert result.corrected["bcr"] <= 60.0
        assert result.corrected["far"] <= 200.0
        assert result.corrected["height_m"] <= 35.0

    def test_보정후_적합(self):
        """보정 후 is_compliant가 True여야 한다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=700.0,  # 건폐율 70%
            num_floors=5,  # 용적률 350%
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert result.is_compliant is True

    def test_보정_반복_횟수(self):
        """위반이 있을 때 iterations가 0보다 커야 한다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=700.0,
            num_floors=5,
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert result.iterations > 0

    def test_corrections_applied_기록(self):
        """보정 내역이 corrections_applied에 기록되어야 한다."""
        building = BuildingModel(
            site_area_sqm=1000.0,
            building_area_sqm=800.0,
            num_floors=1,
            floor_height_m=3.0,
        )
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert len(result.corrections_applied) > 0
        # 건폐율 보정 내역이 포함되어야 함
        assert any("건폐율" in c for c in result.corrections_applied)

    def test_최소_1층_보장(self):
        """보정 후에도 층수는 최소 1층이 보장되어야 한다."""
        building = BuildingModel(
            site_area_sqm=100.0,
            building_area_sqm=50.0,
            num_floors=50,  # 매우 높은 층수
            floor_height_m=3.0,
        )
        regulation = RegulationLimit(max_bcr=60.0, max_far=100.0, max_height_m=10.0)
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert result.corrected["num_floors"] >= 1

    def test_적합건물_보정_불필요(self):
        """이미 적합한 건물은 보정 없이 iterations=0이다."""
        building = _compliant_building()
        regulation = _standard_regulation()
        result = CadAutoCorrectionService.auto_correct(building, regulation)
        assert result.iterations == 0
        assert result.is_compliant is True
        assert len(result.corrections_applied) == 0


# ──────────────────────────────────────────────
# BuildingModel 속성 검증
# ──────────────────────────────────────────────


class TestBuildingModel:
    """BuildingModel의 계산 속성을 검증한다."""

    def test_gross_floor_area(self):
        """연면적 = 건축면적 * 층수."""
        b = BuildingModel(site_area_sqm=1000, building_area_sqm=300, num_floors=5, floor_height_m=3.0)
        assert b.gross_floor_area_sqm == pytest.approx(1500.0)

    def test_total_height(self):
        """건물 높이 = 층수 * 층고."""
        b = BuildingModel(site_area_sqm=1000, building_area_sqm=300, num_floors=10, floor_height_m=3.5)
        assert b.total_height_m == pytest.approx(35.0)

    def test_bcr_zero_site_area(self):
        """대지면적이 0이면 건폐율은 0.0."""
        b = BuildingModel(site_area_sqm=0, building_area_sqm=300, num_floors=1, floor_height_m=3.0)
        assert b.bcr == pytest.approx(0.0)

    def test_far_zero_site_area(self):
        """대지면적이 0이면 용적률은 0.0."""
        b = BuildingModel(site_area_sqm=0, building_area_sqm=300, num_floors=5, floor_height_m=3.0)
        assert b.far == pytest.approx(0.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
