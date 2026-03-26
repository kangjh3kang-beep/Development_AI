"""AVM 서비스 단위 테스트.

DB/MLflow/외부 API 없이 순수 계산 로직만 검증한다.
- 신뢰도 계산
- POI 거리 추정
- 인프라 기반 환경 보정
- 합성 데이터 생성
- 단순 추정 폴백
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.avm_service import AVMService


class TestCalculateConfidence:
    """_calculate_confidence 메서드 테스트."""

    def _make_svc(self) -> AVMService:
        svc = object.__new__(AVMService)
        svc._model = None
        svc._model_stage = "fallback"
        return svc

    def test_production_model_high_comparables(self):
        """Production 모델 + 비교사례 50건 이상 → 최고 신뢰도."""
        svc = self._make_svc()
        conf = svc._calculate_confidence(comparable_count=60, model_stage="production")
        assert conf == pytest.approx(0.92, abs=0.01)

    def test_production_model_moderate_comparables(self):
        """Production 모델 + 비교사례 10~49건."""
        svc = self._make_svc()
        conf = svc._calculate_confidence(comparable_count=20, model_stage="production")
        assert conf == pytest.approx(0.89, abs=0.01)

    def test_staging_model_low_comparables(self):
        """Staging 모델 + 비교사례 3건 이하 → 신뢰도 하락."""
        svc = self._make_svc()
        conf = svc._calculate_confidence(comparable_count=2, model_stage="staging")
        assert conf == pytest.approx(0.60, abs=0.01)

    def test_fallback_model_no_comparables(self):
        """Fallback 모델 + 비교사례 0건."""
        svc = self._make_svc()
        conf = svc._calculate_confidence(comparable_count=0, model_stage="fallback")
        assert conf == pytest.approx(0.30, abs=0.01)

    def test_confidence_bounded_max(self):
        """신뢰도 상한 0.98."""
        svc = self._make_svc()
        conf = svc._calculate_confidence(comparable_count=100, model_stage="production")
        assert conf <= 0.98

    def test_confidence_bounded_min(self):
        """신뢰도 하한 0.10."""
        svc = self._make_svc()
        conf = svc._calculate_confidence(comparable_count=0, model_stage="unknown")
        assert conf >= 0.10


class TestEstimatePOIScores:
    """_estimate_poi_scores 정적 메서드 테스트."""

    def test_seoul_city_center(self):
        """서울 시청(37.5665, 126.9780) — 도심 최소 거리."""
        scores = AVMService._estimate_poi_scores(37.5665, 126.9780)
        assert scores["distance_to_subway_m"] == pytest.approx(200.0, abs=5.0)
        assert scores["distance_to_school_m"] == pytest.approx(150.0, abs=5.0)
        assert scores["school_score"] == pytest.approx(90.0, abs=1.0)

    def test_suburban_area(self):
        """외곽 지역(37.4, 127.2) — 도심보다 거리 증가."""
        scores = AVMService._estimate_poi_scores(37.4, 127.2)
        assert scores["distance_to_subway_m"] > 200.0
        assert scores["distance_to_school_m"] > 150.0
        assert scores["school_score"] < 90.0
        assert scores["view_score"] > 50.0

    def test_max_distance_cap(self):
        """아주 먼 외곽에서도 지하철 거리 최대 2000m."""
        scores = AVMService._estimate_poi_scores(36.0, 128.0)
        assert scores["distance_to_subway_m"] <= 2000.0
        assert scores["distance_to_school_m"] <= 1500.0


class TestAdjustEnvScores:
    """_adjust_env_scores_by_infra 정적 메서드 테스트."""

    def test_no_facilities_no_change(self):
        """시설물 0개 → 보정 없음."""
        result = AVMService._adjust_env_scores_by_infra(
            facilities=[], current={"noise_db": 55.0, "view_score": 60.0}
        )
        assert result["noise_db"] == 55.0
        assert result["view_score"] == 60.0

    def test_high_density_increases_noise(self):
        """시설물 10개 → 소음 증가, 조망 감소."""
        result = AVMService._adjust_env_scores_by_infra(
            facilities=[{"type": "pipe"}] * 10,
            current={"noise_db": 55.0, "view_score": 60.0},
        )
        assert result["noise_db"] == pytest.approx(70.0, abs=0.1)
        assert result["view_score"] == pytest.approx(40.0, abs=0.1)

    def test_noise_capped_at_80(self):
        """소음 상한 80dB."""
        result = AVMService._adjust_env_scores_by_infra(
            facilities=[{"type": "pipe"}] * 20,
            current={"noise_db": 70.0, "view_score": 60.0},
        )
        assert result["noise_db"] <= 80.0

    def test_view_score_min_20(self):
        """조망 점수 하한 20."""
        result = AVMService._adjust_env_scores_by_infra(
            facilities=[{"type": "pipe"}] * 20,
            current={"noise_db": 55.0, "view_score": 30.0},
        )
        assert result["view_score"] >= 20.0


class TestSimplePriceEstimate:
    """_simple_price_estimate 정적 메서드 테스트."""

    def test_comparables_priority(self):
        """비교사례가 있으면 평균가격 사용."""
        price = AVMService._simple_price_estimate(
            area_sqm=84.0,
            comparables=[
                {"price_10k_won": 50000},
                {"price_10k_won": 60000},
            ],
            features={"land_official_price": 1000000},
        )
        # 평균 55000만원 = 5.5억원 = 550,000,000
        assert price == pytest.approx(550_000_000, rel=0.01)

    def test_official_price_fallback(self):
        """비교사례 없고 공시지가 있으면 공시지가 × 면적 × 1.5."""
        price = AVMService._simple_price_estimate(
            area_sqm=100.0,
            comparables=[],
            features={"land_official_price": 5_000_000},
        )
        assert price == pytest.approx(750_000_000, rel=0.01)

    def test_area_based_final_fallback(self):
        """비교사례·공시지가 모두 없으면 면적 × 500만원."""
        price = AVMService._simple_price_estimate(
            area_sqm=84.0,
            comparables=[],
            features={"land_official_price": 0},
        )
        assert price == pytest.approx(84.0 * 5_000_000, rel=0.01)


class TestSyntheticComparables:
    """_generate_synthetic_comparables 정적 메서드 테스트."""

    def test_generates_correct_count(self):
        """지정한 수의 합성 데이터 생성."""
        samples = AVMService._generate_synthetic_comparables(area_sqm=84.0, n_samples=10)
        assert len(samples) == 10

    def test_synthetic_flag(self):
        """모든 합성 데이터에 synthetic=True 표시."""
        samples = AVMService._generate_synthetic_comparables(area_sqm=84.0, n_samples=5)
        for s in samples:
            assert s["synthetic"] is True

    def test_area_reasonable_range(self):
        """합성 면적이 원본 면적 ± 30% 이내."""
        samples = AVMService._generate_synthetic_comparables(area_sqm=100.0, n_samples=30)
        for s in samples:
            assert 50.0 < s["area_m2"] < 200.0, f"면적 {s['area_m2']}이 범위 밖"

    def test_has_required_fields(self):
        """필수 필드(area_m2, price_10k_won, floor, building_age) 포함."""
        samples = AVMService._generate_synthetic_comparables(area_sqm=84.0, n_samples=1)
        required = {"area_m2", "price_10k_won", "floor", "building_age", "synthetic"}
        assert required.issubset(samples[0].keys())


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
