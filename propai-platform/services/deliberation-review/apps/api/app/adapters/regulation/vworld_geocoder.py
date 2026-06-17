"""VWORLD 지오코더 — 주소 → 좌표 → 필지 PNU(심의/설계 입지분석 진입점).

key=VWORLD_API_KEY + Referer. getcoord(주소→좌표) + GetFeature LP_PA_CBND_BUBUN(좌표→PNU).
지번(PARCEL) 우선, 실패 시 도로명(ROAD) 폴백. 결손/오류 None(graceful). 일 40,000건 한도.
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


class VworldGeocoder:
    name = "vworld_geocoder"

    def __init__(self, key: str | None = None) -> None:
        self.key = key or env_or_setting("VWORLD_API_KEY")
        self.req = env_or_setting("VWORLD_REQ_URL") or settings.VWORLD_REQ_URL
        self.headers = {"Referer": env_or_setting("VWORLD_REFERER") or settings.VWORLD_REFERER}

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _getcoord(self, address: str, addr_type: str):
        try:
            import httpx
        except ImportError:
            return None
        try:
            r = httpx.get(f"{self.req}/address",
                          params={"service": "address", "request": "getcoord", "key": self.key,
                                  "address": address, "type": addr_type, "format": "json"},
                          headers=self.headers, timeout=15.0)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        resp = data.get("response", {})
        if resp.get("status") != "OK":
            return None
        pt = resp.get("result", {}).get("point", {})
        try:
            return float(pt["x"]), float(pt["y"])
        except (KeyError, TypeError, ValueError):
            return None

    def _coord_to_parcel(self, lon: float, lat: float) -> tuple[str | None, dict | None]:
        """좌표 → (PNU, 필지 geometry). 3D 일조 시뮬에 site_geometry 사용."""
        try:
            import httpx
        except ImportError:
            return None, None
        try:
            r = httpx.get(f"{self.req}/data",
                          params={"service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN",
                                  "key": self.key, "format": "json", "crs": "EPSG:4326",
                                  "geomFilter": f"POINT({lon} {lat})", "size": "1"},
                          headers=self.headers, timeout=15.0)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None, None
        feats = data.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])
        if not feats:
            return None, None
        return feats[0].get("properties", {}).get("pnu"), feats[0].get("geometry")

    def address_to_pnu(self, address: str) -> dict | None:
        """주소 → {pnu, lon, lat, address, site_geometry}. 지번 우선·도로명 폴백. 좌표 실패 None."""
        if not self.key or not address:
            return None
        coord = self._getcoord(address, "PARCEL") or self._getcoord(address, "ROAD")
        if not coord:
            return None
        lon, lat = coord
        pnu, geom = self._coord_to_parcel(lon, lat)
        return {"pnu": pnu, "lon": lon, "lat": lat, "address": address, "site_geometry": geom}


def build_geocoder() -> VworldGeocoder:
    return VworldGeocoder()
