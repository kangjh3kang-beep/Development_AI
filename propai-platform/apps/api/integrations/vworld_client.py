"""V-World API 클라이언트.

국토정보플랫폼 — 토지/건물 정보, 용도지역, 지하시설물, 주소 변환 등.
API 문서: https://www.vworld.kr/dev/v4dv_apilocallist2.do
"""

from typing import Any

import structlog

from apps.api.integrations.base_client import BaseAPIClient

logger = structlog.get_logger(__name__)

# 지하시설물 유형 매핑
_FACILITY_TYPE_MAP: dict[str, str] = {
    "01": "가스",
    "02": "전기",
    "03": "통신",
    "04": "상수도",
    "05": "하수도",
    "06": "난방",
    "07": "송유",
}


class VWorldClient(BaseAPIClient):
    """V-World 공간정보 API 클라이언트."""

    service_name = "vworld"
    base_url = "https://api.vworld.kr"

    def _default_headers(self) -> dict[str, str]:
        return {"User-Agent": "PropAI/30.0", "Accept": "application/json"}

    # ──────────────────────────────────────
    # 폴백 (API 오류 시 안전한 기본값)
    # ──────────────────────────────────────

    @staticmethod
    def _parcel_fallback(pnu: str, reason: str = "조회 실패") -> dict[str, Any]:
        """API 조회 실패 시 안전한 필지 기본값을 반환한다."""
        logger.warning("VWorld 필지 정보 폴백 사용", pnu=pnu, reason=reason)
        return {
            "pnu": pnu,
            "address": "",
            "land_area_m2": 0.0,
            "land_category": "알 수 없음",
            "geometry": {},
            "centroid_lat": None,
            "centroid_lon": None,
            "fallback": True,
            "error": reason,
        }

    @staticmethod
    def _land_use_fallback(pnu: str, reason: str = "조회 실패") -> dict[str, Any]:
        """API 조회 실패 시 안전한 용도지역 기본값을 반환한다."""
        return {
            "pnu": pnu,
            "land_use_zone": "알 수 없음",
            "land_use_district": "",
            "far_limit": 0.0,
            "bcr_limit": 0.0,
            "fallback": True,
            "error": reason,
        }

    @staticmethod
    def _geocode_fallback(address: str, reason: str = "좌표 변환 실패") -> dict[str, Any]:
        """주소-좌표 변환 실패 시 안전한 기본값을 반환한다."""
        return {
            "lat": 0.0,
            "lon": 0.0,
            "address": address,
            "fallback": True,
            "error": reason,
        }

    # ──────────────────────────────────────
    # API 메서드
    # ──────────────────────────────────────

    async def get_land_info(self, pnu: str) -> dict[str, Any]:
        """필지 토지 정보를 조회한다."""
        try:
            return await self._request(
                "GET",
                "/ned/data/getLandUseAttr",
                params={
                    "key": self.settings.vworld_api_key,
                    "pnu": pnu,
                    "format": "json",
                    "numOfRows": "10",
                },
                cache_key=f"vworld:land:{pnu}",
                cache_ttl=86400,
            )
        except Exception as e:
            logger.warning("토지 정보 조회 실패", pnu=pnu, error=str(e))
            return self._parcel_fallback(pnu, str(e))

    async def get_building_info(self, pnu: str) -> dict[str, Any]:
        """건물 정보를 조회한다."""
        try:
            return await self._request(
                "GET",
                "/ned/data/getBuildingAttr",
                params={
                    "key": self.settings.vworld_api_key,
                    "pnu": pnu,
                    "format": "json",
                },
                cache_key=f"vworld:building:{pnu}",
                cache_ttl=86400,
            )
        except Exception as e:
            logger.warning("건물 정보 조회 실패", pnu=pnu, error=str(e))
            return {}

    async def get_parcel_info(self, pnu: str) -> dict[str, Any]:
        """필지 고유번호(PNU)로 필지 정보(경계 포함)를 조회한다."""
        try:
            data = await self._request(
                "GET",
                "/req/data",
                params={
                    "service": "data",
                    "version": "2.0",
                    "request": "GetFeature",
                    "key": self.settings.vworld_api_key,
                    "data": "LP_PA_CBND_BUBUN",
                    "attrFilter": f"pnu:=:{pnu}",
                    "geometry": "true",
                    "attribute": "true",
                    "format": "json",
                    "errorformat": "json",
                },
                cache_key=f"vworld:parcel:{pnu}",
                cache_ttl=86400,
            )
            return self._parse_parcel_response(data, pnu)
        except Exception as e:
            return self._parcel_fallback(pnu, str(e))

    async def get_land_use_zone(self, pnu: str) -> dict[str, Any]:
        """용도지역(건폐율/용적률 제한 포함)을 조회한다."""
        try:
            data = await self._request(
                "GET",
                "/req/data",
                params={
                    "service": "data",
                    "version": "2.0",
                    "request": "GetFeature",
                    "key": self.settings.vworld_api_key,
                    "data": "LT_C_UD801",
                    "attrFilter": f"pnu:=:{pnu}",
                    "format": "json",
                },
                cache_key=f"vworld:landuse:{pnu}",
                cache_ttl=86400,
            )
            return self._parse_land_use_response(data, pnu)
        except Exception as e:
            return self._land_use_fallback(pnu, str(e))

    async def get_underground_facilities(
        self, lat: float, lon: float, radius_m: int = 50,
    ) -> list[dict[str, Any]]:
        """지하시설물(가스/전기/통신/상수도/하수도)을 조회한다."""
        try:
            data = await self._request(
                "GET",
                "/req/data",
                params={
                    "service": "data",
                    "version": "2.0",
                    "request": "GetFeature",
                    "key": self.settings.vworld_api_key,
                    "data": "LT_C_UGPIPE",
                    "geometry": "true",
                    "crs": "EPSG:4326",
                    "buffer": str(radius_m),
                    "geomFilter": f"point({lon} {lat})",
                    "format": "json",
                },
                cache_key=f"vworld:underground:{lat:.5f}:{lon:.5f}:{radius_m}",
                cache_ttl=86400,
            )
            return self._parse_underground_response(data)
        except Exception as e:
            logger.warning("지하시설물 조회 실패", lat=lat, lon=lon, error=str(e))
            return []

    async def geocode(self, address: str) -> dict[str, Any]:
        """주소를 좌표로 변환한다."""
        try:
            data = await self._request(
                "GET",
                "/req/address",
                params={
                    "key": self.settings.vworld_api_key,
                    "service": "address",
                    "request": "getcoord",
                    "address": address,
                    "type": "ROAD",
                    "format": "json",
                },
                cache_key=f"vworld:geocode:{address}",
                cache_ttl=604800,
            )
            return self._parse_geocode_response(data, address)
        except Exception as e:
            return self._geocode_fallback(address, str(e))

    async def address_to_coordinates(self, address: str) -> dict[str, Any]:
        """주소를 좌표(lat, lon)로 변환한다.

        geocode()의 명시적 래퍼. 어떤 오류가 발생하더라도
        예외를 던지지 않고 {"lat": 0.0, "lon": 0.0, ...} 형태의 안전한
        Fallback을 반환한다.
        """
        return await self.geocode(address)

    # ──────────────────────────────────────
    # 응답 파싱 유틸
    # ──────────────────────────────────────

    def _extract_features(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """V-World 공통: response.result.featureCollection.features 를 추출한다."""
        try:
            result: list[dict[str, Any]] = (
                data.get("response", {})
                .get("result", {})
                .get("featureCollection", {})
                .get("features", [])
            )
            return result
        except (AttributeError, TypeError):
            return []

    def _parse_parcel_response(self, data: dict[str, Any], pnu: str) -> dict[str, Any]:
        """VWORLD 필지 응답을 표준화한다."""
        features = self._extract_features(data)
        if not features:
            return self._parcel_fallback(pnu, "필지 정보 없음")

        prop = features[0].get("properties", {})
        geom = features[0].get("geometry", {})
        return {
            "pnu": pnu,
            "address": prop.get("addr", ""),
            "land_area_m2": float(prop.get("area", 0) or 0),
            "land_category": prop.get("lndcgr_nm", ""),
            "geometry": geom,
            "centroid_lat": prop.get("rep_lat"),
            "centroid_lon": prop.get("rep_lon"),
        }

    def _parse_land_use_response(self, data: dict[str, Any], pnu: str) -> dict[str, Any]:
        """용도지역 응답을 표준화한다."""
        features = self._extract_features(data)
        if not features:
            return self._land_use_fallback(pnu, "용도지역 정보 없음")

        prop = features[0].get("properties", {})
        return {
            "pnu": pnu,
            "land_use_zone": prop.get("uname", ""),
            "land_use_district": prop.get("dgubname", ""),
            "far_limit": float(prop.get("flrrt", 0) or 0),
            "bcr_limit": float(prop.get("bldcovrat", 0) or 0),
        }

    def _parse_geocode_response(self, data: dict[str, Any], address: str) -> dict[str, Any]:
        """주소 변환 응답을 표준화한다. KeyError에 안전."""
        try:
            resp = data.get("response", {})
            if resp.get("status") == "OK":
                result = resp.get("result", {})
                point = result.get("point", {})
                lat = float(point.get("y", 0) or 0)
                lon = float(point.get("x", 0) or 0)
                if lat != 0.0 and lon != 0.0:
                    return {"lat": lat, "lon": lon, "address": address}
        except (ValueError, TypeError, AttributeError):
            pass
        return self._geocode_fallback(address)

    def _parse_underground_response(
        self, data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """지하시설물 응답을 표준화한다."""
        features = self._extract_features(data)
        result: list[dict[str, Any]] = []
        for feat in features:
            prop = feat.get("properties", {})
            type_code = str(prop.get("pipe_tp", ""))
            result.append({
                "facility_type": _FACILITY_TYPE_MAP.get(type_code, type_code),
                "material": prop.get("pipe_mat", ""),
                "diameter_mm": float(prop.get("pipe_dn", 0) or 0),
                "depth_m": float(prop.get("pipe_dep", 0) or 0),
                "geometry": feat.get("geometry", {}),
            })
        return result
