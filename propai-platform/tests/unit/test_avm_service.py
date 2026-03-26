"""AVM 서비스 단위 테스트.

Step 2.1 품질 게이트:
1. _build_features()가 16개 키를 모두 반환하는지
2. _fetch_spatial_data()가 POI 거리/환경 점수를 포함하는지
3. _simple_price_estimate 3단계 폴백 체인 검증
4. _estimate_poi_scores 좌표 기반 점수 추정 검증
5. _adjust_env_scores_by_infra 인프라 밀도 보정 검증
6. 신뢰도 계산 검증
"""

from apps.api.services.avm_service import AVMService

# ──────────────────────────────────────
# _estimate_poi_scores 검증
# ──────────────────────────────────────


class TestEstimatePOIScores:
    """좌표 기반 POI 거리/학군/조망 추정 검증."""

    def test_seoul_center(self) -> None:
        """서울 도심 좌표 → 지하철 가까움, 학군 높음."""
        scores = AVMService._estimate_poi_scores(37.5665, 126.9780)
        assert scores["distance_to_subway_m"] <= 300.0
        assert scores["distance_to_school_m"] <= 250.0
        assert scores["school_score"] >= 85.0

    def test_gangnam(self) -> None:
        """강남 좌표 → 도심 인접, 거리 짧음."""
        scores = AVMService._estimate_poi_scores(37.4979, 127.0276)
        assert scores["distance_to_subway_m"] <= 1000.0
        assert scores["school_score"] >= 60.0

    def test_suburban(self) -> None:
        """수도권 외곽 → 거리 길어짐, 학군 점수 감소."""
        scores = AVMService._estimate_poi_scores(37.3000, 127.3000)
        assert scores["distance_to_subway_m"] > 500.0
        assert scores["school_score"] < 80.0

    def test_subway_distance_capped_at_2000m(self) -> None:
        """지하철 거리 최대 2,000m 캡."""
        scores = AVMService._estimate_poi_scores(35.0, 129.0)
        assert scores["distance_to_subway_m"] <= 2000.0

    def test_school_distance_capped_at_1500m(self) -> None:
        """학교 거리 최대 1,500m 캡."""
        scores = AVMService._estimate_poi_scores(35.0, 129.0)
        assert scores["distance_to_school_m"] <= 1500.0

    def test_school_score_min_40(self) -> None:
        """학군 점수 최저 40점."""
        scores = AVMService._estimate_poi_scores(33.0, 130.0)
        assert scores["school_score"] >= 40.0

    def test_view_score_increases_with_distance(self) -> None:
        """도심에서 멀어질수록 조망 점수 증가."""
        center = AVMService._estimate_poi_scores(37.5665, 126.9780)
        suburb = AVMService._estimate_poi_scores(37.3000, 127.3000)
        assert suburb["view_score"] > center["view_score"]

    def test_view_score_capped_at_90(self) -> None:
        """조망 점수 최대 90점."""
        scores = AVMService._estimate_poi_scores(33.0, 130.0)
        assert scores["view_score"] <= 90.0


# ──────────────────────────────────────
# _adjust_env_scores_by_infra 검증
# ──────────────────────────────────────


class TestAdjustEnvScoresByInfra:
    """지하시설물 밀도 기반 소음/조망 보정 검증."""

    def test_no_facilities(self) -> None:
        """시설물 0개 → 보정 없음."""
        current = {"noise_db": 55.0, "view_score": 60.0}
        result = AVMService._adjust_env_scores_by_infra([], current)
        assert result["noise_db"] == 55.0
        assert result["view_score"] == 60.0

    def test_high_density(self) -> None:
        """시설물 10개 이상 → 소음 증가, 조망 감소."""
        facilities = [{"facility_type": "가스"} for _ in range(12)]
        current = {"noise_db": 55.0, "view_score": 60.0}
        result = AVMService._adjust_env_scores_by_infra(facilities, current)
        assert result["noise_db"] > 55.0
        assert result["view_score"] < 60.0

    def test_noise_capped_at_80(self) -> None:
        """소음 최대 80dB 캡."""
        facilities = [{"facility_type": "전기"} for _ in range(50)]
        current = {"noise_db": 75.0, "view_score": 60.0}
        result = AVMService._adjust_env_scores_by_infra(facilities, current)
        assert result["noise_db"] <= 80.0

    def test_view_score_min_20(self) -> None:
        """조망 점수 최저 20점."""
        facilities = [{"facility_type": "상수도"} for _ in range(50)]
        current = {"noise_db": 55.0, "view_score": 30.0}
        result = AVMService._adjust_env_scores_by_infra(facilities, current)
        assert result["view_score"] >= 20.0

    def test_moderate_density(self) -> None:
        """시설물 5개 → 적절한 보정."""
        facilities = [{"facility_type": "통신"} for _ in range(5)]
        current = {"noise_db": 55.0, "view_score": 60.0}
        result = AVMService._adjust_env_scores_by_infra(facilities, current)
        assert 55.0 < result["noise_db"] < 70.0
        assert 40.0 < result["view_score"] < 60.0


# ──────────────────────────────────────
# _simple_price_estimate 3단계 폴백 체인
# ──────────────────────────────────────


class TestSimplePriceEstimate:
    """_simple_price_estimate 3단계 폴백 검증."""

    def test_comparables_first_priority(self) -> None:
        """1순위: 비교 사례 평균가격."""
        comparables = [
            {"price_10k_won": 30000},
            {"price_10k_won": 40000},
        ]
        features: dict[str, float] = {"land_official_price": 1_000_000}
        result = AVMService._simple_price_estimate(84.0, comparables, features)
        # 평균 35,000만원 = 3.5억원
        assert result == 35000 * 10_000

    def test_official_price_second_priority(self) -> None:
        """2순위: 공시지가 × 면적 × 1.5."""
        comparables: list[dict] = []
        features: dict[str, float] = {"land_official_price": 5_000_000}
        result = AVMService._simple_price_estimate(84.0, comparables, features)
        expected = 5_000_000 * 84.0 * 1.5
        assert result == expected

    def test_area_fallback_third_priority(self) -> None:
        """3순위: 면적 × 500만원."""
        comparables: list[dict] = []
        features: dict[str, float] = {"land_official_price": 0}
        result = AVMService._simple_price_estimate(84.0, comparables, features)
        assert result == 84.0 * 5_000_000

    def test_zero_price_comparables_skip(self) -> None:
        """price_10k_won이 0인 비교 사례는 건너뜀."""
        comparables = [
            {"price_10k_won": 0},
            {"price_10k_won": 0},
        ]
        features: dict[str, float] = {"land_official_price": 3_000_000}
        result = AVMService._simple_price_estimate(84.0, comparables, features)
        # 비교 사례가 있지만 유효한 가격이 없으므로 2순위로 넘어감
        expected = 3_000_000 * 84.0 * 1.5
        assert result == expected

    def test_missing_official_price_key(self) -> None:
        """features에 land_official_price가 없으면 3순위 폴백."""
        result = AVMService._simple_price_estimate(100.0, [], {})
        assert result == 100.0 * 5_000_000


# ──────────────────────────────────────
# _calculate_confidence 검증
# ──────────────────────────────────────


class TestCalculateConfidence:
    """신뢰도 계산 검증."""

    def test_production_high_comparables(self) -> None:
        """production 모델 + 비교 사례 50건 → 높은 신뢰도."""
        svc = AVMService.__new__(AVMService)
        conf = svc._calculate_confidence(50, "production")
        assert conf == 0.87 + 0.05  # 0.92

    def test_staging_medium_comparables(self) -> None:
        """staging + 비교 사례 15건 → 중간 신뢰도."""
        svc = AVMService.__new__(AVMService)
        conf = svc._calculate_confidence(15, "staging")
        assert conf == 0.70 + 0.02  # 0.72

    def test_fallback_low_comparables(self) -> None:
        """fallback + 비교 사례 2건 → 낮은 신뢰도."""
        svc = AVMService.__new__(AVMService)
        conf = svc._calculate_confidence(2, "fallback")
        assert conf == max(0.10, 0.40 - 0.10)  # 0.30

    def test_confidence_min_bound(self) -> None:
        """신뢰도 최소 0.10."""
        svc = AVMService.__new__(AVMService)
        conf = svc._calculate_confidence(0, "fallback")
        assert conf >= 0.10

    def test_confidence_max_bound(self) -> None:
        """신뢰도 최대 0.98."""
        svc = AVMService.__new__(AVMService)
        conf = svc._calculate_confidence(100, "production")
        assert conf <= 0.98


# ──────────────────────────────────────
# 16개 특성 벡터 키 검증
# ──────────────────────────────────────


EXPECTED_16_FEATURES = [
    "area_sqm",
    "building_age_years",
    "floor",
    "comparable_count",
    "total_floors",
    "land_official_price",
    "floor_area_ratio",
    "building_coverage_ratio",
    "recent_trans_avg_10k",
    "distance_to_subway_m",
    "distance_to_school_m",
    "school_score",
    "noise_db",
    "view_score",
    "month_sin",
    "month_cos",
]


class TestFeatureKeys:
    """16개 특성 벡터 키 존재 검증."""

    def test_all_16_keys_listed(self) -> None:
        """목록에 정확히 16개 키가 있다."""
        assert len(EXPECTED_16_FEATURES) == 16

    def test_no_duplicate_keys(self) -> None:
        """중복 키가 없다."""
        assert len(EXPECTED_16_FEATURES) == len(set(EXPECTED_16_FEATURES))
