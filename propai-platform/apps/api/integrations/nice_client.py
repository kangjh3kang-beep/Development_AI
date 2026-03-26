"""NICE 신용평가 API 클라이언트.

신용등급 조회, 소득/부채 검증.
재무 분석 서비스에서 사용.
"""

from apps.api.integrations.base_client import BaseAPIClient


class NiceClient(BaseAPIClient):
    service_name = "nice"
    base_url = "https://api.nice.co.kr"

    async def get_credit_score(self, user_token: str) -> dict:
        return await self._request(
            "POST", "/credit/score",
            json_data={"token": user_token, "apiKey": self.settings.nice_api_key},
            cache_key=None,
        )
