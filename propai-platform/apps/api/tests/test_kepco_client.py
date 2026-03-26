"""KepcoClient 단위 테스트.

한국전력 API 클라이언트의 설정을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.kepco_client import KepcoClient


class TestKepcoClientConfig:
    """KepcoClient 설정 테스트."""

    def test_서비스이름(self):
        assert KepcoClient.service_name == "kepco"

    def test_base_url(self):
        assert "kepco.co.kr" in KepcoClient.base_url


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
