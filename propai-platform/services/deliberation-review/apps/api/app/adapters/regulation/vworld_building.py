"""VWORLD NED 용도별 건물정보 어댑터 — PNU로 기존 건물 제원(잔여 개발용량 산정).

key=VWORLD_API_KEY + Referer. getBuildingUse → 연면적/건축면적/건폐율/용적률/층수/용도. 다동이면 합산.
법정 한도(용도지역) 대비 잔여 개발용량(remaining FAR) 산정·증축/재건축 심의·MOLIT 건축물대장 교차검증.
결손/무건축물(totalCount 0) None(graceful).
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


def _f(v) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(float(v)) if v not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


class VworldBuildingSource:
    """기존 건물 제원. available 시 실 조회, 아니면 None. source 이름 고정."""

    name = "vworld_building"

    def __init__(self, key: str | None = None, base_url: str | None = None) -> None:
        self.key = key or env_or_setting("VWORLD_API_KEY")
        self.base = base_url or env_or_setting("VWORLD_NED_URL") or settings.VWORLD_NED_URL
        self.headers = {"Referer": env_or_setting("VWORLD_REFERER") or settings.VWORLD_REFERER}

    @property
    def available(self) -> bool:
        return bool(self.key)

    def existing_building(self, pnu: str) -> dict | None:
        """기존 건물 제원(다동 합산). 무건축물/오류 None."""
        if not self.key or len(pnu) < 19:
            return None
        try:
            import httpx
        except ImportError:
            return None
        try:
            r = httpx.get(
                f"{self.base}/getBuildingUse",
                params={"key": self.key, "pnu": pnu, "format": "json", "numOfRows": "100"},
                headers=self.headers, timeout=15.0)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        body = data.get("buildingUses") or data.get("buildingUse") or {}
        resp = data.get("response") or {}
        if str(resp.get("totalCount", "")) == "0":
            return None  # 무건축물(나대지 추정)
        fields = body.get("field") or body.get("fields") or []
        if isinstance(fields, dict):
            fields = [fields]
        if not fields:
            return None
        total_floor = sum(_f(f.get("buldTotar")) for f in fields)
        building_area = sum(_f(f.get("buldBildngAr")) for f in fields)
        main = fields[0]
        return {
            "total_floor_area": round(total_floor, 2),       # 연면적 합(㎡)
            "building_area": round(building_area, 2),         # 건축면적 합(㎡)
            "far_pct": _f(main.get("measrmtRt")) or None,     # 용적률(%)
            "bcr_pct": _f(main.get("btlRt")) or None,         # 건폐율(%)
            "main_purpose": main.get("mainPrposCodeNm"),      # 주용도(공동주택…)
            "structure": main.get("strctCodeNm"),             # 구조
            "ground_floors": _i(main.get("groundFloorCo")),
            "underground_floors": _i(main.get("undgrndFloorCo")),
            "building_count": len(fields),
        }


def build_vworld_building() -> VworldBuildingSource:
    return VworldBuildingSource()
