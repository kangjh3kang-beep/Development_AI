"""KmaClient 단위 테스트.

기상청 API 클라이언트의 설정을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.kma_client import KmaClient


class TestKmaClientConfig:
    """KmaClient 설정 테스트."""

    def test_서비스이름(self):
        assert KmaClient.service_name == "kma"

    def test_base_url(self):
        assert "apis.data.go.kr" in KmaClient.base_url

    def test_base_url_기상청_엔드포인트(self):
        assert "VilageFcst" in KmaClient.base_url


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
