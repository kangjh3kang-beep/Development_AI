"""MoisClient 단위 테스트.

행정안전부 API 클라이언트의 설정을 검증한다.
"""

import pytest

from apps.api.integrations.mois_client import MoisClient


class TestMoisClientConfig:
    """MoisClient 설정 테스트."""

    def test_서비스이름(self):
        assert MoisClient.service_name == "mois"

    def test_base_url(self):
        assert "1741000" in MoisClient.base_url

    def test_메서드_존재(self):
        assert hasattr(MoisClient, "get_disaster_risk")
        assert hasattr(MoisClient, "get_building_safety_grade")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
