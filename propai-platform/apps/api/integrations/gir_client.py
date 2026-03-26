"""국가온실가스종합정보센터(GIR) API 클라이언트.

건물 온실가스 배출량 및 에너지원별 배출 계수 조회.
"""

from apps.api.integrations.base_client import BaseAPIClient


class GirClient(BaseAPIClient):
    service_name = "gir"
    base_url = "https://www.gir.go.kr/openapi"

    async def get_building_emissions(self, building_code: str, year: str) -> dict:
        """건물 온실가스 배출량 조회."""
        return await self._request(
            "GET", "/buildingEmission",
            params={
                "apiKey": self.settings.gir_api_key,
                "buildingCode": building_code,
                "year": year,
                "dataType": "JSON",
            },
            cache_key=f"gir:emission:{building_code}:{year}",
            cache_ttl=86400,
        )

    async def get_emission_factor(self, energy_type: str) -> dict:
        """에너지원별 배출 계수 조회."""
        return await self._request(
            "GET", "/emissionFactor",
            params={
                "apiKey": self.settings.gir_api_key,
                "energyType": energy_type,
                "dataType": "JSON",
            },
            cache_key=f"gir:factor:{energy_type}",
            cache_ttl=86400,
        )
