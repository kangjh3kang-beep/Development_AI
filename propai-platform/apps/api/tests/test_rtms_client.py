"""RtmsClient 단위 테스트.

실거래가 공개시스템 API 클라이언트의 설정을 검증한다.
"""

import pytest

from apps.api.integrations.rtms_client import RtmsClient


class TestRtmsClientConfig:
    """RtmsClient 설정 테스트."""

    def test_서비스이름(self):
        assert RtmsClient.service_name == "rtms"

    def test_base_url(self):
        assert "molit.go.kr" in RtmsClient.base_url

    def test_메서드_존재(self):
        assert hasattr(RtmsClient, "get_apt_trade")
        assert hasattr(RtmsClient, "get_apt_rent")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
