"""탄소 배출량 산출 서비스 단위 테스트.

순수 로직 검증:
1. _calculate_embodied_carbon() — 자재별 탄소 배출 계수 적용
2. _estimate_operational_carbon() — 운영 단계 탄소 배출 추정
"""

from unittest.mock import AsyncMock

from apps.api.services.carbon_calculation_service import (
    _CARBON_FACTORS,
    CarbonCalculationService,
)


def _make_service() -> CarbonCalculationService:
    """Mock DB 세션으로 서비스 생성."""
    return CarbonCalculationService(AsyncMock())


# ──────────────────────────────────────
# _calculate_embodied_carbon 검증
# ──────────────────────────────────────


class TestEmbodiedCarbon:
    """내재 탄소 계산 검증."""

    def test_wall_volume_calculation(self) -> None:
        """IfcWall 120 kgCO2e/m³ 적용."""
        svc = _make_service()
        breakdown = [{"type": "IfcWall", "volume_m3": 100.0}]
        total, details = svc._calculate_embodied_carbon(breakdown)
        assert total == 100.0 * 120.0  # 12,000 kgCO2e
        assert len(details) == 1
        assert details[0]["element_type"] == "IfcWall"
        assert details[0]["carbon_kgco2e"] == 12_000.0

    def test_slab_volume_calculation(self) -> None:
        """IfcSlab 130 kgCO2e/m³ 적용."""
        svc = _make_service()
        breakdown = [{"type": "IfcSlab", "volume_m3": 50.0}]
        total, _ = svc._calculate_embodied_carbon(breakdown)
        assert total == 50.0 * 130.0

    def test_window_area_calculation(self) -> None:
        """IfcWindow는 면적(area_sqm) 기준 45 kgCO2e/m²."""
        svc = _make_service()
        breakdown = [{"type": "IfcWindow", "area_sqm": 20.0}]
        total, _ = svc._calculate_embodied_carbon(breakdown)
        assert total == 20.0 * 45.0

    def test_unknown_type_skipped(self) -> None:
        """미정의 자재 유형은 건너뜀."""
        svc = _make_service()
        breakdown = [{"type": "IfcUnknownElement", "volume_m3": 999.0}]
        total, details = svc._calculate_embodied_carbon(breakdown)
        assert total == 0.0
        assert len(details) == 0

    def test_empty_breakdown(self) -> None:
        """빈 자재 목록 → 0."""
        svc = _make_service()
        total, details = svc._calculate_embodied_carbon([])
        assert total == 0.0
        assert details == []

    def test_multiple_elements(self) -> None:
        """복합 자재 합산."""
        svc = _make_service()
        breakdown = [
            {"type": "IfcWall", "volume_m3": 100.0},
            {"type": "IfcSlab", "volume_m3": 50.0},
            {"type": "IfcWindow", "area_sqm": 20.0},
        ]
        total, details = svc._calculate_embodied_carbon(breakdown)
        expected = 100.0 * 120.0 + 50.0 * 130.0 + 20.0 * 45.0
        assert total == expected
        assert len(details) == 3

    def test_all_defined_factors(self) -> None:
        """정의된 모든 자재 유형에 탄소 계수가 있다."""
        assert len(_CARBON_FACTORS) == 8
        for _key, val in _CARBON_FACTORS.items():
            assert "factor" in val
            assert val["factor"] > 0

    def test_volume_preferred_over_area(self) -> None:
        """volume_m3와 area_sqm 모두 있으면 volume_m3 우선."""
        svc = _make_service()
        breakdown = [{"type": "IfcWall", "volume_m3": 10.0, "area_sqm": 999.0}]
        total, _ = svc._calculate_embodied_carbon(breakdown)
        # volume_m3가 0이 아니면 volume 사용
        assert total == 10.0 * 120.0


# ──────────────────────────────────────
# _estimate_operational_carbon 검증
# ──────────────────────────────────────


class TestOperationalCarbon:
    """운영 단계 탄소 배출 추정 검증."""

    def test_basic_calculation(self) -> None:
        """100㎡ × 120kWh × 0.46 × 60년."""
        svc = _make_service()
        result = svc._estimate_operational_carbon(100.0)
        expected = 100.0 * 120 * 0.46 * 60
        assert abs(result - expected) < 0.01

    def test_zero_area(self) -> None:
        """0㎡ → 0."""
        svc = _make_service()
        assert svc._estimate_operational_carbon(0.0) == 0.0

    def test_custom_lifespan(self) -> None:
        """lifespan_years=30 → 절반."""
        svc = _make_service()
        full = svc._estimate_operational_carbon(100.0, lifespan_years=60)
        half = svc._estimate_operational_carbon(100.0, lifespan_years=30)
        assert abs(half - full / 2) < 0.01

    def test_large_area(self) -> None:
        """대형 건물 (10,000㎡)도 정상 계산."""
        svc = _make_service()
        result = svc._estimate_operational_carbon(10_000.0)
        assert result > 0
        expected = 10_000.0 * 120 * 0.46 * 60
        assert abs(result - expected) < 0.01

    def test_proportional_to_area(self) -> None:
        """면적에 비례."""
        svc = _make_service()
        r1 = svc._estimate_operational_carbon(100.0)
        r2 = svc._estimate_operational_carbon(200.0)
        assert abs(r2 - r1 * 2) < 0.01
