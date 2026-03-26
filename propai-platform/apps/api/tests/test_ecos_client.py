"""EcosClient 단위 테스트.

한국은행 경제통계시스템(ECOS) API 클라이언트의 설정 및 구조를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.ecos_client import EcosClient


class TestEcosClientConfig:
    """EcosClient 설정 테스트."""

    def test_서비스이름(self):
        """서비스명이 올바른지 확인."""
        assert EcosClient.service_name == "ecos"

    def test_base_url(self):
        """베이스 URL이 올바른지 확인."""
        assert "ecos.bok.or.kr" in EcosClient.base_url

    def test_인스턴스_생성(self):
        """인스턴스가 정상 생성되는지 확인."""
        client = EcosClient()
        assert client.circuit_breaker is not None

    def test_circuit_breaker_초기_상태(self):
        """Circuit Breaker 초기 상태가 CLOSED인지 확인."""
        client = EcosClient()
        assert client.circuit_breaker.state == "closed"
        assert client.circuit_breaker.failure_count == 0

    def test_메서드_get_base_rate_존재(self):
        """get_base_rate 메서드가 존재하는지 확인."""
        assert hasattr(EcosClient, "get_base_rate")

    def test_메서드_get_gdp_growth_존재(self):
        """get_gdp_growth 메서드가 존재하는지 확인."""
        assert hasattr(EcosClient, "get_gdp_growth")

    def test_메서드_get_cpi_존재(self):
        """get_cpi 메서드가 존재하는지 확인."""
        assert hasattr(EcosClient, "get_cpi")

    def test_메서드_get_construction_investment_index_존재(self):
        """get_construction_investment_index 메서드가 존재하는지 확인."""
        assert hasattr(EcosClient, "get_construction_investment_index")

    def test_base_url_형식(self):
        """베이스 URL이 /api로 끝나는지 확인."""
        assert EcosClient.base_url.endswith("/api")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
