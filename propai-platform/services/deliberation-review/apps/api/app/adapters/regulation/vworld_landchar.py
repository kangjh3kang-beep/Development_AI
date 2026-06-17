"""VWORLD NED 토지특성 어댑터 — PNU로 지목/경사/도로접면/용도지역/이용상황/공시지가 자동수집.

key=VWORLD_API_KEY + Referer. getLandCharacteristics → 토지 기본정보 한 호출. 심의/설계 입지분석의
토지 기본정보 자동수집(서비스 목적과 일치). 결손/오류 None(graceful). 산정·판정·교차검증 입력으로 활용.
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


class VworldLandCharSource:
    """토지특성. available 시 실 조회, 아니면 None. source 이름 고정(교차검증 출처 식별)."""

    name = "vworld_landchar"

    def __init__(self, key: str | None = None, base_url: str | None = None) -> None:
        self.key = key or env_or_setting("VWORLD_API_KEY")
        self.base = base_url or env_or_setting("VWORLD_NED_URL") or settings.VWORLD_NED_URL
        self.headers = {"Referer": env_or_setting("VWORLD_REFERER") or settings.VWORLD_REFERER}

    @property
    def available(self) -> bool:
        return bool(self.key)

    def fetch(self, pnu: str, stdr_year: str = "2024") -> dict | None:
        """토지특성 → {지목, 경사, 도로접면, 용도지역, 이용상황, 공시지가}. 결손/오류 None."""
        if not self.key or len(pnu) < 19:
            return None
        from app.adapters.cache.source_cache import cached_get
        data = cached_get(
            self.name, f"{self.base}/getLandCharacteristics",
            {"key": self.key, "pnu": pnu, "stdrYear": stdr_year, "format": "json", "numOfRows": "1"},
            secret_param_keys=("key",), headers=self.headers, timeout=15.0)
        if data is None:
            return None
        body = data.get("landCharacteristicss") or data.get("landCharacteristics") or {}
        code = str(body.get("resultCode", ""))
        if "INCORRECT" in code.upper() or "ERROR" in code.upper():
            return None
        fields = body.get("field") or body.get("fields") or []
        if isinstance(fields, dict):
            fields = [fields]
        if not fields:
            return None
        f = fields[0]

        def _num(*keys):
            for k in keys:
                v = f.get(k)
                if v not in (None, ""):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        pass
            return None

        return {
            "jimok": f.get("lndcgrCodeNm"),          # 지목(대/전/답…)
            "slope": f.get("tpgrphHgCodeNm"),        # 지형/경사(완경사…)
            "shape": f.get("tpgrphFrmCodeNm"),       # 형상(정방형/부정형…)
            "road_contact": f.get("roadSideCodeNm"),  # 도로접면(소로한면…)
            "use_zone": f.get("prposArea1Nm"),       # 용도지역(제1종일반주거…)
            "use_situation": f.get("ladUseSittnNm"),  # 이용상황(연립…)
            "area": _num("lndpclAr", "parea", "area"),  # 필지면적(㎡)
            "land_price": _num("pblntfPclnd"),       # 개별공시지가(원/㎡)
            "stdr_year": f.get("stdrYear"),
        }

    def metric(self, pnu: str, key: str, stdr_year: str = "2024"):
        """교차검증용 단일 지표(use_zone/land_price 등). 결손 None."""
        d = self.fetch(pnu, stdr_year)
        return d.get(key) if d else None


def build_vworld_landchar() -> VworldLandCharSource:
    return VworldLandCharSource()
