"""국토부 건축물대장(data.go.kr) 어댑터 — PNU로 용적률/건폐율/연면적(교차검증 1차출처).

serviceKey=MOLIT_API_KEY. 키 없음/미승인(resultCode≠00)/실패는 None(graceful, 무음 단정 금지).
PNU(19자) → sigunguCd(5)+bjdongCd(5)+본번(4)+부번(4). 플랫폼 building_registry와 동일 엔드포인트.
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


class MolitBuildingSource:
    """건축물대장 표제부. available 시 실 조회, 아니면 None. source 이름 고정(교차검증 출처 식별)."""

    name = "molit_building"

    def __init__(self, service_key: str | None = None, base_url: str | None = None) -> None:
        self.key = service_key or env_or_setting("MOLIT_API_KEY")
        self.base = base_url or env_or_setting("MOLIT_BLD_URL") or settings.MOLIT_BLD_URL

    @property
    def available(self) -> bool:
        return bool(self.key)

    @staticmethod
    def _pnu_parts(pnu: str) -> tuple[str, str, str, str]:
        # 19자: 시군구(0:5) 법정동(5:10) 산여부(10) 본번(11:15) 부번(15:19)
        return pnu[0:5], pnu[5:10], pnu[11:15], pnu[15:19]

    def building_basis(self, pnu: str) -> dict | None:
        """건축물대장 표제부 → {far_pct, bcr_pct, total_area, main_purpose}. 미승인/무건축물 None."""
        if not self.key or len(pnu) < 19:
            return None
        try:
            import httpx
        except ImportError:
            return None
        sigungu, bjdong, bun, ji = self._pnu_parts(pnu)
        try:
            r = httpx.get(
                f"{self.base}/getBrBasisOulnInfo",
                params={"serviceKey": self.key, "sigunguCd": sigungu, "bjdongCd": bjdong,
                        "bun": bun, "ji": ji, "numOfRows": "1", "pageNo": "1", "_type": "json"},
                timeout=15.0)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        header = data.get("response", {}).get("header", {})
        if header.get("resultCode") != "00":
            return None  # 미승인/오류 → 무음 단정 금지
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item")
        if not items:
            return None  # 무건축물(나대지 추정) → 결손
        it = items[0] if isinstance(items, list) else items
        return {
            "far_pct": float(it.get("vlRat", 0) or 0),
            "bcr_pct": float(it.get("bcRat", 0) or 0),
            "total_area": float(it.get("totArea", 0) or 0),
            "main_purpose": it.get("mainPurpsCdNm", ""),
        }

    def metric(self, pnu: str, key: str) -> float | None:
        """교차검증용 단일 지표(far_pct/bcr_pct/total_area). 결손 None."""
        d = self.building_basis(pnu)
        if not d:
            return None
        val = d.get(key)
        return float(val) if isinstance(val, (int, float)) else None


def build_molit_source() -> MolitBuildingSource:
    return MolitBuildingSource()
