"""한국은행 경제통계시스템(ECOS) API 클라이언트.

기준금리, GDP 성장률, 물가지수 등 경제 지표를 조회한다.
API: https://ecos.bok.or.kr/

주요 기능:
- 기준금리 조회
- GDP 성장률 조회
- 소비자물가지수(CPI) 조회
- 건설투자 지수 조회
"""

from apps.api.integrations.base_client import BaseAPIClient


class EcosClient(BaseAPIClient):
    """한국은행 경제통계시스템 API 클라이언트."""

    service_name = "ecos"
    base_url = "https://ecos.bok.or.kr/api"

    async def get_base_rate(self) -> dict:
        """한국은행 기준금리를 조회한다."""
        return await self._request(
            "GET",
            f"/StatisticSearch/{self.settings.ecos_api_key}/json/kr/1/1/722Y001/M",
            cache_key="ecos:base_rate",
            cache_ttl=86400,
        )

    async def get_gdp_growth(self, year: str) -> dict:
        """GDP 성장률을 조회한다."""
        return await self._request(
            "GET",
            f"/StatisticSearch/{self.settings.ecos_api_key}/json/kr/1/1/200Y002/A/{year}/{year}",
            cache_key=f"ecos:gdp:{year}",
            cache_ttl=86400,
        )

    async def get_cpi(self, start_date: str, end_date: str) -> dict:
        """소비자물가지수를 조회한다."""
        return await self._request(
            "GET",
            f"/StatisticSearch/{self.settings.ecos_api_key}/json/kr/1/100/901Y009/M/{start_date}/{end_date}",
            cache_key=f"ecos:cpi:{start_date}:{end_date}",
            cache_ttl=86400,
        )

    async def get_construction_investment_index(self, year: str) -> dict:
        """건설투자 지수를 조회한다."""
        return await self._request(
            "GET",
            f"/StatisticSearch/{self.settings.ecos_api_key}/json/kr/1/1/301Y017/Q/{year}Q1/{year}Q4",
            cache_key=f"ecos:construction_inv:{year}",
            cache_ttl=86400,
        )
