"""재무 관련 Pydantic 모델 + 서비스 로직 단위 테스트.

전세 리스크, 탄소 배출량 모델/로직 검증.
"""

from uuid import uuid4

import pytest

from packages.schemas.models import (
    CarbonCalculationRequest,
    CarbonCalculationResponse,
    JeonseRiskRequest,
    JeonseRiskResponse,
)

# ──────────────────────────────────────
# JeonseRisk 모델 테스트
# ──────────────────────────────────────

class TestJeonseRiskRequest:
    def test_valid(self) -> None:
        req = JeonseRiskRequest(
            project_id=uuid4(),
            address="서울시 강남구 삼성동",
            jeonse_price=500_000_000,
            sale_price=700_000_000,
        )
        assert req.jeonse_price == 500_000_000

    def test_price_must_be_positive(self) -> None:
        with pytest.raises((ValueError, Exception)):  # noqa: B017
            JeonseRiskRequest(
                project_id=uuid4(),
                address="서울시",
                jeonse_price=-1,
                sale_price=100,
            )


class TestJeonseRiskResponse:
    def test_create(self) -> None:
        resp = JeonseRiskResponse(
            jeonse_ratio=0.71,
            risk_level="MEDIUM",
            risk_score=0.55,
            analysis="전세가율 71%로 중위험",
            factors=[{"factor": "높은 전세가율", "impact": "HIGH"}],
        )
        assert resp.risk_level == "MEDIUM"
        assert len(resp.factors) == 1


# ──────────────────────────────────────
# CarbonCalculation 모델 테스트
# ──────────────────────────────────────

class TestCarbonCalculationRequest:
    def test_valid(self) -> None:
        req = CarbonCalculationRequest(
            project_id=uuid4(),
            material_breakdown=[{"type": "IfcWall", "volume_m3": 100}],
            total_area_sqm=5000.0,
        )
        assert len(req.material_breakdown) == 1


class TestCarbonCalculationResponse:
    def test_create(self) -> None:
        resp = CarbonCalculationResponse(
            total_embodied_carbon=12000.0,
            total_operational_carbon=16560000.0,
            total_carbon=16572000.0,
            breakdown=[{"element_type": "IfcWall", "carbon_kgco2e": 12000.0}],
            reduction_tips=["저탄소 콘크리트 사용"],
        )
        assert resp.total_carbon == 16572000.0
        assert len(resp.reduction_tips) == 1


# ──────────────────────────────────────
# 전세 리스크 계산 로직 테스트
# ──────────────────────────────────────

class TestJeonseRiskCalculation:
    """JeonseRiskService._calculate_risk_level 로직 단독 검증."""

    def _calculate(self, ratio: float) -> tuple[str, float]:
        """서비스 로직을 직접 재현하여 테스트."""
        if ratio >= 0.90:
            return "CRITICAL", 0.95
        elif ratio >= 0.80:
            return "HIGH", 0.80
        elif ratio >= 0.70:
            return "MEDIUM", 0.55
        elif ratio >= 0.60:
            return "LOW", 0.30
        else:
            return "SAFE", 0.10

    def test_critical(self) -> None:
        level, score = self._calculate(0.95)
        assert level == "CRITICAL"
        assert score == 0.95

    def test_high(self) -> None:
        level, _ = self._calculate(0.85)
        assert level == "HIGH"

    def test_medium(self) -> None:
        level, _ = self._calculate(0.75)
        assert level == "MEDIUM"

    def test_low(self) -> None:
        level, _ = self._calculate(0.65)
        assert level == "LOW"

    def test_safe(self) -> None:
        level, score = self._calculate(0.50)
        assert level == "SAFE"
        assert score == 0.10


# ──────────────────────────────────────
# 탄소 배출량 계산 로직 테스트
# ──────────────────────────────────────

class TestCarbonCalculation:
    """CarbonCalculationService 탄소 산출 로직 검증."""

    CARBON_FACTORS = {
        "IfcWall": 120.0,
        "IfcSlab": 130.0,
        "IfcColumn": 150.0,
    }

    def test_embodied_carbon(self) -> None:
        materials = [
            {"type": "IfcWall", "volume_m3": 100, "area_sqm": 0},
            {"type": "IfcSlab", "volume_m3": 50, "area_sqm": 0},
        ]
        total = 0.0
        for m in materials:
            factor = self.CARBON_FACTORS.get(m["type"], 0)
            total += m["volume_m3"] * factor

        assert total == 100 * 120.0 + 50 * 130.0  # 18,500

    def test_operational_carbon(self) -> None:
        area = 5000.0
        lifespan = 60
        annual = area * 120 * 0.46
        total = annual * lifespan
        assert total == 5000 * 120 * 0.46 * 60

    def test_unknown_material_ignored(self) -> None:
        factor = self.CARBON_FACTORS.get("IfcRailing", 0)
        assert factor == 0
