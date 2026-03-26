"""SeumterClient 단위 테스트.

세움터 건축 인허가 API 클라이언트의 설정 및 구조를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.seumter_client import SeumterClient


class TestSeumterClientConfig:
    """SeumterClient 설정 테스트."""

    def test_서비스이름(self):
        """서비스명이 올바른지 확인."""
        assert SeumterClient.service_name == "seumter"

    def test_base_url(self):
        """베이스 URL이 올바른지 확인."""
        assert "cloud.eais.go.kr" in SeumterClient.base_url

    def test_인스턴스_생성(self):
        """인스턴스가 정상 생성되는지 확인."""
        client = SeumterClient()
        assert client.circuit_breaker is not None

    def test_circuit_breaker_초기_상태(self):
        """Circuit Breaker 초기 상태가 CLOSED인지 확인."""
        client = SeumterClient()
        assert client.circuit_breaker.state == "closed"
        assert client.circuit_breaker.failure_count == 0

    def test_메서드_get_building_permit_존재(self):
        """get_building_permit 메서드가 존재하는지 확인."""
        assert hasattr(SeumterClient, "get_building_permit")

    def test_메서드_search_permits_by_address_존재(self):
        """search_permits_by_address 메서드가 존재하는지 확인."""
        assert hasattr(SeumterClient, "search_permits_by_address")

    def test_메서드_get_building_register_존재(self):
        """get_building_register 메서드가 존재하는지 확인."""
        assert hasattr(SeumterClient, "get_building_register")

    def test_메서드_get_permit_status_존재(self):
        """get_permit_status 메서드가 존재하는지 확인."""
        assert hasattr(SeumterClient, "get_permit_status")

    def test_default_headers_오버라이드(self):
        """_default_headers가 인증 헤더를 포함하는지 확인."""
        client = SeumterClient()
        headers = client._default_headers()
        assert "Authorization" in headers
        assert headers["User-Agent"] == "PropAI/30.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
