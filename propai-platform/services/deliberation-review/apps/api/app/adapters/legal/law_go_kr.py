"""국가법령정보센터(법제처) law.go.kr DRF API 어댑터 — 법령 검색/본문(교차검증 1차출처).

OC(기관코드)=MOLEG_API_KEY. 키 없으면 None(graceful 폴백). 라이브 실패도 None(무음 단정 금지).
플랫폼 regulation_monitor와 동일 엔드포인트(lawSearch.do/lawService.do).
"""
from __future__ import annotations

from app.settings import env_or_setting, settings


class LawGoKrSource:
    """law.go.kr DRF. available 시 실 조회, 아니면 None. source 이름 고정(교차검증 출처 식별)."""

    name = "law_go_kr"

    def __init__(self, oc: str | None = None, base_url: str | None = None) -> None:
        self.oc = oc or env_or_setting("MOLEG_API_KEY")
        self.base_url = base_url or env_or_setting("MOLEG_BASE_URL") or settings.MOLEG_BASE_URL

    @property
    def available(self) -> bool:
        return bool(self.oc)

    def _get(self, path: str, params: dict) -> dict | None:
        if not self.oc:
            return None
        # INC-11: 캐시 경유(적중→동일 출력, 결정론 0영향). OC(기관코드)는 cache_key 제외(시크릿 비유출).
        from app.adapters.cache.source_cache import cached_get
        return cached_get(self.name, f"{self.base_url}/{path}", {"OC": self.oc, **params},
                          secret_param_keys=("OC",), timeout=20.0)

    def search_law(self, query: str, display: int = 5) -> dict | None:
        """법령 검색(lawSearch.do) — query로 법령 목록 JSON."""
        return self._get("lawSearch.do", {"target": "law", "type": "JSON", "query": query, "display": display})

    def get_law(self, law_id: str) -> dict | None:
        """법령 본문(lawService.do) — 법령 ID로 조문 JSON."""
        return self._get("lawService.do", {"target": "law", "type": "JSON", "ID": law_id})

    def law_exists(self, query: str) -> bool | None:
        """법령 존재 여부(교차검증용 사실) — 검색 결과 ≥1이면 True, 0이면 False, 결손 None."""
        data = self.search_law(query, display=1)
        if data is None:
            return None
        search = data.get("LawSearch") if isinstance(data, dict) else None
        if not isinstance(search, dict):
            return None
        total = search.get("totalCnt")
        try:
            return int(total) > 0
        except (TypeError, ValueError):
            return bool(search.get("law"))


def build_law_source() -> LawGoKrSource:
    return LawGoKrSource()
