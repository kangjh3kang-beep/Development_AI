"""KcciClient 단위 테스트.

건설공사비지수(KCCI) API 클라이언트의 설정 및 구조를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.kcci_client import KcciClient


class TestKcciClientConfig:
    """KcciClient 설정 테스트."""

    def test_서비스이름(self):
        """서비스명이 올바른지 확인."""
        assert KcciClient.service_name == "kcci"

    def test_base_url(self):
        """베이스 URL이 올바른지 확인."""
        assert "csi.go.kr" in KcciClient.base_url

    def test_인스턴스_생성(self):
        """인스턴스가 정상 생성되는지 확인."""
        client = KcciClient()
        assert client.circuit_breaker is not None

    def test_circuit_breaker_초기_상태(self):
        """Circuit Breaker 초기 상태가 CLOSED인지 확인."""
        client = KcciClient()
        assert client.circuit_breaker.state == "closed"
        assert client.circuit_breaker.failure_count == 0

    def test_메서드_get_construction_cost_index_존재(self):
        """get_construction_cost_index 메서드가 존재하는지 확인."""
        assert hasattr(KcciClient, "get_construction_cost_index")

    def test_메서드_get_material_price_index_존재(self):
        """get_material_price_index 메서드가 존재하는지 확인."""
        assert hasattr(KcciClient, "get_material_price_index")

    def test_메서드_get_labor_cost_index_존재(self):
        """get_labor_cost_index 메서드가 존재하는지 확인."""
        assert hasattr(KcciClient, "get_labor_cost_index")

    def test_base_url_형식(self):
        """베이스 URL이 /api로 끝나는지 확인."""
        assert KcciClient.base_url.endswith("/api")

    def test_timeout_기본값(self):
        """기본 타임아웃이 설정되어 있는지 확인."""
        assert KcciClient.timeout == 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
