"""자치법규(elis.go.kr) 어댑터 — 지자체별 조례 소싱. LiveNetwork(allowlist·LIVE_NETWORK 게이트) 경유.

INV-13: 소비 경로는 버전드 미러만 읽음 — 본 어댑터는 공급(harvest) 단계에서만 호출(라이브). LIVE_NETWORK off
또는 네트워크 실패 시 None(graceful degrade, 예외 비전파 — 호출측이 미상으로 표면화). 결과(조례 본문 + 메타)는
버전드 스냅샷·교차검증에 결속(국가법령 reconcile 패턴 차용). 호스트는 network allowlist(elis.go.kr)만 통과.
"""
from __future__ import annotations

from app.adapters.network import LiveNetwork, NetworkError


class ElisOrdinanceSource:
    """자치법규 1차출처. fetch_ordinance: (지자체코드, 키워드) → 조례 본문/메타 또는 None(미상)."""

    base_url = "https://www.elis.go.kr"
    name = "elis"

    def __init__(self, net: LiveNetwork | None = None) -> None:
        self._net = net or LiveNetwork()

    def fetch_ordinance(self, *, jurisdiction: str, keyword: str) -> dict | None:
        """지자체 조례 조회. 라이브 off/실패 → None(예외 비전파). 성공 시 {jurisdiction, keyword, raw, source}."""
        url = f"{self.base_url}/search?juris={jurisdiction}&q={keyword}"
        try:
            raw = self._net.get(url)
        except NetworkError:
            return None
        if not raw:
            return None
        return {"jurisdiction": jurisdiction, "keyword": keyword, "raw": raw, "source": "elis.go.kr"}
