"""실 VWORLD 관할 어댑터(국토교통부 공간정보 오픈 API). 용도지역지구 조회 → zones.

JurisdictionAdapter 계약(source + lookup(pnu)->dict, 실패 시 AdapterTimeout) 준수 → resolver fallback 흡수.
키 없으면 AdapterTimeout(→ 공부/수기 fallback). ⚠️ 데이터 레이어 코드/속성명은 VWORLD 문서로 확정 필요
(참조 구현 — 요청 구성/응답 파싱은 검증, 실 레이어ID는 운영 시 보정).
"""
from __future__ import annotations

from app.contracts.enums import JurisdictionSource
from app.services.preflight.adapters import AdapterTimeout
from app.settings import env_or_setting, settings


class VWorldJurisdictionAdapter:
    source = JurisdictionSource.EXTERNAL

    def __init__(self, api_key: str | None = None, api_url: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else env_or_setting("VWORLD_API_KEY")
        self.api_url = api_url or env_or_setting("VWORLD_API_URL") or settings.VWORLD_API_URL

    def lookup(self, pnu: str) -> dict:
        if not self.api_key:
            raise AdapterTimeout("VWORLD_API_KEY not configured")
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise AdapterTimeout("httpx unavailable") from exc
        try:
            resp = httpx.get(
                self.api_url,
                params={
                    "service": "data",
                    "request": "GetFeature",
                    "data": "LT_C_UQ111",  # 용도지역지구(참조) — 운영 시 문서로 확정.
                    "key": self.api_key,
                    "attrFilter": f"pnu:=:{pnu}",
                    "format": "json",
                    "size": "100",
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            return self._parse(resp.json(), pnu)
        except AdapterTimeout:
            raise
        except Exception as exc:
            raise AdapterTimeout(f"VWORLD lookup failed: {exc}") from exc

    @staticmethod
    def _parse(data: dict, pnu: str) -> dict:
        features = (
            data.get("response", {})
            .get("result", {})
            .get("featureCollection", {})
            .get("features", [])
        ) or []
        zones = []
        for f in features:
            props = f.get("properties", {})
            zone = props.get("dgm_nm") or props.get("uname") or props.get("prc_se_nm")
            if zone:
                zones.append({"zone_code": zone, "area_ratio": None})
        if not zones:
            raise AdapterTimeout("no zones in VWORLD response")
        return {"sido_code": pnu[:2], "sigungu_code": pnu[:5], "zones": zones}
