"""MarketingService 단위 테스트.

마케팅 헤드라인, 본문 생성 등 결정론적 정적 메서드를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.marketing_service import MarketingService


class TestHeadline:
    """_headline 정적 메서드 테스트."""

    def test_기본_헤드라인_형식(self):
        result = MarketingService._headline("강남 프라임타워", "office", "digital")
        assert result == "강남 프라임타워 | office digital campaign"

    def test_프로젝트명_포함(self):
        result = MarketingService._headline("역삼 레지던스", "residential", "print")
        assert "역삼 레지던스" in result

    def test_채널_포함(self):
        result = MarketingService._headline("프로젝트A", "retail", "social")
        assert "social" in result

    def test_자산유형_포함(self):
        result = MarketingService._headline("프로젝트B", "logistics", "email")
        assert "logistics" in result


class TestBody:
    """_body 정적 메서드 테스트."""

    def test_기본_본문_생성(self):
        result = MarketingService._body(
            project_name="강남 프라임타워",
            asset_type="office",
            target_audience="institutional investors",
            tone="premium",
            highlights=["prime location", "AAA tenant"],
        )
        assert "강남 프라임타워" in result
        assert "office" in result
        assert "institutional investors" in result
        assert "premium" in result

    def test_하이라이트_포함(self):
        result = MarketingService._body(
            project_name="테스트",
            asset_type="retail",
            target_audience="개인투자자",
            tone="moderate",
            highlights=["역세권", "대단지"],
        )
        assert "역세권" in result
        assert "대단지" in result

    def test_빈_하이라이트_기본문구(self):
        result = MarketingService._body(
            project_name="테스트",
            asset_type="office",
            target_audience="기관투자자",
            tone="conservative",
            highlights=[],
        )
        assert "prime location and execution readiness" in result

    def test_하이라이트_최대4개(self):
        """5개 하이라이트 중 4개만 포함."""
        highlights = ["항목1", "항목2", "항목3", "항목4", "항목5제외"]
        result = MarketingService._body(
            project_name="테스트",
            asset_type="mixed",
            target_audience="LP",
            tone="institutional",
            highlights=highlights,
        )
        assert "항목5제외" not in result
        assert "항목1" in result
        assert "항목4" in result

    def test_고정_메시지_포함(self):
        result = MarketingService._body(
            project_name="X",
            asset_type="Y",
            target_audience="Z",
            tone="T",
            highlights=["h"],
        )
        assert "demand depth" in result
        assert "execution discipline" in result
        assert "risk-adjusted upside" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
