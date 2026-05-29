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
        async with httpx.AsyncClient(timeout=30.0, headers=self.HEADERS) as client:
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

    # VWORLD 데이터 API는 Referer 헤더로 도메인 검증
    # 등록 도메인: developmentai-production.up.railway.app
    HEADERS = {"Referer": "https://developmentai-production.up.railway.app"}

    async def geocode_address(self, address: str) -> Optional[Dict]:
        """주소를 좌표+PNU로 변환 (지오코딩).

        PARCEL 타입 우선 시도 (PNU 포함) → 실패 시 ROAD 타입 폴백.
        """
        if not settings.VWORLD_API_KEY:
            return None

        vworld_key = settings.VWORLD_API_KEY
        logger.info(
            "VWORLD geocode 시작: address=%s, key_len=%d, key_prefix=%s",
            address[:30], len(vworld_key) if vworld_key else 0,
            vworld_key[:8] if vworld_key and len(vworld_key) > 8 else "EMPTY",
        )

        async with httpx.AsyncClient(timeout=30.0, headers=self.HEADERS) as client:
            # PARCEL 타입 우선 (PNU가 level4LC에 포함됨)
            for addr_type in ["PARCEL", "ROAD"]:
                try:
                    params = {
                        "service": "address",
                        "request": "getcoord",
                        "key": settings.VWORLD_API_KEY,
                        "address": address,
                        "type": addr_type,
                        "format": "json",
                    }
                    resp = await client.get(f"{self.BASE_URL}/address", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    response = data.get("response", {})
                    if response.get("status") != "OK":
                        logger.warning(
                            "VWORLD 지오코딩 NOT OK (%s): %s — status=%s, msg=%s",
                            addr_type, address[:30],
                            response.get("status"), response.get("error", {}).get("text", ""),
                        )
                        continue

                    point = response.get("result", {}).get("point", {})
                    lat = float(point.get("y", 0) or 0)
                    lon = float(point.get("x", 0) or 0)
                    if lat == 0 and lon == 0:
                        continue

                    # PNU 추출: PARCEL → level4LC, ROAD → level4AC
                    structure = response.get("refined", {}).get("structure", {})
                    pnu = structure.get("level4LC") or None

                    return {"lat": lat, "lon": lon, "pnu": pnu, "address": address}
                except Exception as e:
                    logger.error(
                        "VWORLD 지오코딩 실패 (%s): %s — error=%s, type=%s",
                        addr_type, address[:30], str(e)[:300], type(e).__name__,
                    )
                    continue
            return None

    async def get_land_info(self, pnu: str) -> Optional[Dict]:
        """PNU로 토지정보(지목, 면적, 소유구분, 이용상황, 공시지가) 조회"""
        if not settings.VWORLD_API_KEY:
            return None
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": "LP_PA_CBND_BUBUN",
            "key": settings.VWORLD_API_KEY,
            "format": "json",
            "crs": "EPSG:4326",
            "attrFilter": f"pnu:=:{pnu}",
            "geometry": "true",
            "attribute": "true",
        }
        async with httpx.AsyncClient(timeout=30.0, headers=self.HEADERS) as client:
            try:
                resp = await client.get(f"{self.BASE_URL}/data", params=params)
                resp.raise_for_status()
                data = resp.json()
                features = (
                    data.get("response", {})
                    .get("result", {})
                    .get("featureCollection", {})
                    .get("features", [])
                )
                if not features:
                    return None
                props = features[0].get("properties", {})
                geom = features[0].get("geometry", {})
                return {
                    "properties": {
                        "area": float(props.get("area", 0) or 0),
                        "jimok": props.get("lndcgr_nm", ""),
                        "use_zone": props.get("land_use", ""),
                        "official_price": float(props.get("pblntf_pc", 0) or 0),
                        "owner_type": props.get("own_gbn_nm", ""),
                        "land_use_situation": props.get("lnd_crnt_nm", ""),
                        "road_side": props.get("road_side_nm", ""),
                        "terrain": props.get("tpgrp_nm", ""),
                        "address": props.get("addr", ""),
                    },
                    "geometry": geom,
                }
            except Exception as e:
                logger.error("VWORLD 토지정보 조회 실패", pnu=pnu, error=str(e))
                return None

    async def get_land_use_districts(self, pnu: str) -> List[Dict]:
        """PNU로 용도지구/구역 (UD802, UD803) 목록 조회"""
        results = []
        for data_code, category in [("LT_C_UD802", "용도지구"), ("LT_C_UD803", "용도구역")]:
            try:
                params = {
                    "service": "data",
                    "request": "GetFeature",
                    "data": data_code,
                    "key": settings.VWORLD_API_KEY,
                    "format": "json",
                    "attrFilter": f"pnu:=:{pnu}",
                }
                async with httpx.AsyncClient(timeout=15.0, headers=self.HEADERS) as client:
                    resp = await client.get(f"{self.BASE_URL}/data", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    features = (
                        data.get("response", {})
                        .get("result", {})
                        .get("featureCollection", {})
                        .get("features", [])
                    )
                    for feat in features:
                        props = feat.get("properties", {})
                        results.append({
                            "category": category,
                            "name": props.get("uname", "") or props.get("gname", ""),
                            "code": props.get("ucode", "") or props.get("gcode", ""),
                        })
            except Exception:
                pass  # 용도지구 없는 필지는 정상
        return results

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
        async with httpx.AsyncClient(timeout=30.0, headers=self.HEADERS) as client:
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

    # ── VWORLD NED API (공시지가, 토지이용계획) ──
    NED_BASE_URL = "https://api.vworld.kr/ned/data"

    async def get_individual_land_price(self, pnu: str, year: int = 2025) -> Optional[Dict]:
        """PNU 기반 개별공시지가 조회.

        반환: { pnu, year, price_per_sqm, land_code, land_name, ... }
        """
        if not settings.VWORLD_API_KEY:
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=self.HEADERS) as client:
                resp = await client.get(
                    f"{self.NED_BASE_URL}/getIndvdLandPriceAttr",
                    params={
                        "key": settings.VWORLD_API_KEY,
                        "pnu": pnu,
                        "stdrYear": str(year),
                        "format": "json",
                        "numOfRows": "1",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                fields = data.get("indvdLandPrices", {}).get("field", [])
                if not fields:
                    return None
                item = fields[0] if isinstance(fields, list) else fields
                return {
                    "pnu": item.get("pnu", pnu),
                    "year": int(item.get("stdrYear", year)),
                    "price_per_sqm": int(item.get("pblntfPclnd", 0) or 0),
                    "land_code": item.get("ldCode", ""),
                    "land_name": item.get("ldCodeNm", ""),
                    "last_updated": item.get("lastUpdtDt", ""),
                    "is_standard_land": item.get("stdLandAt", "") == "Y",
                }
        except Exception as e:
            logger.error("개별공시지가 조회 실패: %s (%s)", pnu, str(e))
            return None

    async def get_land_use_plan(self, pnu: str) -> List[Dict]:
        """PNU 기반 토지이용계획 조회 (용도지역/지구/구역 + 기타 규제 전부).

        하나의 필지에 중첩된 모든 규제를 배열로 반환.
        예: [대공방어협조구역, 도시지역, 제2종일반주거지역, ...]
        """
        if not settings.VWORLD_API_KEY:
            return []
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=self.HEADERS) as client:
                resp = await client.get(
                    f"{self.NED_BASE_URL}/getLandUseAttr",
                    params={
                        "key": settings.VWORLD_API_KEY,
                        "pnu": pnu,
                        "format": "json",
                        "numOfRows": "30",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                fields = data.get("landUses", {}).get("field", [])
                if not fields:
                    return []
                if not isinstance(fields, list):
                    fields = [fields]
                results = []
                for item in fields:
                    results.append({
                        "district_name": item.get("prposAreaDstrcCodeNm", ""),
                        "district_code": item.get("prposAreaDstrcCode", ""),
                        "conflict_status": item.get("cnflcAtNm", ""),
                        "land_name": item.get("ldCodeNm", ""),
                        "register_date": item.get("registDt", ""),
                        "last_updated": item.get("lastUpdtDt", ""),
                    })
                return results
        except Exception as e:
            logger.error("토지이용계획 조회 실패: %s (%s)", pnu, str(e))
            return []
