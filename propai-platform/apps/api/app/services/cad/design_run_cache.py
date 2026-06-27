"""design_run_cache — 설계 매스 산출(_resolve_mass)의 input_hash 멱등 캐시(시간절감·thread-safe).

이 파일이 푸는 문제(쉬운 설명):
- 설계 스튜디오는 같은 부지·같은 조건으로 /mass(또는 /layout·/bim·model.glb·export-ifc)를 반복 호출한다.
  그때마다 무거운 매스 산출(compute_optimal_mass + 실내요소 보강 + C2R 계약 조립)을 처음부터 다시 돌린다.
- _resolve_mass는 같은 입력이면 항상 같은 결과(결정적·멱등)이므로, 한 번 계산한 결과를
  '입력 지문(input_hash)'을 열쇠로 보관해두면 두 번째 호출부터는 즉시 돌려줄 수 있다(시간절감).

★왜 in-process(프로세스 메모리) 캐시인가 = 자동 무효화:
- 배포(블루그린)를 할 때마다 API 프로세스가 새로 떠서 이 캐시가 통째로 비워진다.
- 즉, 엔진 코드나 법규 수치가 바뀌어 새로 배포하면 '헌 결과'가 절대 안 남는다(자동으로 무효화).
- 별도 캐시 무효화 키 관리가 필요 없어 단순하고 안전하다(외부 저장소·신규 의존성 0).

★thread-safe(동시요청 안전): FastAPI는 여러 요청을 동시에 처리할 수 있으므로, 캐시 내부의
  OrderedDict를 여러 스레드가 동시에 만지면 자료가 깨질 수 있다. 그래서 모든 접근을 Lock으로 감싼다.

★주의(값 격리는 호출부 책임): 이 캐시 모듈은 값을 '참조 그대로' 저장한다(deepcopy 안 함).
  캐시에 넣기 전/꺼낸 후의 깊은 복사(deepcopy)는 호출부(_resolve_mass)가 책임진다.
  → 호출부가 돌려받은 mass를 나중에 고쳐도(mutate) 캐시 안의 원본은 안 더럽혀진다.

신규 의존성 0: collections(OrderedDict)·threading은 파이썬 표준 라이브러리다.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

# 캐시 최대 보관 개수(LRU). 부지·조건 조합당 결과 1개씩 보관하므로 256이면 활성 세션을 넉넉히 덮는다.
# 초과하면 '가장 오래 안 쓴(LRU)' 항목부터 버린다(메모리 무한증가 방지).
_MAXSIZE = 256


class _DesignRunCache:
    """input_hash → 매스 산출 결과를 보관하는 바운드 LRU 캐시(thread-safe).

    LRU(Least Recently Used) = '가장 오래 안 쓴 것부터 버린다'.
    OrderedDict로 구현 = 최근 쓴 항목을 맨 뒤로 옮기고(move_to_end), 가득 차면 맨 앞(가장 오래된 것)을 버린다.
    """

    def __init__(self, maxsize: int = _MAXSIZE) -> None:
        self._maxsize = maxsize
        # OrderedDict: 삽입/접근 순서를 기억한다 → 맨 앞=가장 오래된 것, 맨 뒤=가장 최근 것.
        self._store: OrderedDict[str, Any] = OrderedDict()
        # Lock: 동시요청이 _store를 동시에 만지지 못하게 잠근다(자료 깨짐 방지).
        self._lock = threading.Lock()
        self._hits = 0    # 캐시 적중(이미 있어 재계산 안 한) 횟수 — 효과 측정용
        self._misses = 0  # 캐시 빗나감(없어 새로 계산해야 한) 횟수

    def get(self, key: str) -> Any | None:
        """열쇠로 값을 찾는다. 있으면 '최근 사용'으로 표시(맨 뒤로 이동)하고 값을, 없으면 None을 돌려준다."""
        with self._lock:
            if key in self._store:
                # 최근 쓴 항목을 맨 뒤로 옮긴다 → LRU에서 '안 버려질 후순위'로 보호.
                self._store.move_to_end(key)
                self._hits += 1
                return self._store[key]
            self._misses += 1
            return None

    def put(self, key: str, value: Any) -> None:
        """열쇠·값을 넣는다. 가득 차면 가장 오래 안 쓴 항목을 버린다(메모리 바운드)."""
        with self._lock:
            # 이미 있던 열쇠면 값을 갱신하고 최근 사용으로 표시.
            self._store[key] = value
            self._store.move_to_end(key)
            # 최대 개수 초과 시 맨 앞(가장 오래된 것)부터 버린다.
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)

    def stats(self) -> dict[str, int]:
        """효과 측정용 통계(적중·빗나감·현재 보관수)를 돌려준다."""
        with self._lock:
            return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}

    def clear(self) -> None:
        """캐시를 비운다(테스트·수동 무효화용). 통계 카운터도 0으로 되돌린다."""
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0


# ── 모듈 단위 단일 인스턴스(프로세스 전역 공용) ──
# _resolve_mass가 이 단일 캐시를 공유한다 → 같은 입력 반복호출이 프로세스 내에서 즉시 반환된다.
_cache = _DesignRunCache()


def get(key: str) -> Any | None:
    """전역 캐시에서 값을 찾는다(없으면 None). 적중 시 '최근 사용'으로 표시한다."""
    return _cache.get(key)


def put(key: str, value: Any) -> None:
    """전역 캐시에 값을 넣는다(초과 시 가장 오래된 항목 축출)."""
    _cache.put(key, value)


def stats() -> dict[str, int]:
    """전역 캐시 통계(hits·misses·size)를 돌려준다."""
    return _cache.stats()


def clear() -> None:
    """전역 캐시를 비운다(테스트·수동 무효화용)."""
    _cache.clear()
