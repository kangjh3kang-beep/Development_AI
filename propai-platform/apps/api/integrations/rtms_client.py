"""실거래가 공개시스템(RTMS) API 클라이언트.

아파트 매매 및 전월세 실거래가 조회.
"""

from apps.api.integrations.base_client import BaseAPIClient


class RtmsClient(BaseAPIClient):
    service_name = "rtms"
    base_url = "http://openapi.molit.go.kr:8081/OpenAPI_ToolInstall498/service/rest/RTMSOBJSvc"

    async def get_apt_trade(self, lawd_cd: str, deal_ymd: str) -> dict:
        """아파트 매매 실거래가 조회."""
        return await self._request(
            "GET", "/getRTMSDataSvcAptTradeDev",
            params={
                "serviceKey": self.settings.rtms_api_key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "numOfRows": "100",
                "pageNo": "1",
            },
            cache_key=f"rtms:apt_trade:{lawd_cd}:{deal_ymd}",
            cache_ttl=43200,
        )

    async def get_apt_rent(self, lawd_cd: str, deal_ymd: str) -> dict:
        """아파트 전월세 실거래가 조회."""
        return await self._request(
            "GET", "/getRTMSDataSvcAptRent",
            params={
                "serviceKey": self.settings.rtms_api_key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "numOfRows": "100",
                "pageNo": "1",
            },
            cache_key=f"rtms:apt_rent:{lawd_cd}:{deal_ymd}",
            cache_ttl=43200,
        )
