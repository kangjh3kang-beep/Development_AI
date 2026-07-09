"""P4-B 인구밀도 지도 레이어 — SGIS 행정동 경계(GeoJSON) + 인구 → 밀도 코로플레스 데이터.

흐름(라이브 검증된 선결 반영):
1. 대상 주소(bcode) → SGIS 시군구 adm_cd 해석(SgisClient._resolve_sgis_sigungu_cd 재사용).
2. 그 시군구 하위 행정동 경계(boundary/hadmarea.geojson, low_search)를 조회 — ★좌표계 UTM-K(EPSG:5179).
3. 시군구의 동별 인구(stats/searchpopulation.json, low_search) 조회.
4. 동별: 면적(UTM-K 폴리곤 shapely, m²→㎢) + 인구 → 밀도(명/㎢). 좌표를 WGS84로 재투영(pyproj).
5. features[{adm_cd, name, geometry(WGS84), population, area_km2, density}] + legend(min/max) 반환.

무자료/키없음/실패는 정직 표기(data_source=unavailable + reason, 가짜 밀도 금지).
SGIS 경계는 인구주택총조사 기준 → 최신 수록연도 폴백(2023→2022).
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from apps.api.integrations.sgis_client import SgisClient

logger = structlog.get_logger(__name__)

_SGIS_BASE = "https://sgisapi.mods.go.kr"
_BOUNDARY_YEARS = ["2023", "2022", "2021"]


def _reproject_5179_to_4326(coords: Any, tf: Any) -> Any:
    """중첩 좌표 배열(UTM-K)을 재귀로 WGS84(경도,위도)로 변환. GeoJSON 구조 보존."""
    if (
        isinstance(coords, (list, tuple))
        and len(coords) >= 2
        and all(isinstance(v, (int, float)) for v in coords[:2])
    ):
        lon, lat = tf.transform(coords[0], coords[1])
        return [round(lon, 6), round(lat, 6)]
    return [_reproject_5179_to_4326(c, tf) for c in coords]


def build_utmk_to_wgs84_transformer() -> Any | None:
    """UTM-K(EPSG:5179)→WGS84(EPSG:4326) 좌표 변환기를 만든다(공용).

    always_xy=True → (경도,위도) 순. pyproj 미설치/생성 실패 시 None 을 돌려주고,
    호출측은 500 대신 정직하게 data_source='unavailable' 로 폴백한다(가짜좌표 금지).
    인구밀도·권역이동 등 UTM-K 경계를 다루는 레이어가 공유한다(한 곳 수정=전역 반영).
    """
    try:
        from pyproj import Transformer
        return Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)
    except Exception:  # noqa: BLE001
        return None


def _polygon_area_m2(geometry: dict[str, Any]) -> float:
    """UTM-K(m) 폴리곤/멀티폴리곤의 면적(m²) — shapely(투영좌표라 면적 정확)."""
    try:
        from shapely.geometry import shape
        return float(shape(geometry).area)
    except Exception:  # noqa: BLE001
        return 0.0


class PopulationDensityService:
    """SGIS 경계+인구 → 인구밀도 코로플레스 features."""

    def __init__(self) -> None:
        self._sgis = SgisClient()

    async def build(self, *, bcode: str | None, region_name: str | None = None) -> dict[str, Any]:
        token = await self._sgis.get_access_token()
        if not token:
            return {"data_source": "unavailable", "reason": "SGIS 인증키 미설정/토큰 실패", "features": []}
        sgis_cd = await self._sgis._resolve_sgis_sigungu_cd(bcode or "", region_name)
        if not sgis_cd:
            return {"data_source": "unavailable", "reason": "SGIS 시군구코드 미해석(주소/bcode 확인)", "features": []}

        # 경계(동) + 인구(동) 동시 조회.
        boundaries, pop_year = await self._fetch_boundaries(token, sgis_cd)
        if not boundaries:
            return {"data_source": "unavailable", "reason": "SGIS 행정동 경계 무자료", "features": [],
                    "sgis_cd": sgis_cd}
        pop_by_cd = await self._fetch_population_by_dong(token, sgis_cd, pop_year)

        # 좌표계 변환기(UTM-K→WGS84, 공용 헬퍼). pyproj 미설치 시 정직 폴백(500 방지).
        tf = build_utmk_to_wgs84_transformer()
        if tf is None:
            return {"data_source": "unavailable", "reason": "좌표 변환기(pyproj) 미설치", "features": [],
                    "sgis_cd": sgis_cd}

        feats: list[dict[str, Any]] = []
        for b in boundaries:
            props = b.get("properties") or {}
            adm_cd = str(props.get("adm_cd") or "")
            name = props.get("adm_nm") or adm_cd
            geom = b.get("geometry") or {}
            area_m2 = _polygon_area_m2(geom)
            area_km2 = round(area_m2 / 1e6, 3) if area_m2 else None
            pop = pop_by_cd.get(adm_cd)
            density = (
                round(pop / area_km2) if (pop and area_km2 and area_km2 > 0) else None
            )
            try:
                wgs_coords = _reproject_5179_to_4326(geom.get("coordinates"), tf)
            except Exception:  # noqa: BLE001
                continue  # 변환 실패 동은 제외(가짜좌표 금지)
            feats.append({
                "adm_cd": adm_cd,
                "name": name,
                "geometry": {"type": geom.get("type"), "coordinates": wgs_coords},
                "population": pop,
                "area_km2": area_km2,
                "density": density,  # 명/㎢ (무자료=None → 프론트 회색)
            })

        densities = [f["density"] for f in feats if f.get("density")]
        legend = {"min": min(densities), "max": max(densities)} if densities else {"min": 0, "max": 0}
        return {
            "data_source": "sgis_live",
            "sgis_cd": sgis_cd,
            "year": pop_year,
            "count": len(feats),
            "features": feats,
            "legend": legend,
            "note": ("SGIS 행정동 경계(UTM-K→WGS84 변환)+인구주택총조사 인구. "
                     "밀도=인구/면적(명/㎢). 무자료 동은 회색(가짜값 없음)."),
        }

    async def _fetch_boundaries(self, token: str, sgis_cd: str) -> tuple[list[dict], str]:
        """시군구 하위 행정동 경계(GeoJSON features, UTM-K). 수록연도 폴백."""
        async with httpx.AsyncClient(timeout=20, base_url=_SGIS_BASE) as c:
            for yr in _BOUNDARY_YEARS:
                try:
                    r = await c.get("/OpenAPI3/boundary/hadmarea.geojson", params={
                        "accessToken": token, "year": yr, "adm_cd": sgis_cd, "low_search": "1",
                    })
                    g = r.json()
                    feats = g.get("features") or []
                    if feats:
                        return feats, yr
                except Exception as e:  # noqa: BLE001
                    logger.debug("SGIS 경계 조회 실패", year=yr, err=str(e)[:80])
        return [], _BOUNDARY_YEARS[0]

    async def _fetch_population_by_dong(self, token: str, sgis_cd: str, year: str) -> dict[str, int]:
        """시군구 하위 동별 인구 dict{adm_cd: population}. low_search로 하위 분해."""
        out: dict[str, int] = {}
        async with httpx.AsyncClient(timeout=20, base_url=_SGIS_BASE) as c:
            for yr in [year] + [y for y in _BOUNDARY_YEARS if y != year]:
                try:
                    r = await c.get("/OpenAPI3/stats/searchpopulation.json", params={
                        "accessToken": token, "year": yr, "adm_cd": sgis_cd, "low_search": "1",
                    })
                    j = r.json()
                    rows = j.get("result") or []
                    for it in rows:
                        cd = str(it.get("adm_cd") or "")
                        pv = int(it.get("population", 0) or 0)
                        if cd and pv > 0:
                            out[cd] = pv
                    if out:
                        return out
                except Exception as e:  # noqa: BLE001
                    logger.debug("SGIS 동별 인구 실패", year=yr, err=str(e)[:80])
        return out
