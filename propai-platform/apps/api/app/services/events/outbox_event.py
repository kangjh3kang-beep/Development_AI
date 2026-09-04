"""전역 아웃박스 — outbox_event (P15 A4 이벤트/아웃박스 전역화).

무엇을 푸는가: 지금까지 아웃박스(트랜잭션 이벤트 발행)는 분양(sales) 하네스에만 있었다
(services/sales/harness/outbox.py — `sales_harness_outbox` 테이블·PII 화이트리스트·동기 투영).
이 모듈은 그 원형을 **전역 `outbox_event`** 로 승격한다. 어떤 집계(aggregate)든 자기 상태를
바꾼 커밋과 **같은 트랜잭션**에서 이벤트 1행을 남겨두면(at-least-once), 디스패처가 뒤에서
폴링해 발행한다. 발행이 실패하면 행은 미발행으로 남아 다음 폴링에 재시도된다.

sales 원형과의 관계(★무회귀 우선): sales 는 **손대지 않는다**. `sales_harness_outbox` 와
`emit_outbox`/동기 투영은 그대로 두고, 전역 `outbox_event` 는 **병렬로 신설**한다. 향후 sales 가
전역을 소비하려면 이 파일의 얇은 어댑터(`outbox_event_from_sales`)로 매핑만 하면 되며,
이번 WP 에서는 배선하지 않는다(기존 소비처 불변).

영속 판단(★): alembic 헤드 추가는 금지다(WP-M 이 모든 마이그레이션 WP 완료 후 5→1 병합을
최후단 격리 실행 — 그 전 헤드 분기 금지). 따라서 WP-H(asset_rights)·growth·secret_store 선례와
동일하게 **CREATE TABLE IF NOT EXISTS 기반 schema_guard** 로 테이블을 멱등 보장한다. 헬퍼는
전부 best-effort·지연 초기화(첫 호출 시 보장)라 부팅 배선이 필요 없다.

원장과의 구분(★): 이 아웃박스는 append-only 해시체인 원장(analysis_ledger)과 **무관**하다.
원장은 감사·무결성용 불변 기록이고, 아웃박스는 발행 후 `published_at` 이 채워지는(=상태 변이)
전송 큐다. 둘을 혼동해선 안 된다(원장 무접촉).

핵심 계약(게이트):
- at-least-once: 발행 전에 행을 커밋한다. 발행 실패 → 미발행 유지 → 재시도(중복 발행 가능).
- 컨슈머 멱등: 중복 발행은 event_id 로 소비처에서 1회만 처리한다(outbox_consumer 참고).
- published_at 원자성: `mark_published` 는 `WHERE published_at IS NULL` 가드로, 여러 워커가
  같은 행을 잡아도 **최초 1회만** 발행 확정된다(나머지는 rowcount 0).
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# 페이로드 스키마 버전 기본값 — 이벤트 페이로드 형태가 바뀌면 이 숫자를 올리고 업캐스터를 등록한다.
DEFAULT_SCHEMA_VERSION = 1
# 발행 최대 재시도 횟수(이 횟수에 도달하면 더 이상 재시도하지 않음 — 데드레터 취급).
DEFAULT_MAX_ATTEMPTS = 8
# 지수 백오프 파라미터(초). attempts=1 → base, 이후 2배씩, cap 에서 포화.
_BACKOFF_BASE_SEC = 5
_BACKOFF_CAP_SEC = 3600


@dataclass
class OutboxEvent:
    """발행 대기 이벤트 1건.

    event_id 는 **멱등 키**다: 같은 논리 이벤트는 같은 event_id 를 가져야 emit 이 1회만 되고
    (INSERT ON CONFLICT DO NOTHING), 소비처도 event_id 로 중복을 1회 처리한다.
    """

    aggregate_id: str  # 이벤트를 낳은 집계 식별자(프로젝트/사이트/설계런 id 등)
    aggregate_type: str  # 집계 종류(예: 'design_run', 'sales_site', 'project')
    event_type: str  # 이벤트 종류(예: 'DesignRunCompleted')
    payload: dict = field(default_factory=dict)  # 비식별 페이로드(집계/식별 최소)
    schema_version: int = DEFAULT_SCHEMA_VERSION  # payload 스키마 버전
    event_id: str = ""  # 멱등 키(비면 new_event 에서 uuid 발급)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "event_type": self.event_type,
            "payload": self.payload,
            "schema_version": int(self.schema_version),
        }


def new_event(
    aggregate_id: str,
    aggregate_type: str,
    event_type: str,
    payload: dict | None = None,
    *,
    schema_version: int = DEFAULT_SCHEMA_VERSION,
    event_id: str | None = None,
) -> OutboxEvent:
    """OutboxEvent 를 만든다(순수). event_id 미지정 시 uuid4 를 발급한다.

    ★멱등: 재시도·중복 emit 을 1회로 접으려면 호출부가 **결정적 event_id**(예: 집계상태
      해시)를 넘겨야 한다. 미지정이면 매 호출 새 uuid 라 중복이 접히지 않는다.
    """
    return OutboxEvent(
        aggregate_id=(aggregate_id or "").strip(),
        aggregate_type=(aggregate_type or "").strip(),
        event_type=(event_type or "").strip(),
        payload=dict(payload or {}),
        schema_version=int(schema_version or DEFAULT_SCHEMA_VERSION),
        event_id=(event_id or str(uuid.uuid4())),
    )


# ── 재시도·백오프(순수) ──────────────────────────────────────────────────
def should_retry(attempts: int, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> bool:
    """attempts 회 실패한 이벤트를 또 시도할지 판단(순수).

    ★0-falsy 주의: attempts=0(아직 한 번도 시도 안 함)은 당연히 재시도 대상(True)이다.
      `attempts or ...` 같은 단축평가로 0 을 '없음'으로 오인하면 안 된다.
    """
    try:
        a = int(attempts)
    except (TypeError, ValueError):
        a = 0
    return a < int(max_attempts)


def next_backoff_seconds(
    attempts: int, base: int = _BACKOFF_BASE_SEC, cap: int = _BACKOFF_CAP_SEC
) -> int:
    """다음 재시도까지 대기 초(지수 백오프, cap 포화). attempts>=1 기준(순수).

    attempts=1 → base, 2 → base*2, 3 → base*4 ... cap 에서 멈춘다.
    """
    try:
        a = max(1, int(attempts))
    except (TypeError, ValueError):
        a = 1
    delay = int(base) * (2 ** (a - 1))
    return min(delay, int(cap))


# ── 페이로드 스키마 진화(순수) ───────────────────────────────────────────
# (event_type, from_version) → 다음 버전으로 올리는 순수 업캐스터. 낮은 버전으로 저장된 오래된
# 이벤트를 소비 시점의 최신 스키마로 끌어올린다. 체인(v1→v2→v3)은 순차 적용된다.
_PAYLOAD_MIGRATIONS: dict[tuple[str, int], Callable[[dict], dict]] = {}


def register_migration(
    event_type: str, from_version: int, upcaster: Callable[[dict], dict]
) -> None:
    """event_type 의 from_version → from_version+1 업캐스터를 등록한다(순수 함수여야 함)."""
    _PAYLOAD_MIGRATIONS[(event_type, int(from_version))] = upcaster


def clear_migrations() -> None:
    """등록된 업캐스터를 모두 비운다(테스트 격리용)."""
    _PAYLOAD_MIGRATIONS.clear()


def migrate_payload(
    event_type: str, payload: dict, from_version: int, to_version: int
) -> dict:
    """payload 를 from_version 에서 to_version 까지 등록된 업캐스터로 순차 변환(순수).

    - to_version <= from_version: 변환 없이 원본 그대로(다운캐스트 안 함).
    - 중간 버전 업캐스터가 없으면 그 단계는 항등(형태 불변) — 버전만 올린다.
    """
    fv, tv = int(from_version), int(to_version)
    if tv <= fv:
        return dict(payload or {})
    cur = dict(payload or {})
    for v in range(fv, tv):
        fn = _PAYLOAD_MIGRATIONS.get((event_type, v))
        if fn is not None:
            cur = fn(cur)
    return cur


# ── 발행 상태 도메인(순수) — DB SQL 과 동일 계약을 코드로 표현 ───────────────
# OutboxRowState 는 outbox_event 한 행의 발행 상태를 담는다. `claim_publish`/`register_failure`
# 는 이 상태에 대한 **결정 로직의 단일 출처**이고, 아래 DB 헬퍼의 SQL(WHERE published_at IS NULL,
# attempts=attempts+1)은 동일 계약을 SQL 로 집행한다. 그래서 이 순수 함수 테스트가 곧 발행
# 원자성·재시도 계약의 검증이 된다(무목업 — 별도 가짜 구현이 아니라 도메인 규칙 자체).
@dataclass
class OutboxRowState:
    event_id: str
    attempts: int = 0
    published_at: datetime | None = None
    status: str = "PENDING"
    last_error: str | None = None
    next_attempt_at: datetime | None = None


def claim_publish(state: OutboxRowState, now: datetime | None = None) -> bool:
    """발행 확정을 시도한다. 아직 미발행이면 published_at 을 채우고 True, 이미 발행이면 False.

    ★published_at 원자성: 이미 published_at 이 있으면 아무 것도 바꾸지 않고 False 를 준다.
      DB 에서는 `UPDATE ... WHERE published_at IS NULL` 이 같은 불변식을 보장한다(경쟁 시 1승).
    """
    if state.published_at is not None:
        return False
    state.published_at = now or datetime.now(UTC)
    state.status = "PUBLISHED"
    return True


def register_failure(
    state: OutboxRowState, error: str | None, now: datetime | None = None
) -> OutboxRowState:
    """발행 실패를 기록한다(순수): attempts+1·last_error·next_attempt_at(백오프) 설정.

    이미 발행된 행(published_at 有)은 실패로 되돌리지 않는다(멱등 안전).

    ★후속 이관(LOW·비차단): 재시도 소진(status=DEAD)은 여기 조용히 기록될 뿐, 대시보드/알림
    (예: DEAD 건수 임계치 초과 시 경보) 같은 가시성 표면이 아직 없다 — outbox_event 테이블을
    쿼리하면 확인 가능하나 능동 통지는 없다. 다음 세션에서 성장루프(growth)나 운영 알림 경로에
    결선한다(이번 봉합 범위 제외 — at-least-once 계약 자체와는 무관).
    """
    if state.published_at is not None:
        return state
    ts = now or datetime.now(UTC)
    state.attempts = int(state.attempts) + 1
    state.last_error = (error or "")[:500] or None
    from datetime import timedelta

    state.next_attempt_at = ts + timedelta(seconds=next_backoff_seconds(state.attempts))
    state.status = "PENDING" if should_retry(state.attempts) else "DEAD"
    return state


# ── 얇은 어댑터(무회귀) — sales 원형 → 전역(미배선) ─────────────────────────
def outbox_event_from_sales(
    site_id: uuid.UUID | str, event_type: str, payload: dict | None
) -> OutboxEvent:
    """sales 하네스 이벤트(site_id·event_type·payload)를 전역 OutboxEvent 로 매핑한다.

    ★이번 WP 에서는 **배선하지 않는다**(sales 는 자기 `sales_harness_outbox` 를 그대로 사용 —
      무회귀). WP-J 이후 sales 가 전역을 소비하기로 하면 emit_outbox 안에서 이 어댑터로 전역
      outbox_event 에 함께 적재하면 된다. 여기서는 계약만 제공한다.
    """
    return new_event(
        aggregate_id=str(site_id),
        aggregate_type="sales_site",
        event_type=event_type,
        payload=dict(payload or {}),
    )


# ── 영속(schema_guard — CREATE TABLE IF NOT EXISTS, alembic 헤드 없음) ─────────
_SCHEMA_READY = False

_OUTBOX_DDL = """
CREATE TABLE IF NOT EXISTS outbox_event (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id uuid NOT NULL,
    aggregate_id text NOT NULL,
    aggregate_type text NOT NULL,
    event_type text NOT NULL,
    payload jsonb,
    schema_version integer NOT NULL DEFAULT 1,
    status text NOT NULL DEFAULT 'PENDING',
    attempts integer NOT NULL DEFAULT 0,
    last_error text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    next_attempt_at timestamptz,
    published_at timestamptz
)
"""

_INDEXES = [
    # event_id 멱등 키 — 같은 논리 이벤트 emit 1회 보장(ON CONFLICT DO NOTHING 근거).
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_outbox_event_event_id ON outbox_event (event_id)",
    # 디스패처 폴링 인덱스 — 미발행 행을 occurred_at 순으로 스캔.
    "CREATE INDEX IF NOT EXISTS idx_outbox_event_unpublished "
    "ON outbox_event (occurred_at) WHERE published_at IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_outbox_event_aggregate "
    "ON outbox_event (aggregate_type, aggregate_id)",
]


async def ensure_schema(db: AsyncSession, force: bool = False) -> bool:
    """outbox_event 테이블·인덱스를 멱등 보장. 실패는 graceful(rollback 후 False)."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return True
    try:
        await db.execute(text(_OUTBOX_DDL))
        for ddl in _INDEXES:
            await db.execute(text(ddl))
        await db.commit()
        _SCHEMA_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("outbox_event schema_guard 실패: %s", str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def emit_event(db: AsyncSession, event: OutboxEvent, *, commit: bool = True) -> bool:
    """이벤트 1건을 아웃박스에 적재한다(PENDING). best-effort — 실패해도 예외 안 냄.

    ★멱등 emit: event_id 충돌 시 DO NOTHING(중복 적재 방지). 같은 트랜잭션에서 발행하려면
      commit=False 로 호출해 호출부 커밋에 합류시킨다(at-least-once 의 정석 — 상태변경과 원자적).
    """
    if not event.event_id or not event.aggregate_id:
        return False
    if not await ensure_schema(db):
        return False
    try:
        await db.execute(
            text(
                "INSERT INTO outbox_event "
                "(event_id, aggregate_id, aggregate_type, event_type, payload, schema_version) "
                "VALUES (:eid, :aid, :atype, :etype, CAST(:payload AS jsonb), :sv) "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "eid": event.event_id,
                "aid": event.aggregate_id,
                "atype": event.aggregate_type,
                "etype": event.event_type,
                "payload": json.dumps(event.payload or {}, ensure_ascii=False, default=str),
                "sv": int(event.schema_version),
            },
        )
        if commit:
            await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("emit_event 실패(%s): %s", event.event_id[:16], str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def fetch_publishable(
    db: AsyncSession, limit: int = 200, max_attempts: int = DEFAULT_MAX_ATTEMPTS
) -> list[dict]:
    """발행 대상(미발행·백오프 경과·재시도 여력) 행을 잠금 확보해 반환한다.

    FOR UPDATE SKIP LOCKED 로 여러 디스패처가 같은 행을 잡지 않게 한다(수평 확장 안전).
    호출부는 각 행을 발행 시도 후 mark_published/mark_failed 하고 **같은 세션에서 커밋**한다.
    """
    if not await ensure_schema(db):
        return []
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT event_id, aggregate_id, aggregate_type, event_type, payload, "
                    "       schema_version, attempts "
                    "FROM outbox_event "
                    "WHERE published_at IS NULL AND attempts < :maxa "
                    "  AND (next_attempt_at IS NULL OR next_attempt_at <= now()) "
                    "ORDER BY occurred_at "
                    "LIMIT :lim "
                    "FOR UPDATE SKIP LOCKED"
                ),
                {"maxa": int(max_attempts), "lim": int(limit)},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_publishable 실패: %s", str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return []


async def mark_published(db: AsyncSession, event_id: str, *, commit: bool = False) -> int:
    """발행 확정(published_at=now·status=PUBLISHED). **WHERE published_at IS NULL** 가드로 원자.

    반환: 갱신된 행 수(1=이 호출이 최초 발행 확정, 0=이미 발행됨/경쟁 패배). commit 은
    보통 호출부(디스패처)가 배치로 하므로 기본 False.
    """
    try:
        res = await db.execute(
            text(
                "UPDATE outbox_event SET published_at=now(), status='PUBLISHED' "
                "WHERE event_id=:eid AND published_at IS NULL"
            ),
            {"eid": event_id},
        )
        if commit:
            await db.commit()
        return int(res.rowcount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("mark_published 실패(%s): %s", str(event_id)[:16], str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return 0


async def mark_failed(
    db: AsyncSession, event_id: str, error: str | None, *, commit: bool = False
) -> bool:
    """발행 실패 기록: attempts+1·last_error·next_attempt_at(백오프). 이미 발행된 행은 불변.

    백오프 계산은 DB에 저장된 attempts+1 을 기준으로 next_backoff_seconds 를 쓴다(순수 도메인
    함수와 동일 계약).
    """
    try:
        # 현재 attempts 를 읽어 다음 백오프를 계산(발행된 행은 건너뜀).
        row = (
            await db.execute(
                text(
                    "SELECT attempts FROM outbox_event "
                    "WHERE event_id=:eid AND published_at IS NULL"
                ),
                {"eid": event_id},
            )
        ).first()
        if row is None:
            return False
        next_attempts = int(row[0] or 0) + 1
        backoff = next_backoff_seconds(next_attempts)
        new_status = "PENDING" if should_retry(next_attempts) else "DEAD"
        await db.execute(
            text(
                "UPDATE outbox_event SET attempts=attempts+1, last_error=:err, "
                "  status=:st, next_attempt_at=now() + make_interval(secs => :bo) "
                "WHERE event_id=:eid AND published_at IS NULL"
            ),
            {"eid": event_id, "err": (error or "")[:500] or None, "st": new_status, "bo": backoff},
        )
        if commit:
            await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("mark_failed 실패(%s): %s", str(event_id)[:16], str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False
