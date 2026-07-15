"""아웃박스 컨슈머 — 멱등 처리 + 소비처 레지스트리(P15 A4).

무엇을 푸는가: 아웃박스는 at-least-once(최소 1회) 발행이라 **같은 이벤트가 2번 이상** 소비처에
도착할 수 있다(발행 성공 후 확정 커밋 전에 죽으면 다음 폴링에 재발행). 따라서 소비처는 반드시
**멱등**이어야 한다 — 같은 event_id 는 몇 번 와도 부수효과를 1회만 낸다. 이 모듈이 그 계약을
제공한다.

구성:
- IdempotencyGuard: event_id 중복 판정(프로세스-로컬 LRU). 단일 워커(운영 Micro = uvicorn
  1워커)에서는 이것으로 충분하고, 수평 확장 시 DB inbox/Redis 로 교체 가능(계약 동일).
  ★계약 한계(반드시 읽을 것): 이 가드는 **동일 프로세스 내 즉시 재시도의 완충**일 뿐이다.
  프로세스가 죽었다 재기동하면(크래시 창) 메모리가 통째로 사라져 dedup 기록도 함께 사라진다
  — "크래시 후에도 부수효과가 정확히 1회"라는 지속적(durable) exactly-once 보장은 **이 가드가
  주지 않는다**. 그런 보장이 필요한 소비처(예: 결제 승인·재고 차감처럼 크래시 창에서도 중복이
  치명적인 부수효과)는 **자기 데이터 계층**(event_id UNIQUE 제약 + INSERT ... ON CONFLICT DO
  NOTHING, 또는 upsert)으로 지속 dedup 을 별도 구현해야 한다. 이 가드에만 기대 exactly-once
  를 설계하지 말 것.
- process_once / process_once_async: "처음이면 핸들러 실행+기억, 이미 봤으면 건너뜀"의 단일
  진입점. ★핸들러가 예외를 내면 **기억하지 않는다**(재전달 시 다시 처리 — at-least-once 보존).
- ConsumerRegistry(register_consumer/deliver): event_type → (이름 붙은) 비동기 핸들러들.
  ★소비처별 멱등 격리: `deliver` 는 소비처마다 **전용 IdempotencyGuard 인스턴스**를 쓰고,
  멱등 키를 `f"{consumer_name}:{event_id}"` 로 네임스페이스화한다(이중 방어). 이렇게 해야
  (a) 부분성공 재전달 시 이미 성공한 소비처는 재실행되지 않고 실패했던 소비처만 재시도되며,
  (b) 여러 소비처가 같은 event_id 를 봐도 서로의 처리 여부에 영향을 주지 않는다(교차억제 0).
  공유 default_guard 를 여러 소비처가 그대로 나눠 쓰면, 먼저 성공한 소비처의 remember(event_id)
  때문에 나중 소비처가 seen=True 로 오판해 **영구히 실행되지 않는** 소실 버그가 난다 — 절대
  공유 가드를 소비처 간 공유하지 말 것.

원장 무관: 여기 dedup 은 전송 멱등일 뿐 원장 해시체인과 무관하다.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

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

    ★계약 한계(모듈 docstring과 동일 — 중요해서 반복): 이 가드는 **동일 프로세스·즉시 재시도용
    완충**이다. 프로세스 크래시/재기동에는 dedup 기록이 함께 사라져 방어되지 않는다. 크래시
    창까지 포함한 지속적 exactly-once 가 필요하면 소비처 스스로 데이터 계층(event_id UNIQUE
    제약·upsert)으로 durable dedup 을 구현해야 한다 — 이 가드에 그 책임을 떠넘기지 말 것.
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
# event_type → 이름 붙은 소비처 목록. 핸들러 시그니처: async def h(event: dict) -> None.
# 외부 브로커(Kafka 등)가 없는 현행 스택에서 '발행'은 이 인프로세스 소비처로의 전달을 뜻한다
# (growth_dispatch 선례와 동형). 등록 소비처가 없으면 발행 = 로그 후 성공(이벤트는 outbox_event
# 테이블에 내구 기록되어 있으므로 손실 아님).
@dataclass
class _Registration:
    """소비처 1건 — 이름 + 핸들러 + **전용** IdempotencyGuard.

    ★가드를 소비처마다 새로 발급하는 것이 핵심 계약이다(공유 default_guard 금지). 이렇게 해야
    소비처 A 의 성공이 소비처 B 의 처리를 막는 교차억제가 원천적으로 불가능하다 — 인스턴스가
    다르므로 A 의 remember(event_id) 는 B 의 가드에 아무 영향이 없다.
    """

    name: str
    handler: Callable[[dict], Awaitable[None]]
    guard: IdempotencyGuard = field(default_factory=IdempotencyGuard)


_CONSUMERS: dict[str, list[_Registration]] = {}


def register_consumer(
    event_type: str, handler: Callable[[dict], Awaitable[None]], *, name: str | None = None
) -> str:
    """event_type 소비처(비동기 핸들러)를 이름과 함께 등록하고, 최종 이름을 반환한다.

    name 미지정 시 `f"{event_type}#{순번}"` 으로 자동 부여한다(로그·멱등 키 네임스페이스에
    쓰이므로 사람이 읽을 수 있는 이름을 권장). 등록 시 이 소비처 전용 IdempotencyGuard 를
    새로 발급한다(다른 소비처와 공유하지 않음 — 위 모듈/클래스 docstring 계약).
    """
    bucket = _CONSUMERS.setdefault(event_type, [])
    cname = name or f"{event_type}#{len(bucket)}"
    bucket.append(_Registration(name=cname, handler=handler))
    return cname


def clear_consumers() -> None:
    """등록된 소비처(및 각자의 전용 가드)를 모두 비운다(테스트 격리용)."""
    _CONSUMERS.clear()


def consumer_count(event_type: str) -> int:
    """해당 event_type 에 등록된 소비처 수."""
    return len(_CONSUMERS.get(event_type, ()))


async def deliver(event: dict) -> bool:
    """이벤트를 등록 소비처들에 **소비처별 멱등**으로 전달한다.

    각 소비처는 `f"{consumer_name}:{event_id}"` 키로 자기 전용 가드를 통해 process_once_async
    를 경유한다. 그 결과:
      - 부분성공 재전달: 이전에 성공했던 소비처는 (자기 가드가 기억하므로) 재실행되지 않고,
        실패했던 소비처만 다시 시도된다 — 성공한 소비처의 중복 부수효과가 없다.
      - 교차억제 0: 여러 소비처가 같은 event_id 를 받아도 서로 독립적으로 판정한다(한 소비처의
        성공이 다른 소비처의 실행을 막지 않는다).
    - 소비처 없음: True(발행 성공으로 간주 — 이벤트는 이미 outbox_event 에 내구 기록됨).
    - 소비처 예외(또는 SKIPPED_DUPLICATE 가 아닌 한): 로그 후 그 소비처만 실패로 집계.
      **하나라도 실패하면 전체 False**(디스패처가 mark_failed → 백오프 재시도 — 이때도 이미
      성공한 소비처는 재전달에서 자기 가드로 스킵되므로 안전).
    ★크래시 창(프로세스 재기동)에는 이 가드가 방어하지 못한다 — IdempotencyGuard docstring 참고.
    """
    etype = str(event.get("event_type", ""))
    eid = str(event.get("event_id", ""))
    regs = _CONSUMERS.get(etype, [])
    if not regs:
        return True
    ok = True
    for reg in regs:
        key = f"{reg.name}:{eid}"
        try:
            await process_once_async(key, lambda ev=event, h=reg.handler: h(ev), reg.guard)
        except Exception as e:  # noqa: BLE001
            ok = False
            logger.warning(
                "outbox 소비처 실패(type=%s, consumer=%s, id=%s): %s",
                etype, reg.name, eid[:16], str(e)[:160],
            )
    return ok
