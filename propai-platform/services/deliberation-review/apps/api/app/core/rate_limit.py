"""security — 경량 인메모리 고정창(fixed-window) 레이트리미터. 분당 클라이언트별 요청 상한.

/analyze는 외부 1차출처(VWORLD/MOLEG/MOLIT) 쿼터·비용을 소모 → 볼륨 폭주 시 쿼터 고갈/과금.
pnu 형식검증(무효 입력)과 별개로, 유효 요청의 '양' 자체를 클라이언트별로 제한한다.

⚠️ 한계(정직): 프로세스 로컬 카운터 — 다중 워커/인스턴스는 각자 셈(분산 강제 아님).
   운영 분산 레이트리밋은 Redis 등 공유 스토어 필요(미구현). 단일 인스턴스/워커 기준 baseline.
키 = 인증 토큰(있으면, 사용자 단위) 우선, 없으면 클라이언트 IP. clock 주입으로 결정론 테스트 가능.
"""
from __future__ import annotations

from collections.abc import Callable
from threading import Lock

import time as _time

_SECONDS_PER_MINUTE = 60  # 시간 단위 환산(법정값 아님 — 고정창 폭)


class FixedWindowRateLimiter:
    def __init__(self, limit_per_minute: int, clock: Callable[[], float] = _time.time) -> None:
        self._limit = limit_per_minute
        self._clock = clock
        self._lock = Lock()
        self._hits: dict[str, tuple[int, int]] = {}  # key -> (window_index, count)

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    def check(self, key: str) -> bool:
        """이 요청을 허용하면 True, 분당 상한 초과면 False. limit<=0이면 항상 True(비활성)."""
        if self._limit <= 0:
            return True
        window = int(self._clock() // _SECONDS_PER_MINUTE)
        with self._lock:
            w, count = self._hits.get(key, (window, 0))
            if w != window:  # 새 분 창 — 카운터 리셋
                w, count = window, 0
            count += 1
            self._hits[key] = (w, count)
            return count <= self._limit
