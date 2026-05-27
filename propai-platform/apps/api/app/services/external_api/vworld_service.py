import math

import httpx
from typing import Optional, List, Dict, Any
from app.core.config import settings
import structlog

logger = structlog.get_logger()

def _wgs84_area_to_sqm(area_deg2: float, center_lat: float) -> float:
    """WGS84 도(degree) 단위 면적을 m² 단위로 변환."""
    lat_m = 111_320  # 위도 1도 ≈ 111,320m (거의 일정)
    lon_m = 111_320 * math.cos(math.radians(center_lat))  # 경도는 위도에 따라 변함
    return area_deg2 * lat_m * lon_m


class VWorldService:
    """VWORLD API (국토지리정보원) 연동 서비스"""
    BASE_URL = settings.VWORLD_BASE_URL

    async def get_parcel_by_pnu(self, pnu_code: str) -> Optional[Dict]:
        """PNU 코드로 필지 정보 조회"""
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": "LP_PA_CBND_BUBUN",
            "key": settings.VWORLD_API_KEY,
            "format": "json",
            "crs": "EPSG:4326",
            "attrFilter": f"pnu:=:{pnu_code}",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(f"{self.BASE_URL}/data", params=params)
                resp.raise_for_status()
                data = resp.json()
                features = data.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
                return features[0] if features else None
            except httpx.HTTPStatusError as e:
                logger.error("VWORLD HTTP 오류", pnu=pnu_code, status=e.response.status_code)
                return None
            except httpx.RequestError as e:
                logger.error("VWORLD 네트워크 오류", pnu=pnu_code, error=str(e))
                return None

    async def merge_parcels_gis_union(self, pnu_codes: List[str]) -> Optional[Dict]:
        """다필지 GIS Union 통합 경계 산출"""
        geometries = []
        for pnu in pnu_codes:
            parcel = await self.get_parcel_by_pnu(pnu)
            if parcel:
                geometries.append(parcel.get("geometry"))
        if not geometries:
            return None
        from shapely.geometry import shape, mapping
        from shapely.ops import unary_union
        shapes = [shape(g) for g in geometries if g]
        merged = unary_union(shapes)
        center_lat = merged.centroid.y
        return {
            "merged_geometry": mapping(merged),
            "total_area_sqm": _wgs84_area_to_sqm(merged.area, center_lat),
            "parcel_count": len(pnu_codes)
        }

    async def get_land_use_zone(self, x: float, y: float) -> Optional[Dict]:
        """좌표 기반 용도지역 조회"""
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": "LT_C_LANDREG",
            "key": settings.VWORLD_API_KEY,
            "format": "json",
            "crs": "EPSG:4326",
            "geomFilter": f"BOX({x-0.001},{y-0.001},{x+0.001},{y+0.001})",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.get(f"{self.BASE_URL}/data", params=params)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error("용도지역 HTTP 오류", status=e.response.status_code)
                return None
            except httpx.RequestError as e:
                logger.error("용도지역 네트워크 오류", error=str(e))
                return None
