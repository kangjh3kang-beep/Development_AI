"""K-ETS(한국 배출권거래제) API 클라이언트.

한국거래소에서 제공하는 배출권(KAU/KCU) 시세를 조회한다.
https://ets.krx.co.kr/

주요 기능:
- KAU(한국 배출 할당량) 시세 조회
- KCU(한국 크레딧) 시세 조회
- 배출권 거래 이력 조회
"""

from apps.api.integrations.base_client import BaseAPIClient


class KetsClient(BaseAPIClient):
    """K-ETS 배출권 거래 시세 API 클라이언트."""

    service_name = "kets"
    base_url = "https://ets.krx.co.kr/api"

    async def get_kau_price(self) -> dict:
        """KAU(배출 할당량) 현재 시세를 조회한다."""
        return await self._request(
            "GET",
            "/market/kau/price",
            params={"apiKey": self.settings.kets_api_key},
            cache_key="kets:kau:current",
            cache_ttl=1800,
        )

    async def get_kcu_price(self) -> dict:
        """KCU(크레딧) 현재 시세를 조회한다."""
        return await self._request(
            "GET",
            "/market/kcu/price",
            params={"apiKey": self.settings.kets_api_key},
            cache_key="kets:kcu:current",
            cache_ttl=1800,
        )

    async def get_trading_history(self, *, start_date: str, end_date: str) -> dict:
        """배출권 거래 이력을 조회한다."""
        return await self._request(
            "GET",
            "/market/history",
            params={
                "apiKey": self.settings.kets_api_key,
                "startDate": start_date,
                "endDate": end_date,
            },
            cache_key=f"kets:history:{start_date}:{end_date}",
            cache_ttl=86400,
        )
