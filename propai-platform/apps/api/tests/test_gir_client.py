"""GirClient 단위 테스트.

국가온실가스종합정보센터 API 클라이언트의 설정을 검증한다.
"""

import pytest

from apps.api.integrations.gir_client import GirClient


class TestGirClientConfig:
    """GirClient 설정 테스트."""

    def test_서비스이름(self):
        assert GirClient.service_name == "gir"

    def test_base_url(self):
        assert "gir.go.kr" in GirClient.base_url

    def test_메서드_존재(self):
        assert hasattr(GirClient, "get_building_emissions")
        assert hasattr(GirClient, "get_emission_factor")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
