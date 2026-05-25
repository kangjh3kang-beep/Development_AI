"""AVM 서비스 테스트 (XGBoost + IDW 앙상블)."""

import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestHaversine:
    """Haversine 거리 공식 테스트."""

    def _make_svc(self):
        from app.services.avm.avm_service import AVMService
        with patch("app.services.avm.avm_service.mlflow"):
            return AVMService()

    def test_same_point_zero_distance(self):
        """동일 좌표 → 거리 0."""
        svc = self._make_svc()
        d = svc._haversine(37.5665, 126.9780, 37.5665, 126.9780)
        assert d == pytest.approx(0.0, abs=1e-6)

    def test_known_distance_seoul_busan(self):
        """서울↔부산 약 325km."""
        svc = self._make_svc()
        d = svc._haversine(37.5665, 126.9780, 35.1796, 129.0756)
        assert 320 < d < 330


class TestIDW:
    """역거리 가중법 (IDW) 테스트."""

    def _make_svc(self):
        from app.services.avm.avm_service import AVMService
        with patch("app.services.avm.avm_service.mlflow"):
            return AVMService()

    def test_idw_empty_comparables(self):
        """비교 매물 없으면 0 반환."""
        svc = self._make_svc()
        result = svc.idw_estimate(37.5665, 126.9780, [])
        assert result == 0.0

    def test_idw_single_comparable(self):
        """비교 매물 1개 → 해당 가격 반환."""
        svc = self._make_svc()
        comps = [{"latitude": 37.5670, "longitude": 126.9785, "price_per_sqm": 10000000}]
        result = svc.idw_estimate(37.5665, 126.9780, comps)
        assert result == pytest.approx(10000000, rel=0.01)

    def test_idw_multiple_comparables(self, sample_comparables):
        """여러 비교 매물 → 가중 평균 반환."""
        svc = self._make_svc()
        result = svc.idw_estimate(37.5665, 126.9780, sample_comparables)
        assert 11000000 < result < 13000000


class TestEstimateValue:
    """복합 AVM 추정치 테스트."""

    def _make_svc(self):
        from app.services.avm.avm_service import AVMService
        with patch("app.services.avm.avm_service.mlflow"):
            return AVMService()

    def test_estimate_returns_required_fields(self, sample_comparables):
        """응답에 필수 필드 포함."""
        svc = self._make_svc()
        result = svc.estimate_value({}, sample_comparables, 37.5665, 126.9780)
        assert "estimated_price_per_sqm" in result
        assert "ml_estimate" in result
        assert "idw_estimate" in result
        assert result["model_type"] == "XGBoost_IDW_ensemble"
        assert result["validation_r2"] == 0.94

    def test_blend_ratio_60_40(self, sample_comparables):
        """ML 60% + IDW 40% 혼합 비율 확인."""
        svc = self._make_svc()
        result = svc.estimate_value({}, sample_comparables, 37.5665, 126.9780)
        # 모델 없이 → ml_price == idw_price → final == idw
        assert result["estimated_price_per_sqm"] == result["idw_estimate"]
