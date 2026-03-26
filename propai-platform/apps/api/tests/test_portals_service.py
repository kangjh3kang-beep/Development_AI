"""PortalsService 단위 테스트.

포탈별 기본값(_portal_defaults)과 상수(_PORTAL_FACTORS)를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.portals_service import _PORTAL_FACTORS, PortalsService


class TestPortalFactors:
    """_PORTAL_FACTORS 상수 테스트."""

    def test_4개_포탈_정의(self):
        assert len(_PORTAL_FACTORS) == 4

    def test_naver_포함(self):
        assert "naver" in _PORTAL_FACTORS

    def test_zigbang_포함(self):
        assert "zigbang" in _PORTAL_FACTORS

    def test_dabang_포함(self):
        assert "dabang" in _PORTAL_FACTORS

    def test_peterpan_포함(self):
        assert "peterpan" in _PORTAL_FACTORS

    def test_naver_조회수_최고(self):
        naver_views = _PORTAL_FACTORS["naver"]["views"]
        for portal, factors in _PORTAL_FACTORS.items():
            if portal != "naver":
                assert naver_views >= factors["views"]

    def test_각_포탈_5개_메트릭(self):
        for portal, factors in _PORTAL_FACTORS.items():
            assert set(factors.keys()) == {"views", "inquiries", "ctr", "bookmark", "rank"}, \
                f"{portal} 메트릭 키 불일치"


class TestPortalDefaults:
    """_portal_defaults 정적 메서드 테스트."""

    def test_naver_기본값(self):
        result = PortalsService._portal_defaults("naver")
        assert result["views"] == 220
        assert result["inquiries"] == 12
        assert result["ctr"] == 0.19

    def test_zigbang_기본값(self):
        result = PortalsService._portal_defaults("zigbang")
        assert result["views"] == 180

    def test_dabang_기본값(self):
        result = PortalsService._portal_defaults("dabang")
        assert result["views"] == 165

    def test_peterpan_기본값(self):
        result = PortalsService._portal_defaults("peterpan")
        assert result["views"] == 120

    def test_알수없는_포탈_기본값(self):
        """등록되지 않은 포탈 → 기본 폴백값."""
        result = PortalsService._portal_defaults("unknown_portal")
        assert result["views"] == 140
        assert result["inquiries"] == 6
        assert result["ctr"] == 0.12
        assert result["bookmark"] == 4
        assert result["rank"] == 10

    def test_빈문자열_포탈_기본값(self):
        result = PortalsService._portal_defaults("")
        assert result["views"] == 140


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
