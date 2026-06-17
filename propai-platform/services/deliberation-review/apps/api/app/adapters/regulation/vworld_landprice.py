"""VWORLD NED 개별공시지가 어댑터 — PNU로 공시지가(원/㎡)(교차검증 1차출처).

key=VWORLD_API_KEY(NED 활용 추가 필요). 엔드포인트=getIndvdLandPriceAttr(워크플로우로 규명,
LandPriceService/att는 오타였음). 키 미적용(INCORRECT_KEY)/실패/결손은 None(graceful, 무음 단정 금지).
NSDI(data.go.kr 1611000)는 2024 VWORLD 이관으로 폐지(500) → VWORLD NED가 정답 경로.
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


class VworldLandPriceSource:
    """개별공시지가. available 시 실 조회, 아니면 None. source 이름 고정(교차검증 출처 식별)."""

    name = "vworld_landprice"

    def __init__(self, key: str | None = None, base_url: str | None = None) -> None:
        self.key = key or env_or_setting("VWORLD_API_KEY")
        self.base = base_url or env_or_setting("VWORLD_NED_URL") or settings.VWORLD_NED_URL
        # VWORLD 키는 Referer 도메인 검증 — 등록 도메인 미전송 시 INCORRECT_KEY.
        self.headers = {"Referer": env_or_setting("VWORLD_REFERER") or settings.VWORLD_REFERER}

    @property
    def available(self) -> bool:
        return bool(self.key)

    def land_price(self, pnu: str, stdr_year: str = "2024") -> float | None:
        """PNU 개별공시지가(원/㎡). 미적용 키/결손/비정상 resultCode는 None."""
        if not self.key or len(pnu) < 19:
            return None
        from app.adapters.cache.source_cache import cached_get
        data = cached_get(
            self.name, f"{self.base}/getIndvdLandPriceAttr",
            {"key": self.key, "pnu": pnu, "stdrYear": stdr_year, "format": "json", "numOfRows": "1"},
            secret_param_keys=("key",), headers=self.headers, timeout=15.0)
        if data is None:
            return None
        body = data.get("indvdLandPrices") or data.get("indvdLandPrice") or {}
        code = str(body.get("resultCode", ""))
        if code and "NORMAL" not in code.upper() and code.upper() != "OK":
            return None  # INCORRECT_KEY 등 → 무음 단정 금지
        fields = body.get("field") or body.get("fields") or []
        if isinstance(fields, dict):
            fields = [fields]
        if not fields:
            return None
        val = fields[0].get("pblntfPclnd") or fields[0].get("pblntfPclndPc")
        try:
            return float(val) if val not in (None, "") else None
        except (TypeError, ValueError):
            return None


def build_vworld_landprice() -> VworldLandPriceSource:
    return VworldLandPriceSource()
