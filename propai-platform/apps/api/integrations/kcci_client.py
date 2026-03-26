"""건설공사비지수(KCCI) API 클라이언트.

한국건설기술연구원에서 제공하는 건설공사비지수를 조회한다.
자재 가격, 노무비, 장비비 변동을 추적한다.

주요 기능:
- 건설공사비 지수 조회 (월별)
- 자재별 가격 지수 조회
- 노무비 지수 조회
"""

from apps.api.integrations.base_client import BaseAPIClient


class KcciClient(BaseAPIClient):
    """건설공사비지수 API 클라이언트."""

    service_name = "kcci"
    base_url = "https://www.csi.go.kr/api"

    async def get_construction_cost_index(self, year_month: str) -> dict:
        """건설공사비 종합 지수를 조회한다."""
        return await self._request(
            "GET",
            "/cost-index",
            params={
                "apiKey": self.settings.kcci_api_key,
                "yearMonth": year_month,
            },
            cache_key=f"kcci:index:{year_month}",
            cache_ttl=86400,
        )

    async def get_material_price_index(
        self, material_code: str, year_month: str
    ) -> dict:
        """자재별 가격 지수를 조회한다."""
        return await self._request(
            "GET",
            "/material-index",
            params={
                "apiKey": self.settings.kcci_api_key,
                "materialCode": material_code,
                "yearMonth": year_month,
            },
            cache_key=f"kcci:material:{material_code}:{year_month}",
            cache_ttl=86400,
        )

    async def get_labor_cost_index(self, year_month: str) -> dict:
        """노무비 지수를 조회한다."""
        return await self._request(
            "GET",
            "/labor-index",
            params={
                "apiKey": self.settings.kcci_api_key,
                "yearMonth": year_month,
            },
            cache_key=f"kcci:labor:{year_month}",
            cache_ttl=86400,
        )
