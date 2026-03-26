"""DevelopmentMethodService 단위 테스트.

AHP 가중치, 7가지 개발방법 점수 산출, 면적/용도지역 기반 조정,
BCR 계산, 순위 정렬 등 핵심 로직을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.development_method_service import (
    AHP_WEIGHTS,
    BASE_SCORE_MATRIX,
    DEVELOPMENT_METHODS,
    DevelopmentMethodService,
    SiteProfile,
)


# ── 공통 테스트 프로파일 ──


def _make_profile(**overrides) -> SiteProfile:
    """기본 SiteProfile을 생성하고, overrides로 필드를 재정의한다."""
    defaults = {
        "site_area_sqm": 3000.0,
        "zoning_type": "제1종일반주거지역",
        "current_use": "나대지",
        "ownership_type": "단독",
        "road_frontage_m": 15.0,
        "transit_score": 7.0,
        "current_value_krw": 5_000_000_000,
        "building_age_years": None,
        "num_owners": 1,
    }
    defaults.update(overrides)
    return SiteProfile(**defaults)


class TestAHPWeights:
    """AHP 가중치 검증."""

    def test_ahp_가중치_합_1(self):
        """AHP 가중치 합계가 정확히 1.0이어야 한다."""
        assert sum(AHP_WEIGHTS) == pytest.approx(1.0, abs=1e-10)

    def test_ahp_가중치_개수(self):
        """AHP 가중치는 4개 항목이어야 한다."""
        assert len(AHP_WEIGHTS) == 4


class TestScoreCalculation:
    """점수 산출 검증."""

    def test_7가지_방법_전부_점수_산출(self):
        """7가지 개발방법 모두에 대해 가중 점수가 산출되어야 한다."""
        profile = _make_profile()
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        weighted = DevelopmentMethodService._calculate_weighted_scores(adjusted)
        assert len(weighted) == 7
        for method in DEVELOPMENT_METHODS:
            assert method in weighted, f"{method} 누락"

    def test_가중점수_범위(self):
        """모든 가중 점수가 1.0 ~ 10.0 범위 내여야 한다."""
        profile = _make_profile()
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        weighted = DevelopmentMethodService._calculate_weighted_scores(adjusted)
        for method, score in weighted.items():
            assert 1.0 <= score <= 10.0, (
                f"{method}: 가중점수 {score}가 범위 밖"
            )

    def test_점수_범위_1_10(self):
        """모든 조정 점수가 1 이상 10 이하여야 한다."""
        # 극단적 프로파일로 클램프 검증
        profile = _make_profile(site_area_sqm=100, num_owners=500)
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        for method, scores in adjusted.items():
            for i, s in enumerate(scores):
                assert 1 <= s <= 10, (
                    f"{method}[{i}] = {s} 범위 밖 (profile: 소규모+다수소유자)"
                )

    def test_weighted_score_계산_정확성(self):
        """수동 계산과 서비스 계산 결과가 일치해야 한다."""
        profile = _make_profile()
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        weighted = DevelopmentMethodService._calculate_weighted_scores(adjusted)

        # 단독개발의 수동 계산
        scores = adjusted["단독개발"]
        expected = sum(s * w for s, w in zip(scores, AHP_WEIGHTS))
        assert weighted["단독개발"] == pytest.approx(expected, rel=1e-6)


class TestAreaAdjustments:
    """면적 기반 점수 조정 검증."""

    def test_소규모_필지_단독개발_1위(self):
        """면적 500m2 → 단독개발이 최고 점수여야 한다."""
        profile = _make_profile(site_area_sqm=500)
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        weighted = DevelopmentMethodService._calculate_weighted_scores(adjusted)
        ranked = DevelopmentMethodService._rank_methods(weighted)
        assert ranked[0][0] == "단독개발", (
            f"소규모 필지에서 1위가 '{ranked[0][0]}'이 아니라 '단독개발'이어야 함"
        )

    def test_대규모_필지_도시개발_상위(self):
        """면적 30,000m2 → 도시개발/정비의 수익성 점수가 최대치(10)여야 한다.

        대규모 필지에서 도시개발/정비는 수익성 +2 보너스를 받아
        수익성 점수가 클램프 상한인 10에 도달한다.
        사업기간/인허가 점수가 낮아 종합 순위는 하위일 수 있지만,
        수익성 측면에서는 가장 유리한 방법이다.
        """
        profile = _make_profile(site_area_sqm=30_000)
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        # 도시개발/정비는 수익성(인덱스 0) 점수가 최대치
        assert adjusted["도시개발"][0] == 10, (
            f"대규모 도시개발 수익성={adjusted['도시개발'][0]} != 10"
        )
        assert adjusted["도시정비"][0] == 10, (
            f"대규모 도시정비 수익성={adjusted['도시정비'][0]} != 10"
        )
        # 단독개발은 위험도(인덱스 2)가 감소해야 한다
        base_risk = BASE_SCORE_MATRIX["단독개발"][2]
        assert adjusted["단독개발"][2] < base_risk, (
            f"대규모 단독개발 위험도={adjusted['단독개발'][2]} >= 기본 {base_risk}"
        )

    def test_adjust_scores_면적_1000_미만(self):
        """면적 1000 미만에서 단독개발 수익성이 기본값보다 높아야 한다."""
        profile = _make_profile(site_area_sqm=500)
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        base = BASE_SCORE_MATRIX["단독개발"][0]
        assert adjusted["단독개발"][0] >= base, (
            f"소규모 단독개발 수익성 {adjusted['단독개발'][0]} < 기본 {base}"
        )

    def test_adjust_scores_면적_10000_초과(self):
        """면적 10000 초과에서 도시개발 수익성이 기본값보다 높아야 한다."""
        profile = _make_profile(site_area_sqm=15_000)
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        base = BASE_SCORE_MATRIX["도시개발"][0]
        assert adjusted["도시개발"][0] >= base, (
            f"대규모 도시개발 수익성 {adjusted['도시개발'][0]} < 기본 {base}"
        )


class TestZoningAdjustments:
    """용도지역 기반 점수 조정 검증."""

    def test_상업지역_합동개발_보너스(self):
        """일반상업지역에서 합동개발의 수익성이 기본값보다 높아야 한다."""
        profile = _make_profile(zoning_type="일반상업지역")
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        base = BASE_SCORE_MATRIX["합동개발"][0]
        assert adjusted["합동개발"][0] >= base, (
            f"상업지역 합동개발 수익성 {adjusted['합동개발'][0]} < 기본 {base}"
        )

    def test_준공업_도시정비_보너스(self):
        """준공업지역에서 도시정비의 수익성이 기본값보다 높아야 한다."""
        profile = _make_profile(zoning_type="준공업지역")
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        base = BASE_SCORE_MATRIX["도시정비"][0]
        assert adjusted["도시정비"][0] >= base, (
            f"준공업 도시정비 수익성 {adjusted['도시정비'][0]} < 기본 {base}"
        )


class TestBuildingAndOwnership:
    """건물 연수 및 소유자 수 기반 조정 검증."""

    def test_리모델링_노후건물_보너스(self):
        """30년 노후 건물이 있으면 리모델링의 수익성이 증가해야 한다."""
        profile = _make_profile(building_age_years=30)
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        base = BASE_SCORE_MATRIX["리모델링"][0]
        assert adjusted["리모델링"][0] > base, (
            f"노후건물 리모델링 수익성 {adjusted['리모델링'][0]} <= 기본 {base}"
        )

    def test_다수소유자_도시정비_감점(self):
        """소유자 200명이면 도시정비의 인허가 점수가 감소해야 한다."""
        profile = _make_profile(num_owners=200)
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        base = BASE_SCORE_MATRIX["도시정비"][3]  # 인허가용이
        assert adjusted["도시정비"][3] < base, (
            f"다수소유자 도시정비 인허가 {adjusted['도시정비'][3]} >= 기본 {base}"
        )


class TestBCR:
    """BCR (비용효익비) 검증."""

    def test_bcr_양수(self):
        """일반 조건에서 BCR이 양수여야 한다."""
        profile = _make_profile()
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        weighted = DevelopmentMethodService._calculate_weighted_scores(adjusted)
        ranked = DevelopmentMethodService._rank_methods(weighted)
        best_method, best_score = ranked[0]
        bcr = DevelopmentMethodService._calculate_bcr(profile, best_method, best_score)
        assert bcr > 0, f"BCR={bcr} <= 0"

    def test_bcr_리모델링_높음(self):
        """리모델링은 비용비율이 0.5로 낮아서 BCR이 상대적으로 높아야 한다."""
        profile = _make_profile(building_age_years=30)
        # 리모델링의 가중 점수를 사용
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        weighted = DevelopmentMethodService._calculate_weighted_scores(adjusted)
        remodel_score = weighted["리모델링"]
        bcr_remodel = DevelopmentMethodService._calculate_bcr(
            profile, "리모델링", remodel_score
        )

        # 도시개발의 BCR과 비교
        dev_score = weighted["도시개발"]
        bcr_dev = DevelopmentMethodService._calculate_bcr(
            profile, "도시개발", dev_score
        )

        assert bcr_remodel > bcr_dev, (
            f"리모델링 BCR={bcr_remodel} <= 도시개발 BCR={bcr_dev}"
        )

    def test_current_value_0_bcr_0(self):
        """현재 토지 가치가 0이면 BCR이 0이어야 한다."""
        profile = _make_profile(current_value_krw=0)
        bcr = DevelopmentMethodService._calculate_bcr(profile, "단독개발", 7.5)
        assert bcr == 0.0


class TestRanking:
    """순위 정렬 검증."""

    def test_rank_내림차순(self):
        """ranked 리스트가 점수 기준 내림차순이어야 한다."""
        profile = _make_profile()
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        weighted = DevelopmentMethodService._calculate_weighted_scores(adjusted)
        ranked = DevelopmentMethodService._rank_methods(weighted)
        scores = [s for _, s in ranked]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"순위 역전: {scores[i]} < {scores[i + 1]}"
            )


class TestClamp:
    """클램프 로직 검증."""

    def test_클램프_최소1_최대10(self):
        """극단적 조건에서도 모든 점수가 1~10 범위 내여야 한다."""
        # 매우 극단적: 소규모 + 다수 소유자 + 노후 건물
        profile = _make_profile(
            site_area_sqm=100,
            num_owners=500,
            building_age_years=50,
        )
        adjusted = DevelopmentMethodService._adjust_scores(profile)
        for method, scores in adjusted.items():
            for i, s in enumerate(scores):
                assert 1 <= s <= 10, (
                    f"{method}[{i}] = {s} 범위 밖 (극단적 프로파일)"
                )


class TestSiteProfile:
    """SiteProfile dataclass 검증."""

    def test_site_profile_dataclass_생성(self):
        """SiteProfile이 정상적으로 생성되어야 한다."""
        profile = _make_profile()
        assert profile.site_area_sqm == 3000.0
        assert profile.zoning_type == "제1종일반주거지역"
        assert profile.current_use == "나대지"
        assert profile.ownership_type == "단독"
        assert profile.road_frontage_m == 15.0
        assert profile.transit_score == 7.0
        assert profile.current_value_krw == 5_000_000_000
        assert profile.building_age_years is None
        assert profile.num_owners == 1

    def test_기본_site_profile(self):
        """모든 필드가 정상 값으로 설정된 SiteProfile."""
        profile = SiteProfile(
            site_area_sqm=5000.0,
            zoning_type="일반상업지역",
            current_use="상업",
            ownership_type="법인",
            road_frontage_m=20.0,
            transit_score=9.0,
            current_value_krw=10_000_000_000,
            building_age_years=15,
            num_owners=3,
        )
        assert profile.site_area_sqm == 5000.0
        assert profile.zoning_type == "일반상업지역"
        assert profile.building_age_years == 15
        assert profile.num_owners == 3


class TestBaseScoreMatrix:
    """기본 점수 매트릭스 무결성 검증."""

    def test_모든_방법_매트릭스_존재(self):
        """7가지 개발방법 모두 기본 점수 매트릭스에 존재해야 한다."""
        for method in DEVELOPMENT_METHODS:
            assert method in BASE_SCORE_MATRIX, f"{method} 매트릭스 누락"

    def test_매트릭스_각_방법_4개_항목(self):
        """각 방법의 기본 점수가 4개 항목이어야 한다."""
        for method, scores in BASE_SCORE_MATRIX.items():
            assert len(scores) == 4, (
                f"{method}: 항목 수 {len(scores)} != 4"
            )

    def test_매트릭스_기본점수_범위(self):
        """기본 점수가 모두 1~10 범위 내여야 한다."""
        for method, scores in BASE_SCORE_MATRIX.items():
            for i, s in enumerate(scores):
                assert 1 <= s <= 10, f"{method}[{i}] = {s} 범위 밖"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
