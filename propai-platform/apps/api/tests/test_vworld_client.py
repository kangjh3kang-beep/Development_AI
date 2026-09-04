"""VWorldClient 단위 테스트.

폴백 메서드와 지하시설물 유형 매핑 상수를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.vworld_client import _FACILITY_TYPE_MAP, VWorldClient


class TestFacilityTypeMap:
    """_FACILITY_TYPE_MAP 상수 테스트."""

    def test_7개_유형(self):
        assert len(_FACILITY_TYPE_MAP) == 7

    def test_가스_매핑(self):
        assert _FACILITY_TYPE_MAP["01"] == "가스"

    def test_전기_매핑(self):
        assert _FACILITY_TYPE_MAP["02"] == "전기"

    def test_통신_매핑(self):
        assert _FACILITY_TYPE_MAP["03"] == "통신"

    def test_상수도_매핑(self):
        assert _FACILITY_TYPE_MAP["04"] == "상수도"

    def test_하수도_매핑(self):
        assert _FACILITY_TYPE_MAP["05"] == "하수도"


class TestParcelFallback:
    """_parcel_fallback 정적 메서드 테스트."""

    def test_기본_폴백_구조(self):
        result = VWorldClient._parcel_fallback("1234567890")
        assert result["pnu"] == "1234567890"
        assert result["land_area_m2"] == 0.0
        assert result["fallback"] is True

    def test_에러_메시지_포함(self):
        result = VWorldClient._parcel_fallback("123", reason="timeout")
        assert result["error"] == "timeout"


class TestLandUseFallback:
    """_land_use_fallback 정적 메서드 테스트."""

    def test_기본_폴백_구조(self):
        result = VWorldClient._land_use_fallback("1234567890")
        assert result["pnu"] == "1234567890"
        assert result["land_use_zone"] == "알 수 없음"
        assert result["far_limit"] == 0.0
        assert result["bcr_limit"] == 0.0
        assert result["fallback"] is True


class TestGeocodeFallback:
    """_geocode_fallback 정적 메서드 테스트."""

    def test_기본_폴백_구조(self):
        result = VWorldClient._geocode_fallback("서울시 강남구")
        assert result["lat"] == 0.0
        assert result["lon"] == 0.0
        assert result["address"] == "서울시 강남구"
        assert result["fallback"] is True


class TestClientConfig:
    """VWorldClient 설정 테스트."""

    def test_서비스이름(self):
        assert VWorldClient.service_name == "vworld"

    def test_base_url(self):
        assert VWorldClient.base_url == "https://api.vworld.kr"

    def test_snapshot_enabled_on(self):
        # W2-1: 스파이크에서 BaseAPIClient 경유가 확인된 실사용 커넥터 — SourceSnapshot ON.
        assert VWorldClient.snapshot_enabled is True

    def test_snapshot_source_meta(self):
        assert VWorldClient.source_name
        assert VWorldClient.authority_grade == "OFFICIAL"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
