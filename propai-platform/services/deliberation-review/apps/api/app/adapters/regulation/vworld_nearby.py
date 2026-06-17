"""VWORLD 주변 건물(lt_c_bldginfo) 수집 + 스카이라인 — 일조/경관/높이제한 시뮬 입력.

key=VWORLD_API_KEY + Referer. 좌표 BBOX로 주변 건물 footprint+지상층수(grnd_flr)+높이 수집 →
평균/최고 층수·높이(스카이라인 컨텍스트). 신축안 돌출도·인접 일영·가로경관 연속성 판정에 활용.
결손/오류 None(graceful). 결정론.
"""
from __future__ import annotations

from statistics import mean

from app.settings import env_or_setting, settings

_DEG_PER_M = 1.0 / 111000.0  # 위도 1m≈도(경도 근사)


class VworldNearbyBuildings:
    name = "vworld_nearby"

    def __init__(self, key: str | None = None) -> None:
        self.key = key or env_or_setting("VWORLD_API_KEY")
        self.req = env_or_setting("VWORLD_REQ_URL") or settings.VWORLD_REQ_URL
        self.headers = {"Referer": env_or_setting("VWORLD_REFERER") or settings.VWORLD_REFERER}

    @property
    def available(self) -> bool:
        return bool(self.key)

    @staticmethod
    def _i(v) -> int:
        try:
            return int(float(v)) if v not in (None, "") else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _f(v) -> float:
        try:
            return float(v) if v not in (None, "") else 0.0
        except (TypeError, ValueError):
            return 0.0

    def buildings_near(self, lon: float, lat: float, radius_m: int = 150) -> list[dict] | None:
        if not self.key:
            return None
        try:
            import httpx
        except ImportError:
            return None
        d = radius_m * _DEG_PER_M
        try:
            r = httpx.get(f"{self.req}/data",
                          params={"service": "data", "request": "GetFeature", "data": "lt_c_bldginfo",
                                  "key": self.key, "format": "json", "crs": "EPSG:4326",
                                  "geomFilter": f"BOX({lon - d},{lat - d},{lon + d},{lat + d})", "size": "1000"},
                          headers=self.headers, timeout=20.0)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        resp = data.get("response", {})
        if resp.get("status") != "OK":
            return None
        feats = resp.get("result", {}).get("featureCollection", {}).get("features", [])
        out = []
        for f in feats:
            p = f.get("properties", {})
            out.append({"name": p.get("bld_nm") or "", "floors": self._i(p.get("grnd_flr")),
                        "underground": self._i(p.get("ugrnd_flr")), "height_m": self._f(p.get("height")),
                        "far_pct": self._f(p.get("vl_rat")),
                        "geometry": f.get("geometry")})  # footprint(GeoJSON) — 3D 그림자 시뮬용
        return out

    @staticmethod
    def skyline_from(buildings: list[dict], radius_m: int = 150) -> dict:
        """주변 건물 목록 → 스카이라인 통계(건물수·평균/최고 층수·높이). 신축 돌출도 판정 기준."""
        floors = [b["floors"] for b in buildings if b["floors"] > 0]
        heights = [b["height_m"] for b in buildings if b["height_m"] > 0]
        return {
            "building_count": len(buildings),
            "avg_floors": round(mean(floors), 1) if floors else None,
            "max_floors": max(floors) if floors else None,
            "avg_height_m": round(mean(heights), 1) if heights else None,
            "max_height_m": max(heights) if heights else None,
            "radius_m": radius_m,
        }

    def skyline_context(self, lon: float, lat: float, radius_m: int = 150) -> dict | None:
        """주변 건물 수집 + 스카이라인 통계. 결손 None."""
        bs = self.buildings_near(lon, lat, radius_m)
        if not bs:
            return None
        return self.skyline_from(bs, radius_m)


def build_nearby() -> VworldNearbyBuildings:
    return VworldNearbyBuildings()
