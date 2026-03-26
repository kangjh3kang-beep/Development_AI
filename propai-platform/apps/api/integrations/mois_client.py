"""행정안전부(MOIS) API 클라이언트.

지역 재해위험 등급 및 건축물 안전등급 조회.
"""

from apps.api.integrations.base_client import BaseAPIClient


class MoisClient(BaseAPIClient):
    service_name = "mois"
    base_url = "http://apis.data.go.kr/1741000"

    async def get_disaster_risk(self, region_code: str) -> dict:
        """지역 재해위험 등급 조회."""
        return await self._request(
            "GET", "/DisasterRiskInfo/getDisasterRiskList",
            params={
                "serviceKey": self.settings.mois_api_key,
                "regionCode": region_code,
                "numOfRows": "10",
                "pageNo": "1",
                "dataType": "JSON",
            },
            cache_key=f"mois:disaster:{region_code}",
            cache_ttl=86400,
        )

    async def get_building_safety_grade(self, address: str) -> dict:
        """건축물 안전등급 조회."""
        return await self._request(
            "GET", "/BuildingSafetyGrade/getBuildingSafetyGradeList",
            params={
                "serviceKey": self.settings.mois_api_key,
                "address": address,
                "numOfRows": "10",
                "pageNo": "1",
                "dataType": "JSON",
            },
            cache_key=f"mois:safety:{address}",
            cache_ttl=86400,
        )
