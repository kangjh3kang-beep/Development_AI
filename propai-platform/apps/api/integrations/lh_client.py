"""LH (한국토지주택공사) API 클라이언트.

공공분양/임대 정보, 택지 정보 조회.
"""

from apps.api.integrations.base_client import BaseAPIClient


class LHClient(BaseAPIClient):
    service_name = "lh"
    base_url = "https://api.lh.or.kr"

    async def get_public_housing(self, region_code: str) -> dict:
        return await self._request(
            "GET", "/openapi/publicHousing",
            params={
                "apiKey": self.settings.lh_api_key,
                "regionCode": region_code,
            },
            cache_key=f"lh:housing:{region_code}",
            cache_ttl=86400,
        )
