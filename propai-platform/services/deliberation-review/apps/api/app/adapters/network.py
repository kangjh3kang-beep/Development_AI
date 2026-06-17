"""R2 — 라이브 외부 호출 단일 choke point. 분석(소비)경로에서 사용 금지(INV-13).

공급측 harvester/주기 정합잡만 LiveNetwork를 사용. 기본(LIVE_NETWORK=False) mock(NetworkError),
운영(LIVE_NETWORK=True) 시 실 httpx GET. 소비 경로가 이 모듈을 import/사용하지 않음을 정적검사로 강제
(test_consume_static·test_live_call_scan은 소비 디렉터리만 스캔 — adapters/network.py는 공급측 choke point).
"""
from __future__ import annotations

# 라이브 GET 타임아웃(초). 운영 인프라 수치(법정 아님, INV-3 비대상) — source_cache.cached_get과 동일 기본.
_TIMEOUT_SECONDS = 15.0


class NetworkError(Exception):
    """라이브 외부 호출 실패/비활성. 호출자는 fallback으로 흡수."""


class LiveNetwork:
    def get(self, url: str) -> bytes:
        from app.settings import settings

        # 기본(mock): 라이브 호출 비활성. 공급측은 NetworkError를 fallback으로 흡수한다(소비경로는 무관).
        if not settings.LIVE_NETWORK:
            raise NetworkError(f"live network disabled (mock env): {url}")
        # 운영: 실 httpx GET → 본문 bytes. 실패는 NetworkError로 통일(무음 단정 금지 — 예외 표면화).
        try:
            import httpx

            # follow_redirects=False(명시) — 리다이렉트 통한 사설/내부 호스트 우회(SSRF) 표면 축소.
            r = httpx.get(url, timeout=_TIMEOUT_SECONDS, follow_redirects=False)
            r.raise_for_status()
            return r.content
        except Exception as exc:  # ImportError 포함 — 라이브 실패 일원화
            raise NetworkError(f"live fetch failed: {url}: {exc}") from exc
