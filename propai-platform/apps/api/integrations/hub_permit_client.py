"""건축HUB 주택인허가정보 API 클라이언트.

국토교통부_건축HUB_주택인허가정보 서비스(data.go.kr)와 연동하여
주택 인허가와 관련된 기본개요, 동별개요, 층별개요 등의 속성정보를 조회한다.
"""

from typing import Any

import structlog

from apps.api.integrations.base_client import BaseAPIClient

logger = structlog.get_logger(__name__)


class HubPermitClient(BaseAPIClient):
    """건축HUB 주택인허가 API 클라이언트."""

    service_name = "hub_permit"
    base_url = "https://apis.data.go.kr"
    
    # 공공데이터포털 건축HUB 주택인허가 기본 경로
    _HUB_PERMIT_PATH = "/1613000/HsPmsHubService"

    async def _get_data(self, endpoint: str, params: dict[str, Any], cache_key: str, cache_ttl: int = 86400) -> list[dict[str, Any]]:
        """공통 API 호출 메서드."""
        # 기본 공통 파라미터
        base_params = {
            "serviceKey": self.settings.hub_permit_api_key or self.settings.molit_api_key,
            "pageNo": "1",
            "numOfRows": "100",
            "_type": "json",
        }
        # 파라미터 병합
        base_params.update(params)

        try:
            data = await self._request(
                "GET",
                f"{self._HUB_PERMIT_PATH}/{endpoint}",
                params=base_params,
                cache_key=cache_key,
                cache_ttl=cache_ttl,
            )
            return self._extract_items(data)
        except Exception as e:
            logger.warning(f"건축HUB 주택인허가 조회 실패: {endpoint}", error=str(e))
            return []

    @staticmethod
    def _extract_items(data: dict) -> list[dict]:
        """응답에서 item 배열을 추출한다."""
        body = (data.get("response") or {}).get("body")
        if not body:
            return []
        items = (body.get("items") or {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        return items if isinstance(items, list) else []

    async def get_basis_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """국토교통부_주택인허가 기본개요 조회.
        
        Args:
            sigungu_cd: 시군구코드 (예: 11680)
            bjdong_cd: 법정동코드 (선택)
        """
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd:
            params["bjdongCd"] = bjdong_cd
            
        return await self._get_data(
            "getHpBasisOulnInfo",
            params,
            cache_key=f"hub_permit:basis:{sigungu_cd}:{bjdong_cd}",
        )

    async def get_dong_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 동별개요 조회.
        
        Args:
            sigungu_cd: 시군구코드
            bjdong_cd: 법정동코드
        """
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd:
            params["bjdongCd"] = bjdong_cd
            
        return await self._get_data(
            "getHpDongOulnInfo",
            params,
            cache_key=f"hub_permit:dong:{sigungu_cd}:{bjdong_cd}",
        )

    async def get_flr_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 층별개요 조회.
        
        Args:
            sigungu_cd: 시군구코드
            bjdong_cd: 법정동코드
        """
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd:
            params["bjdongCd"] = bjdong_cd
            
        return await self._get_data(
            "getHpFlrOulnInfo",
            params,
            cache_key=f"hub_permit:flr:{sigungu_cd}:{bjdong_cd}",
        )

    # --- 상세 정보 조회 추가 ---
    
    async def get_ho_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 호별개요 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getHpHoOulnInfo", params, cache_key=f"hub_permit:ho:{sigungu_cd}:{bjdong_cd}")

    async def get_sbsd_fcl_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 부대시설 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getHpSbsdFclInfo", params, cache_key=f"hub_permit:sbsd:{sigungu_cd}:{bjdong_cd}")

    async def get_pklot_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 주차장 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getHpPklotInfo", params, cache_key=f"hub_permit:pklot:{sigungu_cd}:{bjdong_cd}")

    async def get_expos_pubuse_area_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 전유공용면적 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getHpExposPubuseAreaInfo", params, cache_key=f"hub_permit:expos:{sigungu_cd}:{bjdong_cd}")

    async def get_plat_plc_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 대지위치 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getHpPlatPlcInfo", params, cache_key=f"hub_permit:plat:{sigungu_cd}:{bjdong_cd}")

    async def get_jijigu_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_주택인허가 지역지구구역 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getHpJijiguInfo", params, cache_key=f"hub_permit:jijigu:{sigungu_cd}:{bjdong_cd}")


class ArchPermitClient(BaseAPIClient):
    """건축HUB 건축인허가 API 클라이언트."""

    service_name = "arch_permit"
    base_url = "https://apis.data.go.kr"
    
    # 공공데이터포털 건축HUB 건축인허가 기본 경로
    _ARCH_PERMIT_PATH = "/1613000/ArchPmsHubService"

    async def _get_data(self, endpoint: str, params: dict[str, Any], cache_key: str, cache_ttl: int = 86400) -> list[dict[str, Any]]:
        """공통 API 호출 메서드."""
        base_params = {
            "serviceKey": self.settings.hub_permit_api_key or self.settings.molit_api_key,
            "pageNo": "1",
            "numOfRows": "100",
            "_type": "json",
        }
        base_params.update(params)

        try:
            data = await self._request(
                "GET",
                f"{self._ARCH_PERMIT_PATH}/{endpoint}",
                params=base_params,
                cache_key=cache_key,
                cache_ttl=cache_ttl,
            )
            return HubPermitClient._extract_items(data)
        except Exception as e:
            logger.warning(f"건축HUB 건축인허가 조회 실패: {endpoint}", error=str(e))
            return []

    async def get_ap_basis_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 기본개요 조회.
        
        Args:
            sigungu_cd: 시군구코드
            bjdong_cd: 법정동코드
        """
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd:
            params["bjdongCd"] = bjdong_cd
            
        return await self._get_data(
            "getApBasisOulnInfo",
            params,
            cache_key=f"arch_permit:basis:{sigungu_cd}:{bjdong_cd}",
        )

    async def get_ap_dong_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 동별개요 조회.
        
        Args:
            sigungu_cd: 시군구코드
            bjdong_cd: 법정동코드
        """
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd:
            params["bjdongCd"] = bjdong_cd
            
        return await self._get_data(
            "getApDongOulnInfo",
            params,
            cache_key=f"arch_permit:dong:{sigungu_cd}:{bjdong_cd}",
        )

    async def get_ap_flr_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 층별개요 조회.
        
        Args:
            sigungu_cd: 시군구코드
            bjdong_cd: 법정동코드
        """
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd:
            params["bjdongCd"] = bjdong_cd
            
        return await self._get_data(
            "getApFlrOulnInfo",
            params,
            cache_key=f"arch_permit:flr:{sigungu_cd}:{bjdong_cd}",
        )

    # --- 상세 정보 조회 추가 ---

    async def get_ap_ho_ouln_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 호별개요 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApHoOulnInfo", params, cache_key=f"arch_permit:ho:{sigungu_cd}:{bjdong_cd}")

    async def get_ap_pklot_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 주차장 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApPklotInfo", params, cache_key=f"arch_permit:pklot:{sigungu_cd}:{bjdong_cd}")

    async def get_ap_atch_pklot_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 부설주차장 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApAtchPklotInfo", params, cache_key=f"arch_permit:atch_pklot:{sigungu_cd}:{bjdong_cd}")

    async def get_ap_expos_pubuse_area_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 전유공용면적 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApExposPubuseAreaInfo", params, cache_key=f"arch_permit:expos:{sigungu_cd}:{bjdong_cd}")

    async def get_ap_plat_plc_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 대지위치 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApPlatPlcInfo", params, cache_key=f"arch_permit:plat:{sigungu_cd}:{bjdong_cd}")

    async def get_ap_jijigu_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 지역지구구역 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApJijiguInfo", params, cache_key=f"arch_permit:jijigu:{sigungu_cd}:{bjdong_cd}")

    async def get_ap_imprpr_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 대수선 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApImprprInfo", params, cache_key=f"arch_permit:imprpr:{sigungu_cd}:{bjdong_cd}")

    async def get_ap_hs_tp_info(self, sigungu_cd: str, bjdong_cd: str = "") -> list[dict[str, Any]]:
        """건축HUB_건축인허가 주택유형 조회 (상세)."""
        params = {"sigunguCd": sigungu_cd}
        if bjdong_cd: params["bjdongCd"] = bjdong_cd
        return await self._get_data("getApHsTpInfo", params, cache_key=f"arch_permit:hstp:{sigungu_cd}:{bjdong_cd}")
