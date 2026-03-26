"""AuctionService 단위 테스트.

경매 투자 분석 스냅샷(점수 산정, 권장 입찰가, 마진 계산) 등
순수 정적 메서드를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.auction_service import AuctionService


class TestAnalysisSnapshot:
    """_analysis_snapshot 정적 메서드 테스트."""

    def _base_params(self, **overrides) -> dict:
        defaults = {
            "appraised_value_krw": 1_000_000_000,
            "minimum_bid_krw": 700_000_000,
            "bid_count": 0,
            "occupancy_status": "vacant",
            "senior_lien_exists": False,
            "expected_repair_cost_krw": 0,
            "nearby_market_price_krw": None,
        }
        defaults.update(overrides)
        return defaults

    def test_할인율_계산(self):
        """최저가 7억 / 감정가 10억 → 할인율 0.3."""
        result = AuctionService._analysis_snapshot(**self._base_params())
        assert result["discount_ratio"] == pytest.approx(0.3, abs=0.001)

    def test_시장갭비율_nearby없으면_감정가_사용(self):
        result = AuctionService._analysis_snapshot(**self._base_params())
        assert result["market_gap_ratio"] == pytest.approx(0.3, abs=0.001)

    def test_시장갭비율_nearby있으면_시장가_사용(self):
        result = AuctionService._analysis_snapshot(
            **self._base_params(nearby_market_price_krw=1_200_000_000)
        )
        # 1 - (700M / 1200M) ≈ 0.4167
        assert result["market_gap_ratio"] == pytest.approx(0.4167, abs=0.01)

    def test_투자점수_기본값_범위(self):
        result = AuctionService._analysis_snapshot(**self._base_params())
        assert 0 <= result["investment_score"] <= 100

    def test_공실_보너스_5점(self):
        """vacant → +5점."""
        vacant = AuctionService._analysis_snapshot(**self._base_params(occupancy_status="vacant"))
        unknown = AuctionService._analysis_snapshot(**self._base_params(occupancy_status="unknown"))
        assert vacant["investment_score"] > unknown["investment_score"]

    def test_점유중_감점(self):
        """occupied → -10점."""
        vacant = AuctionService._analysis_snapshot(**self._base_params(occupancy_status="vacant"))
        occupied = AuctionService._analysis_snapshot(**self._base_params(occupancy_status="occupied"))
        assert vacant["investment_score"] - occupied["investment_score"] == pytest.approx(15, abs=1)

    def test_선순위_근저당_감점_15점(self):
        no_lien = AuctionService._analysis_snapshot(**self._base_params(senior_lien_exists=False))
        with_lien = AuctionService._analysis_snapshot(**self._base_params(senior_lien_exists=True))
        assert no_lien["investment_score"] - with_lien["investment_score"] == pytest.approx(15, abs=0.1)

    def test_입찰자_많으면_감점(self):
        zero_bids = AuctionService._analysis_snapshot(**self._base_params(bid_count=0))
        many_bids = AuctionService._analysis_snapshot(**self._base_params(bid_count=6))
        assert zero_bids["investment_score"] > many_bids["investment_score"]

    def test_수리비_높으면_감점(self):
        no_repair = AuctionService._analysis_snapshot(**self._base_params(expected_repair_cost_krw=0))
        expensive = AuctionService._analysis_snapshot(
            **self._base_params(expected_repair_cost_krw=100_000_000)
        )
        assert no_repair["investment_score"] > expensive["investment_score"]

    def test_권장최대입찰가_양수(self):
        result = AuctionService._analysis_snapshot(**self._base_params())
        assert result["recommended_max_bid_krw"] > 0

    def test_권장최대입찰가_최저가_이상(self):
        result = AuctionService._analysis_snapshot(**self._base_params())
        assert result["recommended_max_bid_krw"] >= 700_000_000

    def test_예상마진_양수(self):
        result = AuctionService._analysis_snapshot(**self._base_params())
        assert result["expected_margin_krw"] >= 0

    def test_due_diligence_플래그_선순위근저당(self):
        result = AuctionService._analysis_snapshot(**self._base_params(senior_lien_exists=True))
        assert "review senior lien exposure" in result["diligence_flags"]

    def test_due_diligence_플래그_점유상태(self):
        result = AuctionService._analysis_snapshot(**self._base_params(occupancy_status="occupied"))
        assert "confirm vacancy and handover timing" in result["diligence_flags"]

    def test_due_diligence_플래그_수리비_5퍼(self):
        """수리비 > 감정가 5% → 플래그."""
        result = AuctionService._analysis_snapshot(
            **self._base_params(expected_repair_cost_krw=60_000_000)
        )
        assert "validate repair capex before bid" in result["diligence_flags"]

    def test_due_diligence_플래그_경쟁과열(self):
        result = AuctionService._analysis_snapshot(**self._base_params(bid_count=3))
        assert "competition is elevated" in result["diligence_flags"]

    def test_due_diligence_기본_플래그(self):
        """이슈 없을 때 기본 플래그."""
        result = AuctionService._analysis_snapshot(**self._base_params())
        assert "standard legal and title diligence" in result["diligence_flags"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
