"""KetsClient 단위 테스트.

K-ETS(한국 배출권거래제) API 클라이언트의 설정 및 구조를 검증한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.kets_client import KetsClient


class TestKetsClientConfig:
    """KetsClient 설정 테스트."""

    def test_서비스이름(self):
        """서비스명이 올바른지 확인."""
        assert KetsClient.service_name == "kets"

    def test_base_url(self):
        """베이스 URL이 올바른지 확인."""
        assert "krx.co.kr" in KetsClient.base_url

    def test_인스턴스_생성(self):
        """인스턴스가 정상 생성되는지 확인."""
        client = KetsClient()
        assert client.circuit_breaker is not None

    def test_circuit_breaker_초기_상태(self):
        """Circuit Breaker 초기 상태가 CLOSED인지 확인."""
        client = KetsClient()
        assert client.circuit_breaker.state == "closed"
        assert client.circuit_breaker.failure_count == 0

    def test_메서드_get_kau_price_존재(self):
        """get_kau_price 메서드가 존재하는지 확인."""
        assert hasattr(KetsClient, "get_kau_price")

    def test_메서드_get_kcu_price_존재(self):
        """get_kcu_price 메서드가 존재하는지 확인."""
        assert hasattr(KetsClient, "get_kcu_price")

    def test_메서드_get_trading_history_존재(self):
        """get_trading_history 메서드가 존재하는지 확인."""
        assert hasattr(KetsClient, "get_trading_history")

    def test_base_url_형식(self):
        """베이스 URL이 /api로 끝나는지 확인."""
        assert KetsClient.base_url.endswith("/api")

    def test_timeout_기본값(self):
        """기본 타임아웃이 설정되어 있는지 확인."""
        assert KetsClient.timeout == 30.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
