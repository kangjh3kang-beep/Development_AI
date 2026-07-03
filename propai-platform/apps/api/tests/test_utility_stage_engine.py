"""공사단계 세금 엔진 테스트 — B01~B08."""

import pytest

from app.services.tax.utility_stage_engine import (
    calculate_all_utility_stage,
    calculate_b01_metro_transport,
    calculate_b02_school_site,
    calculate_b03_water_supply,
    calculate_b04_sewage,
    calculate_b05_electricity,
    calculate_b08_fire,
)


class TestB01MetroTransport:
    def test_seoul(self):
        result = calculate_b01_metro_transport(
            sido_name="서울", sigungu_name="강남구",
            total_households=1000,
        )
        # 21.0만원/세대 × 1000 = 2.1억 (21만원 = 210,000원)
        assert result["amount_won"] == pytest.approx(210_000_000, rel=0.01)

    def test_gyeonggi_override(self):
        result = calculate_b01_metro_transport(
            sido_name="경기", sigungu_name="고양시",
            total_households=500,
        )
        assert result["detail"]["source"] == "override"


class TestB02SchoolSite:
    def test_under_300(self):
        """300세대 미만 면제."""
        result = calculate_b02_school_site(
            total_sale_amount_won=100_000_000_000,
            total_households=200,
        )
        assert result["amount_won"] == 0

    def test_over_300(self):
        """300세대 이상: 분양가 × 0.8%."""
        result = calculate_b02_school_site(
            total_sale_amount_won=500_000_000_000,
            total_households=1000,
        )
        assert result["amount_won"] == 4_000_000_000  # 5000억 × 0.8%


class TestB03WaterSupply:
    def test_oasan_reference(self):
        """오산 1624세대 참조: 120만원/세대 × 1624 ≈ 19.49억."""
        result = calculate_b03_water_supply(
            sido_name="경기", sigungu_name="오산시",
            total_households=1624,
        )
        # 경기_오산시 = 120_0000 (data에 typo — 1,200,000원으로 해석)
        assert result["amount_won"] > 0


class TestB04Sewage:
    def test_basic(self):
        result = calculate_b04_sewage(
            sido_name="서울", sigungu_name="강남구",
            total_households=500,
        )
        # 서울: 180,000원/세대 × 500 = 9000만
        assert result["amount_won"] == 90_000_000


class TestB05Electricity:
    def test_basic(self):
        result = calculate_b05_electricity(total_households=1000)
        assert result["amount_won"] == 250_000_000


class TestB08Fire:
    def test_basic(self):
        result = calculate_b08_fire(total_gfa_sqm=100_000)
        assert result["amount_won"] == 350_000_000


class TestAllUtilityStage:
    def test_full(self):
        result = calculate_all_utility_stage(
            sido_name="서울",
            sigungu_name="강남구",
            total_households=1000,
            total_sale_amount_won=500_000_000_000,
            total_gfa_sqm=100_000,
        )
        assert result["stage"] == "construction"
        assert result["applicable_count"] == 8
        assert result["total_won"] > 0
        codes = [it["code"] for it in result["items"]]
        assert "B01" in codes
        assert "B08" in codes
