"""HUG (주택도시보증공사) API 클라이언트.

전세보증보험 가입 가능성 조회 — 전세 리스크 분석에 사용.
"""

from apps.api.integrations.base_client import BaseAPIClient


class HugClient(BaseAPIClient):
    service_name = "hug"
    base_url = "https://api.hug.go.kr"

    async def check_guarantee_eligibility(self, address: str, jeonse_amount: int) -> dict:
        return await self._request(
            "GET", "/openapi/guarantee/check",
            params={
                "apiKey": self.settings.hug_api_key,
                "address": address,
                "amount": str(jeonse_amount),
            },
            cache_key=f"hug:guarantee:{address}:{jeonse_amount}",
            cache_ttl=3600,
        )
