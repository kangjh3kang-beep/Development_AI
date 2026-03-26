"""ContractorService 단위 테스트.

시공사 추천 스코어링(_score_candidate) 정적 메서드를 검증한다.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.contractor_service import ContractorService


def _make_contractor(**kwargs) -> MagicMock:
    """Contractor 모델 Mock 생성."""
    defaults = {
        "category": "general_contractor",
        "specialties_json": [],
        "address": None,
        "rating": None,
    }
    defaults.update(kwargs)
    mock = MagicMock()
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


class TestScoreCandidate:
    """_score_candidate 정적 메서드 테스트."""

    def test_기본점수_45(self):
        """카테고리 미매칭, 전문분야 없음, 지역 없음, 평점 없음 → 45점."""
        contractor = _make_contractor(category="plumbing")
        score, reasons = ContractorService._score_candidate(
            category="electrical",
            required_specialties=[],
            region_hint=None,
            contractor=contractor,
        )
        assert score == 45.0
        assert reasons == []

    def test_카테고리_일치_20점_추가(self):
        contractor = _make_contractor(category="electrical")
        score, reasons = ContractorService._score_candidate(
            category="electrical",
            required_specialties=[],
            region_hint=None,
            contractor=contractor,
        )
        assert score == 65.0
        assert "category aligned" in reasons

    def test_general_contractor_폴백_8점(self):
        contractor = _make_contractor(category="general_contractor")
        score, reasons = ContractorService._score_candidate(
            category="plumbing",
            required_specialties=[],
            region_hint=None,
            contractor=contractor,
        )
        assert score == 53.0
        assert "general contractor fallback" in reasons

    def test_전문분야_겹침_점수(self):
        """1개 겹침 → +10점, 최대 25점."""
        contractor = _make_contractor(
            category="hvac",
            specialties_json=["냉난방", "공조", "환기"],
        )
        score, reasons = ContractorService._score_candidate(
            category="hvac",
            required_specialties=["냉난방", "환기"],
            region_hint=None,
            contractor=contractor,
        )
        # 카테고리 +20 + 전문분야 2개×10=20 = 85
        assert score == 85.0

    def test_전문분야_최대_25점_캡(self):
        """3개 이상 겹침 → min(30, 25) = 25."""
        contractor = _make_contractor(
            category="plumbing",
            specialties_json=["a", "b", "c", "d"],
        )
        score, _ = ContractorService._score_candidate(
            category="plumbing",
            required_specialties=["a", "b", "c"],
            region_hint=None,
            contractor=contractor,
        )
        # 45 + 20(카테고리) + 25(캡) = 90
        assert score == 90.0

    def test_지역_매칭_10점(self):
        contractor = _make_contractor(
            category="plumbing", address="서울시 강남구 역삼동",
        )
        score, reasons = ContractorService._score_candidate(
            category="none",
            required_specialties=[],
            region_hint="강남",
            contractor=contractor,
        )
        # 45(기본) + 10(지역) = 55 (general_contractor 아닌 카테고리)
        assert score == 55.0
        assert "regional coverage matched" in reasons

    def test_평점_점수_반영(self):
        """rating 4.5 → +18점, + 'strong rating' 사유."""
        contractor = _make_contractor(category="other", rating=4.5)
        score, reasons = ContractorService._score_candidate(
            category="other2",
            required_specialties=[],
            region_hint=None,
            contractor=contractor,
        )
        # 45 + 4.5*4 = 63
        assert score == 63.0
        assert "strong rating" in reasons

    def test_평점_4미만_strong_rating_없음(self):
        contractor = _make_contractor(rating=3.5)
        _, reasons = ContractorService._score_candidate(
            category="x",
            required_specialties=[],
            region_hint=None,
            contractor=contractor,
        )
        assert "strong rating" not in reasons

    def test_점수_0_100_범위(self):
        """최소 0, 최대 100."""
        contractor = _make_contractor(
            category="electrical",
            specialties_json=["a", "b", "c"],
            address="서울시",
            rating=5.0,
        )
        score, _ = ContractorService._score_candidate(
            category="electrical",
            required_specialties=["a", "b", "c"],
            region_hint="서울",
            contractor=contractor,
        )
        assert 0.0 <= score <= 100.0

    def test_대소문자_무시_전문분야(self):
        """전문분야 비교 시 대소문자 무시."""
        contractor = _make_contractor(specialties_json=["HVAC", "Plumbing"])
        score, reasons = ContractorService._score_candidate(
            category="x",
            required_specialties=["hvac"],
            region_hint=None,
            contractor=contractor,
        )
        assert score >= 55.0  # 45 + 10(1개 겹침)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
