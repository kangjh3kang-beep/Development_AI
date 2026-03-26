"""BaseAPIClient 단위 테스트.

공통 베이스 클라이언트의 설정, 헤더, 서비스명을 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.base_client import BaseAPIClient


class TestBaseAPIClientDefaults:
    """BaseAPIClient 기본값 테스트."""

    def test_기본_서비스명(self):
        assert BaseAPIClient.service_name == "unknown"

    def test_기본_base_url(self):
        assert BaseAPIClient.base_url == ""

    def test_기본_timeout(self):
        assert BaseAPIClient.timeout == 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
