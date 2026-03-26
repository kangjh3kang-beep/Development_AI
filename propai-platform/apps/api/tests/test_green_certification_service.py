"""녹색건축 인증 자동 평가 서비스 단위 테스트.

T3-3: G-SEED, ZEB, LEED 인증 등급 예측 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.green_certification_service import (
    BuildingGreenData,
    GreenCertificationService,
)


def _make_data(**overrides) -> BuildingGreenData:
    """테스트용 BuildingGreenData를 생성한다."""
    defaults = {
        "energy_independence_rate": 0.5,
        "primary_energy_demand_kwh_m2": 100,
        "renewable_energy_ratio": 0.3,
        "co2_reduction_rate": 0.3,
        "green_material_ratio": 0.5,
        "indoor_air_quality_score": 70,
        "water_saving_rate": 0.5,
        "waste_recycling_rate": 0.5,
        "public_transit_score": 7.0,
        "site_greenery_ratio": 0.4,
        "has_bems": True,
        "has_ev_charging": True,
    }
    defaults.update(overrides)
    return BuildingGreenData(**defaults)


# ──────────────────────────────────────────────
# G-SEED 평가
# ──────────────────────────────────────────────


class TestGSEED:
    """G-SEED 등급 평가를 검증한다."""

    def test_gseed_최우수(self):
        """높은 점수는 최우수 (그린1등급)을 받는다."""
        data = _make_data(
            energy_independence_rate=1.0,
            renewable_energy_ratio=1.0,
            green_material_ratio=1.0,
            indoor_air_quality_score=100,
            water_saving_rate=1.0,
            waste_recycling_rate=1.0,
            public_transit_score=10.0,
            site_greenery_ratio=1.0,
            has_bems=True,
            has_ev_charging=True,
        )
        result = GreenCertificationService.evaluate_gseed(data)
        assert result["grade"] == "최우수 (그린1등급)"
        assert result["score"] >= 74

    def test_gseed_미인증(self):
        """낮은 점수는 미인증이다."""
        data = _make_data(
            energy_independence_rate=0.0,
            renewable_energy_ratio=0.0,
            green_material_ratio=0.0,
            indoor_air_quality_score=0,
            water_saving_rate=0.0,
            waste_recycling_rate=0.0,
            public_transit_score=0.0,
            site_greenery_ratio=0.0,
            has_bems=False,
            has_ev_charging=False,
        )
        result = GreenCertificationService.evaluate_gseed(data)
        assert result["grade"] == "미인증"
        assert result["score"] < 50

    def test_gseed_점수_범위_0_100(self):
        """G-SEED 점수는 0~100 범위 내에 있어야 한다."""
        data = _make_data()
        result = GreenCertificationService.evaluate_gseed(data)
        assert 0 <= result["score"] <= 100

    def test_gseed_breakdown_7분야(self):
        """breakdown에 7개 평가 분야가 포함되어야 한다."""
        data = _make_data()
        result = GreenCertificationService.evaluate_gseed(data)
        expected_fields = {"에너지", "교통", "토지이용", "재료자원", "물환경", "유지관리", "실내환경"}
        assert set(result["breakdown"].keys()) == expected_fields


# ──────────────────────────────────────────────
# ZEB 평가
# ──────────────────────────────────────────────


class TestZEB:
    """ZEB 등급 평가를 검증한다."""

    def test_zeb_1등급(self):
        """에너지 자립률 100%는 ZEB 1등급이다."""
        data = _make_data(energy_independence_rate=1.0)
        result = GreenCertificationService.evaluate_zeb(data)
        assert result["grade"] == "ZEB 1등급"

    def test_zeb_5등급(self):
        """에너지 자립률 20%는 ZEB 5등급이다."""
        data = _make_data(energy_independence_rate=0.2)
        result = GreenCertificationService.evaluate_zeb(data)
        assert result["grade"] == "ZEB 5등급"

    def test_zeb_미인증(self):
        """에너지 자립률 10%는 미인증이다."""
        data = _make_data(energy_independence_rate=0.1)
        result = GreenCertificationService.evaluate_zeb(data)
        assert result["grade"] == "미인증"

    def test_에너지자립률_0(self):
        """에너지 자립률 0%는 미인증이다."""
        data = _make_data(energy_independence_rate=0.0)
        result = GreenCertificationService.evaluate_zeb(data)
        assert result["grade"] == "미인증"
        assert result["energy_independence_rate"] == 0.0


# ──────────────────────────────────────────────
# LEED 평가
# ──────────────────────────────────────────────


class TestLEED:
    """LEED 등급 평가를 검증한다."""

    def test_leed_platinum(self):
        """높은 점수는 Platinum 등급이다."""
        data = _make_data(
            energy_independence_rate=1.0,
            renewable_energy_ratio=1.0,
            green_material_ratio=1.0,
            indoor_air_quality_score=100,
            water_saving_rate=1.0,
            waste_recycling_rate=1.0,
            public_transit_score=10.0,
            site_greenery_ratio=1.0,
            has_bems=True,
            has_ev_charging=True,
        )
        result = GreenCertificationService.evaluate_leed(data)
        assert result["grade"] == "Platinum"
        assert result["score"] >= 80

    def test_leed_certified(self):
        """중간 점수는 Certified 이상이어야 한다."""
        data = _make_data(
            energy_independence_rate=0.5,
            renewable_energy_ratio=0.5,
            green_material_ratio=0.5,
            indoor_air_quality_score=60,
            water_saving_rate=0.5,
            waste_recycling_rate=0.5,
            public_transit_score=6.0,
            site_greenery_ratio=0.4,
            has_bems=False,
            has_ev_charging=False,
        )
        result = GreenCertificationService.evaluate_leed(data)
        assert result["score"] >= 40
        assert result["grade"] in ("Certified", "Silver", "Gold", "Platinum")

    def test_leed_미인증(self):
        """낮은 점수는 미인증이다."""
        data = _make_data(
            energy_independence_rate=0.0,
            renewable_energy_ratio=0.0,
            green_material_ratio=0.0,
            indoor_air_quality_score=0,
            water_saving_rate=0.0,
            waste_recycling_rate=0.0,
            public_transit_score=0.0,
            site_greenery_ratio=0.0,
            has_bems=False,
            has_ev_charging=False,
        )
        result = GreenCertificationService.evaluate_leed(data)
        assert result["grade"] == "미인증"
        assert result["score"] < 40


# ──────────────────────────────────────────────
# 전체 평가
# ──────────────────────────────────────────────


class TestEvaluateAll:
    """전체 인증 평가를 검증한다."""

    def test_evaluate_all_3개_인증(self):
        """evaluate_all은 gseed, zeb, leed 3개 키를 반환한다."""
        data = _make_data()
        result = GreenCertificationService.evaluate_all(data)
        assert "gseed" in result
        assert "zeb" in result
        assert "leed" in result
        assert "grade" in result["gseed"]
        assert "grade" in result["zeb"]
        assert "grade" in result["leed"]
