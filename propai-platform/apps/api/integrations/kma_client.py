"""기상청 API 클라이언트.

기상 데이터 조회 — 공사 일지 자동 입력, 설계 환경 분석.
"""

from apps.api.integrations.base_client import BaseAPIClient


class KmaClient(BaseAPIClient):
    service_name = "kma"
    base_url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

    async def get_weather(self, nx: int, ny: int, base_date: str, base_time: str = "0600") -> dict:
        return await self._request(
            "GET", "/getVilageFcst",
            params={
                "serviceKey": self.settings.kma_api_key,
                "numOfRows": "100",
                "pageNo": "1",
                "dataType": "JSON",
                "base_date": base_date,
                "base_time": base_time,
                "nx": str(nx),
                "ny": str(ny),
            },
            cache_key=f"kma:weather:{nx}:{ny}:{base_date}",
            cache_ttl=3600,
        )
