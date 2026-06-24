import math
import re

import httpx
from typing import Optional, List, Dict, Any
from app.core.config import settings
import structlog

logger = structlog.get_logger()

# 필지(지적도) 프로세스 캐시 — PNU→feature(dict). 필지는 거의 불변이라 대량 다필지
# 분석 시 동일 PNU 반복/중복 호출을 제거(N+1 완화). 무한증식 방지로 상한 둠.
_PARCEL_CACHE: Dict[str, dict] = {}
_PARCEL_CACHE_MAX = 20000


def _parcel_cache_put(pnu: str, value: dict) -> None:
    """필지 캐시에 저장. 상한 초과 시 단순 초기화(LRU 미도입 — 정적 데이터라 충분)."""
    if len(_PARCEL_CACHE) >= _PARCEL_CACHE_MAX:
        _PARCEL_CACHE.clear()
    _PARCEL_CACHE[pnu] = value


async def _vworld_get_json(client, url: str, params: dict, *, retries: int = 2) -> Optional[dict]:
    """VWorld GET → JSON. 대량 동시호출 시 레이트리밋(429)·일시오류(5xx)·타임아웃을
    지수 백오프+지터로 재시도한다(무목업: 끝내 실패하면 None, 가짜 생성 금지).
    Retry-After 헤더가 있으면 우선 적용. 단일 호출에는 영향 없음(성공 시 즉시 반환).
    """
    import asyncio
    import random

    for attempt in range(retries + 1):
        try:
            resp = await client.get(url, params=params)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                ra = resp.headers.get("Retry-After")
                if ra and ra.replace(".", "", 1).isdigit():
                    delay = float(ra)
                else:
                    delay = (2 ** attempt) + random.uniform(0, 0.3)
                logger.warning("VWORLD 재시도", status=resp.status_code, attempt=attempt, delay=round(delay, 2))
                await asyncio.sleep(min(delay, 5.0))
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.RequestError) as e:
            if attempt < retries:
                await asyncio.sleep((2 ** attempt) + random.uniform(0, 0.3))
                continue
            logger.error("VWORLD 요청 실패(재시도 소진)", error=str(e))
            return None
        except httpx.HTTPStatusError as e:
            logger.error("VWORLD HTTP 오류", status=e.response.status_code)
            return None
    return None


def _wgs84_area_to_sqm(area_deg2: float, center_lat: float) -> float:
    """WGS84 도(degree) 단위 면적을 m² 단위로 변환."""
    lat_m = 111_320  # 위도 1도 ≈ 111,320m (거의 일정)
    lon_m = 111_320 * math.cos(math.radians(center_lat))  # 경도는 위도에 따라 변함
    return area_deg2 * lat_m * lon_m


class VWorldService:
    """VWORLD API (국토지리정보원) 연동 서비스"""
    BASE_URL = settings.VWORLD_BASE_URL

    async def get_parcel_by_pnu(self, pnu_code: str) -> Optional[dict]:
        """PNU 코드로 필지 정보 조회.

        필지(지적도)는 거의 바뀌지 않으므로 프로세스 캐시로 중복/반복 호출을 제거한다
        (대량 다필지 분석 시 동일 PNU 재조회·N+1 완화). 캐시는 PNU→feature.
        """
        if not pnu_code:
            return None
        cached = _PARCEL_CACHE.get(pnu_code)
        if cached is not None:
            # 빈 결과(None 못찾음)도 빈 dict로 캐시해 반복 실패호출 방지.
            return cached or None
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": "LP_PA_CBND_BUBUN",
            "key": settings.VWORLD_API_KEY,
            "format": "json",
            "crs": "EPSG:4326",
            "attrFilter": f"pnu:=:{pnu_code}",
        }
        async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
            data = await _vworld_get_json(client, f"{self.BASE_URL}/data", params)
            if data is None:
                return None  # 재시도 소진/오류 — 캐시하지 않음(일시오류일 수 있음)
            features = data.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
            result = features[0] if features else None
            _parcel_cache_put(pnu_code, result or {})
            return result

    async def merge_parcels_gis_union(self, pnu_codes: list[str]) -> Optional[dict]:
        """다필지 GIS Union 통합 경계 산출.

        대량 다필지에서 필지 경계를 PNU별로 순차 조회하면 N+1 지연(수백 필지=수십 초)이
        발생하므로, 동시성 제한(Semaphore) 하에 병렬 조회한다(캐시와 결합해 반복 제거).
        """
        import asyncio

        sem = asyncio.Semaphore(8)  # VWorld 보호용 동시 호출 상한

        async def _one(pnu: str):
            async with sem:
                return await self.get_parcel_by_pnu(pnu)

        parcels = await asyncio.gather(*[_one(p) for p in pnu_codes], return_exceptions=True)
        geometries = [
            p.get("geometry") for p in parcels
            if isinstance(p, dict) and p.get("geometry")
        ]
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
    HEADERS = {"Referer": "https://www.4t8t.net"}

    async def search_address(self, query: str, size: int = 8) -> list[dict]:
        """지번/도로명 검색 — 다음 주소검색처럼 후보 목록을 반환(자동완성용).

        VWORLD 검색 API(service=search). 지번(parcel) 우선, 부족하면 도로명(road) 보강.
        반환: [{address(지번주소), road_address, pnu, lat, lon, kind}] (최대 size).
        키 미설정/무자료/오류 → [](가짜 후보 생성 금지).
        """
        q = (query or "").strip()
        if not settings.VWORLD_API_KEY or len(q) < 2:
            return []

        results: list[dict] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=10.0, headers=self.HEADERS) as client:
            for category in ("parcel", "road"):
                if len(results) >= size:
                    break
                try:
                    params = {
                        "service": "search", "request": "search", "version": "2.0",
                        "crs": "EPSG:4326", "size": str(size), "page": "1",
                        "query": q, "type": "address", "category": category,
                        "format": "json", "key": settings.VWORLD_API_KEY,
                    }
                    resp = await client.get(f"{self.BASE_URL}/search", params=params)
                    resp.raise_for_status()
                    response = resp.json().get("response", {})
                    if response.get("status") != "OK":
                        continue
                    items = response.get("result", {}).get("items", []) or []
                    for it in items:
                        addr = it.get("address", {}) or {}
                        parcel = addr.get("parcel") or ""
                        road = addr.get("road") or ""
                        label = parcel or road
                        if not label or label in seen:
                            continue
                        seen.add(label)
                        point = it.get("point", {}) or {}
                        # parcel 검색의 id는 PNU(19자리). road는 PNU 없음.
                        rid = str(it.get("id", "") or "")
                        pnu = rid if (category == "parcel" and len(rid) >= 19) else None
                        results.append({
                            "address": parcel or road,
                            "road_address": road,
                            "pnu": pnu,
                            "lat": float(point.get("y", 0) or 0) or None,
                            "lon": float(point.get("x", 0) or 0) or None,
                            "kind": "지번" if category == "parcel" else "도로명",
                        })
                        if len(results) >= size:
                            break
                except Exception as e:  # noqa: BLE001
                    logger.warning("VWORLD 주소검색 실패(%s): %s (%s)", category, q[:30], str(e)[:200])
                    continue
        return results[:size]

    async def geocode_address(self, address: str) -> Optional[dict]:
        """주소를 좌표+PNU로 변환 (지오코딩).

        PARCEL 타입 우선 시도 (PNU 포함) → 실패 시 ROAD 타입 폴백.
        """
        if not settings.VWORLD_API_KEY:
            return None

        vworld_key = settings.VWORLD_API_KEY
        # 키 값(prefix 포함)은 로그에 남기지 않는다 — 설정 여부만 기록(부분 키 노출 방지).
        logger.info(
            "VWORLD geocode 시작: address=%s, key_set=%s",
            address[:30], bool(vworld_key),
        )

        async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
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
                    logger.info(
                        "VWORLD 응답 (%s): status_code=%d, len=%d",
                        addr_type, resp.status_code, len(resp.text),
                    )
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

    async def get_land_info(self, pnu: str) -> Optional[dict]:
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
        async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
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

    async def get_parcel_by_point(self, lat: float, lon: float) -> Optional[dict]:
        """좌표(점)가 포함된 필지를 조회 (도로명주소 등 PNU 미확보 시 폴백).

        VWORLD 지적도 LP_PA_CBND_BUBUN에 geomFilter=POINT 질의 → pnu+geometry 반환.
        """
        if not settings.VWORLD_API_KEY or not lat or not lon:
            return None
        params = {
            "service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN",
            "key": settings.VWORLD_API_KEY, "format": "json", "crs": "EPSG:4326",
            "geomFilter": f"POINT({lon} {lat})", "geometry": "true", "attribute": "true",
        }
        async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
            try:
                resp = await client.get(f"{self.BASE_URL}/data", params=params)
                resp.raise_for_status()
                feats = (resp.json().get("response", {}).get("result", {})
                         .get("featureCollection", {}).get("features", []))
                if not feats:
                    return None
                props = feats[0].get("properties", {})
                return {
                    "pnu": props.get("pnu"),
                    "address": props.get("addr", ""),
                    "geometry": feats[0].get("geometry"),
                }
            except Exception as e:  # noqa: BLE001
                logger.error("VWORLD 점 기반 필지 조회 실패: %s,%s (%s)", lat, lon, str(e))
                return None

    async def get_parcels_in_bbox(
        self,
        min_lon: float, min_lat: float, max_lon: float, max_lat: float,
        max_count: int = 100,
    ) -> list[dict]:
        """bbox 내 필지 목록 조회 (geometry + 지목).

        연속지적도(LP_PA_CBND_BUBUN)에서 bbox에 걸치는 필지를 가져온다.
        정밀 접도 분석에서 인접 도로 필지(지목=도로)를 찾는 데 사용된다.

        반환: [{pnu, jimok, geometry(GeoJSON)}, ...]
        """
        if not settings.VWORLD_API_KEY:
            return []
        params = {
            "service": "data",
            "request": "GetFeature",
            "data": "LP_PA_CBND_BUBUN",
            "key": settings.VWORLD_API_KEY,
            "format": "json",
            "crs": "EPSG:4326",
            "geomFilter": f"BOX({min_lon},{min_lat},{max_lon},{max_lat})",
            "geometry": "true",
            "attribute": "true",
            "size": str(max_count),
        }
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
                resp = await client.get(f"{self.BASE_URL}/data", params=params)
                resp.raise_for_status()
                data = resp.json()
                features = (
                    data.get("response", {})
                    .get("result", {})
                    .get("featureCollection", {})
                    .get("features", [])
                )
                parcels = []
                for feat in features:
                    props = feat.get("properties", {})
                    geom = feat.get("geometry")
                    if not geom:
                        continue
                    parcels.append({
                        "pnu": props.get("pnu", ""),
                        "jimok": props.get("lndcgr_nm", ""),
                        "geometry": geom,
                    })
                return parcels
        except Exception as e:
            logger.warning("bbox 필지 조회 실패: %s", str(e))
            return []

    async def get_land_use_districts(self, pnu: str) -> list[dict]:
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
                async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
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

    async def get_planning_facilities(
        self, lat: float, lon: float, radius_m: int = 1000
    ) -> list[dict]:
        """입지 좌표 주변의 도시계획시설(특히 철도·역사·도시철도 계획결정)을 best-effort로 조회한다.

        VWorld data API GetFeature + geomFilter(BBOX)로 좌표 반경 내 도시계획시설을 받아
        철도/역사/도시철도 관련 시설만 골라 '주변 개발계획' 후보로 반환한다.

        ★레이어 코드/속성명이 확실치 않으므로 여러 후보 레이어를 차례로 시도하고, 응답
          status가 OK이고 features가 있을 때만 채택한다(어떤 후보도 안 되면 빈 배열).
        무목업: 키 미설정·무자료·오류 시 가짜 시설을 생성하지 않고 [] 반환(엔드포인트가 정직 note 처리).

        반환: [{type(시설구분), name, status('계획'/'결정'/'운영' 등 속성 그대로·불명시 '확인필요'),
                distance_m, source:'vworld_도시계획시설'}]
        """
        if not settings.VWORLD_API_KEY or not lat or not lon:
            return []

        # 반경(m)을 위경도 박스로 환산(위도 1도 ≈ 111,320m). 경도는 위도 보정.
        d_lat = radius_m / 111_320
        d_lon = radius_m / (111_320 * max(0.1, math.cos(math.radians(lat))))
        min_lat, max_lat = lat - d_lat, lat + d_lat
        min_lon, max_lon = lon - d_lon, lon + d_lon
        box = f"BOX({min_lon},{min_lat},{max_lon},{max_lat})"

        # 도시계획시설 계열 후보 레이어(확실치 않아 순차 시도) — VWorld 데이터목록 기준.
        candidate_layers = [
            "LT_C_UQ111",       # 도시계획시설(점/면)
            "LT_C_UQ112",
            "LT_C_UPISUQ151",   # 도시계획시설(UPIS) 계열
            "LT_C_UPISUQ153",
        ]
        # 철도/역사/도시철도 판별 키워드(시설명/시설구분 기준).
        # 철도 전용 키워드 — ★바 '역'은 '지역(용도지역)'에 오탐되므로 제외. 명시적 철도용어만.
        rail_kw = ("철도", "도시철도", "전철", "지하철", "광역철도", "고속철도", "경전철", "전동차")
        # 용도지역/지구/공원 등은 도시계획시설(철도)이 아니므로 제외(오탐 차단).
        rail_exclude = ("지역", "지구", "공원", "녹지", "광장", "주차장", "학교", "도로")

        def _is_rail(blob: str) -> bool:
            if any(x in blob for x in rail_exclude):
                # 단, '○○역'(역명)이 명시되고 제외어가 우연히 섞인 경우는 철도용어 우선.
                if not any(kw in blob for kw in rail_kw):
                    return False
            if any(kw in blob for kw in rail_kw):
                return True
            # 역명(…역) 패턴 — '지역/역사공원/역세권' 등은 위 제외어로 이미 걸러짐.
            return bool(re.search(r"[가-힣]{1,6}역(\s|$|\d)", blob)) and "지역" not in blob

        facilities: list[dict] = []
        seen: set[str] = set()  # 동일 시설 중복 제거(name+type)
        for layer in candidate_layers:
            params = {
                "service": "data",
                "request": "GetFeature",
                "data": layer,
                "key": settings.VWORLD_API_KEY,
                "format": "json",
                "crs": "EPSG:4326",
                "geomFilter": box,
                "geometry": "true",
                "attribute": "true",
                "size": "100",
            }
            try:
                async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
                    resp = await client.get(f"{self.BASE_URL}/data", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                # 응답 status가 OK일 때만 채택(레이어 미존재·오류면 NOT_FOUND/ERROR).
                status = data.get("response", {}).get("status")
                if status != "OK":
                    continue
                features = (
                    data.get("response", {})
                    .get("result", {})
                    .get("featureCollection", {})
                    .get("features", [])
                )
                if not features:
                    continue
                for feat in features:
                    props = feat.get("properties", {}) or {}
                    # 시설명/시설구분 후보 속성(레이어마다 키가 달라 폭넓게 탐색).
                    name = (
                        props.get("dgm_nm") or props.get("fac_nm") or props.get("uname")
                        or props.get("ntfc_nm") or props.get("ucode_nm") or props.get("name") or ""
                    )
                    fac_type = (
                        props.get("dgm_knd") or props.get("fac_knd") or props.get("ucode_nm")
                        or props.get("knd_nm") or props.get("uname") or ""
                    )
                    blob = f"{name} {fac_type}"
                    # 철도 관련만 채택(용도지역/지구/공원 오탐 제외).
                    if not _is_rail(blob):
                        continue
                    # 상태(계획/결정/운영 등) 속성 그대로 — 없으면 '확인필요'(가짜 단정 금지).
                    fac_status = (
                        props.get("prog_se") or props.get("ntfc_se") or props.get("dgm_se")
                        or props.get("status") or "확인필요"
                    )
                    # 시설 대표 좌표로 입지까지 거리 산출(geometry 첫 좌표 추출).
                    f_lat, f_lon = self._first_coord(feat.get("geometry"))
                    distance_m = None
                    if f_lat is not None and f_lon is not None:
                        distance_m = round(self._haversine_m(lat, lon, f_lat, f_lon))
                    dedup_key = f"{name}|{fac_type}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    facilities.append({
                        "type": str(fac_type).strip() or "도시계획시설",
                        "name": str(name).strip() or "(명칭 미상)",
                        "status": str(fac_status).strip() or "확인필요",
                        "distance_m": distance_m,
                        "source": "vworld_도시계획시설",
                    })
            except Exception as e:  # noqa: BLE001 — 후보 레이어 실패는 다음 후보로(가짜 생성 금지).
                logger.warning("도시계획시설 후보 레이어 조회 실패", layer=layer, error=str(e)[:120])
                continue
        if not facilities:
            logger.info("주변 도시계획시설(철도 등) 자동수집 결과 없음", lat=lat, lon=lon, radius_m=radius_m)
        # 가까운 순으로 정렬(거리 미상은 뒤로).
        facilities.sort(key=lambda f: (f["distance_m"] is None, f["distance_m"] or 0))
        return facilities

    @staticmethod
    def _first_coord(geom: Optional[dict]) -> tuple[Optional[float], Optional[float]]:
        """GeoJSON geometry에서 대표 좌표(lat, lon)를 추출.

        면(역사 부지 등)은 경계 한 꼭짓점보다 **중심점(centroid)**이 입지~시설 거리를
        더 정확히 준다(경계점은 수백 m 오차 가능) → shapely centroid 우선, 실패 시 첫 좌표 폴백.
        """
        if not isinstance(geom, dict):
            return (None, None)
        # 1순위: shapely centroid(면·선의 중심) — 거리 정확도↑
        try:
            from shapely.geometry import shape
            c = shape(geom).centroid
            if c and not c.is_empty:
                return (float(c.y), float(c.x))
        except Exception:  # noqa: BLE001 — geometry 이상/shapely 미가용 시 첫 좌표 폴백
            pass
        # 폴백: 중첩 리스트를 끝까지 파고들어 [lon, lat] 쌍을 찾는다.
        pt = geom.get("coordinates")
        try:
            while isinstance(pt, list) and pt and isinstance(pt[0], list):
                pt = pt[0]
            if isinstance(pt, list) and len(pt) >= 2:
                return (float(pt[1]), float(pt[0]))  # GeoJSON은 [lon, lat] 순서
        except (TypeError, ValueError, IndexError):
            return (None, None)
        return (None, None)

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """두 경위도 좌표 간 거리(m) — 입지~시설 거리 산출용."""
        R = 6_371_000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lam = math.radians(lon2 - lon1)
        a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    async def get_land_use_zone(self, x: float, y: float) -> Optional[dict]:
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
        async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
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

    async def get_individual_land_price(self, pnu: str, year: int = 2025) -> Optional[dict]:
        """PNU 기반 개별공시지가 조회.

        반환: { pnu, year, price_per_sqm, land_code, land_name, ... }
        """
        if not settings.VWORLD_API_KEY:
            return None
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
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

    async def get_land_characteristics(self, pnu: str, year: int = 2025) -> Optional[dict]:
        """PNU 기반 토지특성정보 조회 (NED getLandCharacteristics).

        면적·지목·용도지역(1·2)·이용상황·도로접면·지형·공시지가를 한 번에 반환.
        기존 get_land_info(지적도 LP_PA_CBND_BUBUN)가 면적 0을 주는 필지를 보완하고,
        주소 키워드 감지로 누락되던 용도지역(prposArea1Nm)을 정확히 채운다.
        """
        if not settings.VWORLD_API_KEY:
            return None
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
                resp = await client.get(
                    f"{self.NED_BASE_URL}/getLandCharacteristics",
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
                fields = data.get("landCharacteristicss", {}).get("field", [])
                if not fields:
                    return None
                item = fields[0] if isinstance(fields, list) else fields

                def _nm(v: str | None) -> str:
                    """'지정되지않음'/'해당없음' 등은 빈값 처리."""
                    s = (v or "").strip()
                    return "" if s in ("지정되지않음", "해당없음", "0") else s

                return {
                    "pnu": item.get("pnu", pnu),
                    "year": int(item.get("stdrYear", year) or year),
                    "area_sqm": float(item.get("lndpclAr", 0) or 0),
                    "land_category": item.get("lndcgrCodeNm", "") or "",
                    "zone_type": _nm(item.get("prposArea1Nm")),
                    "zone_type_2": _nm(item.get("prposArea2Nm")),
                    "land_use_situation": item.get("ladUseSittnNm", "") or "",
                    "road_side": item.get("roadSideCodeNm", "") or "",
                    "terrain_height": item.get("tpgrphHgCodeNm", "") or "",
                    "terrain_form": item.get("tpgrphFrmCodeNm", "") or "",
                    "official_price_per_sqm": int(item.get("pblntfPclnd", 0) or 0),
                }
        except Exception as e:
            logger.error("토지특성 조회 실패: %s (%s)", pnu, str(e))
            return None

    async def get_land_use_plan(self, pnu: str) -> list[dict]:
        """PNU 기반 토지이용계획 조회 (용도지역/지구/구역 + 기타 규제 전부).

        하나의 필지에 중첩된 모든 규제를 배열로 반환.
        예: [대공방어협조구역, 도시지역, 제2종일반주거지역, ...]
        """
        if not settings.VWORLD_API_KEY:
            return []
        # ★전수 수집(원칙: 광범위 누락없는 수집): numOfRows=30 단일호출은 중첩규제가 많은 필지에서
        #   무음 절단됐다. totalCount까지 페이지를 순회한다(상한 도달 시 절단 경고).
        results: list[dict] = []
        total: int | None = None
        try:
            async with httpx.AsyncClient(timeout=12.0, headers=self.HEADERS) as client:
                page = 1
                while page <= 10:  # 상한 10×100 = 1000 규제(현실적으로 1페이지 내)
                    resp = await client.get(
                        f"{self.NED_BASE_URL}/getLandUseAttr",
                        params={
                            "key": settings.VWORLD_API_KEY,
                            "pnu": pnu,
                            "format": "json",
                            "numOfRows": "100",
                            "pageNo": str(page),
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    land_uses = data.get("landUses", {}) or {}
                    fields = land_uses.get("field", [])
                    if not isinstance(fields, list):
                        fields = [fields] if fields else []
                    if not fields:
                        break
                    for item in fields:
                        results.append({
                            "district_name": item.get("prposAreaDstrcCodeNm", ""),
                            "district_code": item.get("prposAreaDstrcCode", ""),
                            "conflict_status": item.get("cnflcAtNm", ""),
                            "land_name": item.get("ldCodeNm", ""),
                            "register_date": item.get("registDt", ""),
                            "last_updated": item.get("lastUpdtDt", ""),
                        })
                    tc = land_uses.get("totalCount")
                    try:
                        total = int(tc) if tc not in (None, "") else None
                    except (TypeError, ValueError):
                        total = None
                    if total is None or len(results) >= total:
                        break
                    page += 1
                if total is not None and len(results) < total:
                    logger.warning(
                        "VWorld 토지이용계획 페이지 상한 — 일부 절단: pnu=%s collected=%d total=%d",
                        pnu, len(results), total,
                    )
                return results
        except Exception as e:
            logger.error("토지이용계획 조회 실패: %s (%s)", pnu, str(e))
            return results  # 부분 수집분이라도 반환(전체 손실 방지)

    # ── VWORLD 정적 영상(항공/위성 정사영상) ──
    IMAGE_URL = "https://api.vworld.kr/req/image"

    async def get_aerial_image(
        self,
        lat: float,
        lon: float,
        zoom: int = 18,
        size: int = 512,
        basemap: str = "PHOTO",
    ) -> Optional[dict]:
        """좌표 중심 정사영상(항공/위성) PNG 취득 (VWorld static image getmap).

        라이브 검증 결과: service=image&request=getmap, center=lon,lat(필수),
        zoom=7~18, basemap=PHOTO(항공)·PHOTO_HYBRID, size=512,512, format=png →
        image/png bytes 반환. 키 권한/도메인(Referer) 불일치 시 JSON 오류 응답.

        반환: {"bytes": <png>, "source": "VWorld-PHOTO", "center": [lon,lat],
               "zoom": int, "size": int} 또는 None(미취득/폴백).
        """
        if not settings.VWORLD_API_KEY or not lat or not lon:
            return None
        # zoom은 7~18 범위(라이브 확인). 범위 밖이면 클램프.
        zoom = max(7, min(18, zoom))
        params = {
            "service": "image",
            "request": "getmap",
            "key": settings.VWORLD_API_KEY,
            "format": "png",
            "basemap": basemap,
            "crs": "EPSG:4326",
            "center": f"{lon},{lat}",
            "zoom": str(zoom),
            "size": f"{size},{size}",
            "version": "2.0",
        }
        try:
            # 이미지(항공/위성 PNG 타일)는 JSON보다 응답이 크고 느릴 수 있어 타임아웃을 길게 유지
            # (지적도 경계 JSON 경로만 12s 단축, 이미지 취득은 20s 보존 — 정상 타일 절단 방지).
            async with httpx.AsyncClient(timeout=20.0, headers=self.HEADERS) as client:
                resp = await client.get(self.IMAGE_URL, params=params)
                ct = resp.headers.get("content-type", "")
                # 정상 취득: PNG 매직넘버 또는 image/* content-type
                if resp.status_code == 200 and (
                    resp.content[:4] == b"\x89PNG" or ct.startswith("image")
                ):
                    return {
                        "bytes": resp.content,
                        "source": f"VWorld-{basemap}",
                        "center": [lon, lat],
                        "zoom": zoom,
                        "size": size,
                        "content_type": ct or "image/png",
                    }
                # 키 권한/파라미터 오류는 JSON으로 응답 → 폴백
                logger.warning(
                    "VWORLD 정사영상 미취득: status=%s ct=%s body=%s",
                    resp.status_code, ct, resp.text[:200],
                )
                return None
        except Exception as e:  # noqa: BLE001
            logger.error("VWORLD 정사영상 취득 실패: %s,%s (%s)", lat, lon, str(e)[:200])
            return None
