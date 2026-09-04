"""VWORLD 지오코더 — 주소 → 좌표 → 필지 PNU(심의/설계 입지분석 진입점).

key=VWORLD_API_KEY + Referer. getcoord(주소→좌표) + GetFeature LP_PA_CBND_BUBUN(좌표→PNU).
지번(PARCEL) 우선, 실패 시 도로명(ROAD) 폴백. 결손/오류 None(graceful). 일 40,000건 한도.
"""
from __future__ import annotations

from app.utils.pnu import is_valid_pnu

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
        from app.adapters.cache.source_cache import cached_get
        data = cached_get(
            self.name, f"{self.req}/address",
            {"service": "address", "request": "getcoord", "key": self.key,
             "address": address, "type": addr_type, "format": "json"},
            secret_param_keys=("key",), headers=self.headers, timeout=15.0)
        if data is None:
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
        from app.adapters.cache.source_cache import cached_get
        data = cached_get(
            self.name, f"{self.req}/data",
            {"service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN",
             "key": self.key, "format": "json", "crs": "EPSG:4326",
             "geomFilter": f"POINT({lon} {lat})", "size": "1"},
            secret_param_keys=("key",), headers=self.headers, timeout=15.0)
        if data is None:
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
        # ★**외부 응답을 그대로 값으로 쓰지 않는다.** 여기가 이 서비스에서 PNU 가 들어오는
        #   **유일한 미검증 입구**다 — 입력 계약(`AnalysisInput.pnu`)은 `^([0-9]{19})?$` 로
        #   이미 막혀 있지만, `effective_pnu` 는 **이 반환값으로 덮인다**.
        #   그 뒤 `collect_land_card` 와 어댑터 5벌이 그것을 **외부 API 인자**로 내보낸다.
        #   ★비규격이면 **싣지 않고 사유를 남긴다** — 무언 실패는 진단 불가를 만든다.
        pnu_reason = None
        if pnu is not None and not is_valid_pnu(pnu):
            pnu_reason = f"지오코딩 PNU 비규격(19자리 ASCII 숫자 아님): {str(pnu)[:24]!r}"
            pnu = None
        return {"pnu": pnu, "lon": lon, "lat": lat, "address": address,
                "site_geometry": geom, "pnu_reason": pnu_reason}


def build_geocoder() -> VworldGeocoder:
    return VworldGeocoder()
