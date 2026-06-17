"""VWORLD NED 토지이용계획 어댑터 — PNU로 용도지역/지구/고도제한(교차검증·규제 1차출처).

key=VWORLD_API_KEY + Referer 도메인 검증. getLandUseAttr → 용도지역지구 목록(prposAreaDstrcCodeNm).
용도지역은 용적률/건폐율/고도 한도를 결정하는 핵심 규제 — 법령/조례와 교차검증, 산정 입력에 활용.
결손/비정상은 None(graceful, 무음 단정 금지).
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


class VworldLandUseSource:
    """토지이용계획 용도지역지구. available 시 실 조회, 아니면 None. source 이름 고정."""

    name = "vworld_landuse"

    def __init__(self, key: str | None = None, base_url: str | None = None) -> None:
        self.key = key or env_or_setting("VWORLD_API_KEY")
        self.base = base_url or env_or_setting("VWORLD_NED_URL") or settings.VWORLD_NED_URL
        self.headers = {"Referer": env_or_setting("VWORLD_REFERER") or settings.VWORLD_REFERER}

    @property
    def available(self) -> bool:
        return bool(self.key)

    def land_use_zones(self, pnu: str) -> list[str] | None:
        """PNU 토지이용계획 용도지역지구명 목록. 결손/오류 None."""
        if not self.key or len(pnu) < 19:
            return None
        try:
            import httpx
        except ImportError:
            return None
        try:
            r = httpx.get(
                f"{self.base}/getLandUseAttr",
                params={"key": self.key, "pnu": pnu, "format": "json", "numOfRows": "50"},
                headers=self.headers, timeout=15.0)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        body = data.get("landUses") or data.get("landUse") or {}
        code = str(body.get("resultCode", ""))
        if "INCORRECT" in code.upper() or "ERROR" in code.upper():
            return None
        fields = body.get("field") or body.get("fields") or []
        if isinstance(fields, dict):
            fields = [fields]
        zones = sorted({f.get("prposAreaDstrcCodeNm") for f in fields if f.get("prposAreaDstrcCodeNm")})
        return zones or None

    def has_zone(self, pnu: str, keyword: str) -> bool | None:
        """특정 규제(예: '고도', '주거', '상업') 지구 포함 여부 — 교차검증용. 결손 None."""
        zones = self.land_use_zones(pnu)
        if zones is None:
            return None
        return any(keyword in z for z in zones)


def build_vworld_landuse() -> VworldLandUseSource:
    return VworldLandUseSource()
