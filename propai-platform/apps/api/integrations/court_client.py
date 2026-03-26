"""법원 등기 API 클라이언트.

대법원 인터넷등기소 — 부동산 등기 정보 조회.
에스크로/전세 리스크 분석에 사용.
"""

from apps.api.integrations.base_client import BaseAPIClient


class CourtClient(BaseAPIClient):
    """법원 등기 API 클라이언트."""

    service_name = "court"
    base_url = "https://api.court.go.kr"

    async def get_registry_info(self, registry_number: str) -> dict:
        """부동산 등기 정보를 조회한다."""
        return await self._request(
            "GET",
            "/openapi/registry",
            params={
                "apiKey": self.settings.court_api_key,
                "registryNo": registry_number,
                "format": "json",
            },
            cache_key=f"court:registry:{registry_number}",
            cache_ttl=3600,
        )

    async def check_lien(self, registry_number: str) -> dict:
        """근저당/압류 등 권리관계를 확인한다."""
        return await self._request(
            "GET",
            "/openapi/lien",
            params={
                "apiKey": self.settings.court_api_key,
                "registryNo": registry_number,
                "format": "json",
            },
            cache_key=f"court:lien:{registry_number}",
            cache_ttl=3600,
        )
