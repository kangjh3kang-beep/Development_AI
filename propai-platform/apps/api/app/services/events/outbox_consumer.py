"""아웃박스 컨슈머 — 멱등 처리 + 소비처 레지스트리(P15 A4).

무엇을 푸는가: 아웃박스는 at-least-once(최소 1회) 발행이라 **같은 이벤트가 2번 이상** 소비처에
도착할 수 있다(발행 성공 후 확정 커밋 전에 죽으면 다음 폴링에 재발행). 따라서 소비처는 반드시
**멱등**이어야 한다 — 같은 event_id 는 몇 번 와도 부수효과를 1회만 낸다. 이 모듈이 그 계약을
제공한다.

구성:
- IdempotencyGuard: event_id 중복 판정(프로세스-로컬 LRU). 단일 워커(운영 Micro = uvicorn
  1워커)에서는 이것으로 충분하고, 수평 확장 시 DB inbox/Redis 로 교체 가능(계약 동일).
- process_once / process_once_async: "처음이면 핸들러 실행+기억, 이미 봤으면 건너뜀"의 단일
  진입점. ★핸들러가 예외를 내면 **기억하지 않는다**(재전달 시 다시 처리 — at-least-once 보존).
- ConsumerRegistry: event_type → 비동기 핸들러들. 디스패처가 발행 시 이 레지스트리로 전달한다.

원장 무관: 여기 dedup 은 전송 멱등일 뿐 원장 해시체인과 무관하다.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# 처리 결과 라벨.
PROCESSED = "PROCESSED"
SKIPPED_DUPLICATE = "SKIPPED_DUPLICATE"

# 프로세스-로컬 dedup 캐시 기본 용량(메모리 상한 — 무한 증식 방지).
_DEFAULT_CAPACITY = 50_000


class IdempotencyGuard:
    """event_id 중복 판정용 프로세스-로컬 LRU 집합.

    seen(id) 로 이미 처리했는지 보고, remember(id) 로 기록한다. 용량 초과 시 가장 오래된
    항목부터 버린다(LRU). ★버려진 오래된 event_id 가 다시 오면 '처음'으로 보여 재처리될 수
    있으나, 이는 부수효과가 진짜 멱등(같은 결과)일 때 안전하다 — 용량은 재전달 창보다 크게 둔다.
    """

    def __init__(self, capacity: int = _DEFAULT_CAPACITY) -> None:
        self._capacity = max(1, int(capacity))
        self._seen: OrderedDict[str, bool] = OrderedDict()

    def seen(self, event_id: str) -> bool:
        """이미 처리한 event_id 인가. (조회 시 LRU 갱신)"""
        if not event_id:
            return False
        if event_id in self._seen:
            self._seen.move_to_end(event_id)
            return True
        return False

    def remember(self, event_id: str) -> None:
        """event_id 를 처리됨으로 기록한다(용량 초과 시 최老 항목 축출)."""
        if not event_id:
            return
        self._seen[event_id] = True
        self._seen.move_to_end(event_id)
        while len(self._seen) > self._capacity:
            self._seen.popitem(last=False)

    def __len__(self) -> int:
        return len(self._seen)


# 모듈 기본 가드(단일 프로세스 공용).
default_guard = IdempotencyGuard()


def process_once(
    event_id: str, handler: Callable[[], object], guard: IdempotencyGuard | None = None
) -> str:
    """동기 핸들러를 멱등 실행한다.

    - 이미 본 event_id: 핸들러 실행 없이 SKIPPED_DUPLICATE.
    - 처음: 핸들러 실행 → 성공 시 기억하고 PROCESSED.
    - ★핸들러 예외: 기억하지 않고 예외 재전파(재전달 시 재처리 — at-least-once 보존).
    """
    # ★0-falsy: IdempotencyGuard 는 __len__ 을 정의하므로 '빈 가드'가 falsy 다. `guard or ...`
    #   단축평가는 갓 만든 빈 가드를 '없음'으로 오인해 default_guard 로 새므로 반드시 is None 판정.
    g = guard if guard is not None else default_guard
    if g.seen(event_id):
        return SKIPPED_DUPLICATE
    handler()  # 실패하면 여기서 예외 → remember 도달 못 함(의도).
    g.remember(event_id)
    return PROCESSED


async def process_once_async(
    event_id: str,
    handler: Callable[[], Awaitable[object]],
    guard: IdempotencyGuard | None = None,
) -> str:
    """비동기 핸들러를 멱등 실행한다(process_once 의 async 판)."""
    g = guard if guard is not None else default_guard  # ★0-falsy(위 process_once 주석 참고).
    if g.seen(event_id):
        return SKIPPED_DUPLICATE
    await handler()  # 실패하면 예외 → remember 미도달(재처리 가능).
    g.remember(event_id)
    return PROCESSED


# ── 소비처 레지스트리 ─────────────────────────────────────────────────────
# event_type → 비동기 핸들러 목록. 핸들러 시그니처: async def h(event: dict) -> None.
# 외부 브로커(Kafka 등)가 없는 현행 스택에서 '발행'은 이 인프로세스 소비처로의 전달을 뜻한다
# (growth_dispatch 선례와 동형). 등록 소비처가 없으면 발행 = 로그 후 성공(이벤트는 outbox_event
# 테이블에 내구 기록되어 있으므로 손실 아님).
_CONSUMERS: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}


def register_consumer(
    event_type: str, handler: Callable[[dict], Awaitable[None]]
) -> None:
    """event_type 소비처(비동기 핸들러)를 등록한다."""
    _CONSUMERS.setdefault(event_type, []).append(handler)


def clear_consumers() -> None:
    """등록된 소비처를 모두 비운다(테스트 격리용)."""
    _CONSUMERS.clear()


def consumer_count(event_type: str) -> int:
    """해당 event_type 에 등록된 소비처 수."""
    return len(_CONSUMERS.get(event_type, ()))


async def deliver(event: dict) -> bool:
    """이벤트를 등록 소비처들에 전달한다. **하나라도 실패하면 False**(재시도 대상).

    - 소비처 없음: True(발행 성공으로 간주 — 이벤트는 이미 내구 기록됨).
    - 소비처 예외: 로그 후 False 반환(디스패처가 mark_failed → 백오프 재시도).
    ★소비처 자신이 멱등이어야 한다(재전달 대비 — process_once_async 활용 권장).
    """
    etype = str(event.get("event_type", ""))
    handlers = _CONSUMERS.get(etype, [])
    if not handlers:
        return True
    ok = True
    for h in handlers:
        try:
            await h(event)
        except Exception as e:  # noqa: BLE001
            ok = False
            logger.warning(
                "outbox 소비처 실패(type=%s, id=%s): %s",
                etype, str(event.get("event_id", ""))[:16], str(e)[:160],
            )
    return ok
