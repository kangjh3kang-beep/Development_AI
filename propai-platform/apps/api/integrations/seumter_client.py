"""세움터 API 클라이언트.

세움터(https://cloud.eais.go.kr)는 건축행정시스템으로
건축 인허가 신청/조회/진행상태 확인 API를 제공한다.

주요 기능:
- 건축허가 조회 (허가번호, 주소 기반)
- 건축물대장 조회
- 인허가 진행상태 추적
"""

import structlog

from apps.api.integrations.base_client import BaseAPIClient

logger = structlog.get_logger(__name__)


class SeumterClient(BaseAPIClient):
    """세움터 건축 인허가 API 클라이언트."""

    service_name = "seumter"
    base_url = "https://cloud.eais.go.kr/api"

    def _default_headers(self) -> dict[str, str]:
        """세움터 인증 헤더를 반환한다."""
        return {
            "User-Agent": "PropAI/30.0",
            "Authorization": f"Bearer {self.settings.seumter_api_key}",
        }

    async def get_building_permit(self, permit_number: str) -> dict:
        """건축허가 정보를 조회한다."""
        return await self._request(
            "GET",
            "/permits",
            params={"permitNo": permit_number},
            cache_key=f"seumter:permit:{permit_number}",
            cache_ttl=1800,
        )

    async def search_permits_by_address(
        self, address: str, *, page: int = 1, size: int = 20
    ) -> dict:
        """주소 기반으로 건축허가를 검색한다."""
        return await self._request(
            "GET",
            "/permits/search",
            params={"address": address, "page": page, "size": size},
            cache_key=f"seumter:search:{address}:{page}",
        )

    async def get_building_register(self, pnu: str) -> dict:
        """건축물대장을 조회한다."""
        return await self._request(
            "GET",
            "/registers",
            params={"pnu": pnu},
            cache_key=f"seumter:register:{pnu}",
            cache_ttl=3600,
        )

    async def get_permit_status(self, permit_number: str) -> dict:
        """인허가 진행상태를 조회한다."""
        return await self._request(
            "GET",
            "/permits/status",
            params={"permitNo": permit_number},
            cache_key=f"seumter:status:{permit_number}",
            cache_ttl=300,  # 5분 캐시 (상태 변경 빈번)
        )
