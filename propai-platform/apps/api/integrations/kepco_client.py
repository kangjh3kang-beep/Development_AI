"""한국전력 API 클라이언트.

전력 사용량 조회 — 탄소 배출량 산출에 사용.
"""

from apps.api.integrations.base_client import BaseAPIClient


class KepcoClient(BaseAPIClient):
    service_name = "kepco"
    base_url = "https://opm.kepco.co.kr"

    async def get_power_usage(self, building_id: str, year_month: str) -> dict:
        return await self._request(
            "GET", "/openapi/powerUsage",
            params={
                "apiKey": self.settings.kepco_api_key,
                "buildingId": building_id,
                "yearMonth": year_month,
            },
            cache_key=f"kepco:usage:{building_id}:{year_month}",
            cache_ttl=86400,
        )
