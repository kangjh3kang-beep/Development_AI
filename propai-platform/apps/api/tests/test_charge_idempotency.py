"""과금 단위 멱등 — **실 Postgres 를 태우는** 락.

## 왜 실 DB 인가 (이게 이 파일의 존재 이유다)

`app/core/idempotency.py` 는 fail-open 이다 — DB 를 못 쓰면 조용히 "처음 보는 키"로 판정한다.
CI 백엔드 잡에는 `services: postgres` 가 **없었다**. 그래서 그 모듈을 태운다던 기존 테스트는
`ensure_schema` 실패 → `lookup` 이 무조건 miss → **무엇을 단언하든 통과**하는 구조였다.
`ON CONFLICT (COALESCE(...), ...)` 같은 표현식 인덱스 추론이 진짜 Postgres 에서 성립하는지
**한 번도 확인된 적이 없다.**

돈 가드에서 그건 허용할 수 없다. 이 파일은 실 Postgres 에 붙고, **CI 에서 DB 가 없으면 skip 이
아니라 fail** 한다(조용한 초록 금지). CI 워크플로에 postgres 서비스를 함께 추가했다.

## 네 모집단 (계획서는 셋만 적었다 — 넷째가 봉합 대상 그 자체다)

| 모집단 | 기대 | 이게 없으면 |
|---|---|---|
| 같은 키 **순차** 2회 | 두 번째는 `settled` → **과금 안 함** | 재시도가 이중청구 |
| **다른** 키 2회 | 둘 다 `reserved` → 2회분 과금 | "멱등성"이 그냥 "과금 안 함"과 구분 안 됨 |
| 같은 키 **다른 바디** | `conflict` → 422 | 키 오사용이 무음 통과 |
| ★같은 키 **동시** 2회 | 두 번째는 `in_flight` → 409 | **`lookup`/`save` 방식이 놓치는 바로 그 구멍**(둘 다 miss → 둘 다 과금) |

★넷이 **서로 다른 결과**를 내야 잠금이다. 차가 0이면 배선을 끊어도 통과한다.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import charge_idempotency as ci

# ★게이트 조건을 `CI` 환경변수가 아니라 **`TEST_PG_DSN` 의 존재**에 건다.
#   `CI` 에 기대면 "GitHub Actions 가 CI=true 를 준다"는 **내가 확인하지 않은 전제**에 락 전체가
#   매달린다 — 그 전제가 틀리면 17건이 조용히 skip 되고, fail-open 모듈이라 아무도 모른다.
#   반면 `TEST_PG_DSN` 은 **우리 워크플로가 직접 설정**하는 값이라 확인 가능한 사실이다.
#     · 설정돼 있는데 못 붙으면 → **fail**(누군가 DB 를 주기로 해 놓고 안 준 것이다)
#     · 설정이 없으면 → skip(로컬 편의). 로컬은 게이트가 아니므로 허용된다.
_EXPLICIT_DSN = os.environ.get("TEST_PG_DSN")
_DSN = _EXPLICIT_DSN or "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db"
_ENDPOINT = "test.charge_idem"


def _hash(payload: dict) -> str:
    return ci.compute_request_hash(payload)


def _key() -> str:
    return f"k-{uuid.uuid4()}"


def _scope() -> str:
    return ci.scope_id(uuid.uuid4(), uuid.uuid4())


@pytest_asyncio.fixture
async def sessions():
    """서로 **다른 커넥션** 두 개 — 동시성 모집단을 진짜로 재현하기 위해서다.

    한 세션에서 두 번 부르면 같은 트랜잭션 맥락이라 '동시'가 아니다.
    """
    engine = create_async_engine(_DSN, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as probe:
            await probe.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        await engine.dispose()
        msg = f"Postgres 에 붙지 못했다({_DSN}): {str(e)[:200]}"
        if _EXPLICIT_DSN:
            # ★TEST_PG_DSN 을 준 환경에서는 **절대 skip 하지 않는다** — fail-open 모듈이라
            #   skip 은 곧 무잠금이고, 그 무잠금이 초록으로 보인다.
            pytest.fail(f"TEST_PG_DSN 이 설정됐는데 붙지 못했다 — 이 락은 실 DB 를 태워야 한다. {msg}")
        pytest.skip(msg)

    ci._SCHEMA_READY = False  # 테스트마다 schema_guard 를 실제로 태운다
    async with maker() as a, maker() as b:
        yield a, b
    await engine.dispose()


# ── 네 모집단 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_같은_키_순차_2회는_두_번째가_과금대상이_아니다(sessions):
    a, _ = sessions
    key, scope, h = _key(), _scope(), _hash({"parcels": ["1", "2"]})

    first = await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    assert first.state == ci.STATE_RESERVED
    assert first.billable is True
    await ci.settle(db=a, key=key, scope=scope, endpoint=_ENDPOINT)

    second = await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    assert second.state == ci.STATE_SETTLED
    assert second.billable is False, "이미 청구된 키인데 또 과금 대상이 됐다 — 이중청구"


@pytest.mark.asyncio
async def test_다른_키_2회는_둘_다_과금대상이다(sessions):
    """★이 케이스가 없으면 '멱등성'과 '아무것도 과금 안 함'을 구분할 수 없다."""
    a, _ = sessions
    scope, h = _scope(), _hash({"parcels": ["1"]})

    r1 = await ci.reserve(db=a, key=_key(), scope=scope, endpoint=_ENDPOINT, request_hash=h)
    r2 = await ci.reserve(db=a, key=_key(), scope=scope, endpoint=_ENDPOINT, request_hash=h)
    assert (r1.state, r2.state) == (ci.STATE_RESERVED, ci.STATE_RESERVED)
    assert r1.billable and r2.billable, "다른 키인데 과금이 한 번만 나가면 매출 누수다"


@pytest.mark.asyncio
async def test_같은_키_다른_바디는_conflict(sessions):
    a, _ = sessions
    key, scope = _key(), _scope()

    await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT,
                     request_hash=_hash({"parcels": ["1"]}))
    dup = await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT,
                           request_hash=_hash({"parcels": ["1", "2"]}))
    assert dup.state == ci.STATE_CONFLICT


@pytest.mark.asyncio
async def test_동시_같은_키는_두_번째가_in_flight(sessions):
    """★넷째 모집단 — `lookup`/`save` 방식이 놓치는 구멍.

    첫 요청이 아직 안 끝났는데(정산 전) 같은 키가 또 오면, 저장 기반 방식은 **둘 다 miss** 를
    받아 둘 다 실행·과금한다. 선점이 있으면 두 번째는 여기서 멈춘다.
    """
    a, b = sessions
    key, scope, h = _key(), _scope(), _hash({"parcels": ["1"]})

    first = await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    # ★settle 을 부르지 않는다 = 첫 요청이 아직 처리 중이라는 뜻.
    second = await ci.reserve(db=b, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)

    assert first.state == ci.STATE_RESERVED
    assert second.state == ci.STATE_IN_FLIGHT, (
        "처리 중인 키를 두 번째 요청이 그대로 가져갔다 — 동시 이중청구가 그대로 난다"
    )
    assert first.billable and not second.billable


# ── 경계·회복 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_실패해서_선점을_풀면_같은_키로_재시도할_수_있다(sessions):
    """실패는 재시도의 가장 흔한 이유다 — 그 재시도를 우리가 막으면 안 된다."""
    a, _ = sessions
    key, scope, h = _key(), _scope(), _hash({"parcels": ["1"]})

    assert (await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT,
                             request_hash=h)).state == ci.STATE_RESERVED
    await ci.release(db=a, key=key, scope=scope, endpoint=_ENDPOINT)
    again = await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    assert again.state == ci.STATE_RESERVED


@pytest.mark.asyncio
async def test_정산된_키는_release_로_풀리지_않는다(sessions):
    """★`release` 가 정산 행까지 지우면 중복청구 방지가 통째로 풀린다."""
    a, _ = sessions
    key, scope, h = _key(), _scope(), _hash({"parcels": ["1"]})

    await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    await ci.settle(db=a, key=key, scope=scope, endpoint=_ENDPOINT)
    await ci.release(db=a, key=key, scope=scope, endpoint=_ENDPOINT)

    after = await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    assert after.state == ci.STATE_SETTLED, "정산 기록이 release 로 지워졌다 — 재청구가 난다"


@pytest.mark.asyncio
async def test_사용자가_다르면_같은_키라도_섞이지_않는다(sessions):
    """★스코프가 테넌트뿐이면 같은 회사 소속 타인이 남의 결제를 재생받는다."""
    a, _ = sessions
    tenant = uuid.uuid4()
    key, h = _key(), _hash({"parcels": ["1"]})
    scope_u1 = ci.scope_id(tenant, uuid.uuid4())
    scope_u2 = ci.scope_id(tenant, uuid.uuid4())

    r1 = await ci.reserve(db=a, key=key, scope=scope_u1, endpoint=_ENDPOINT, request_hash=h)
    await ci.settle(db=a, key=key, scope=scope_u1, endpoint=_ENDPOINT)
    r2 = await ci.reserve(db=a, key=key, scope=scope_u2, endpoint=_ENDPOINT, request_hash=h)

    assert r1.state == ci.STATE_RESERVED
    assert r2.state == ci.STATE_RESERVED, "같은 테넌트의 다른 사용자가 남의 정산을 물려받았다"


@pytest.mark.asyncio
async def test_엔드포인트가_다르면_키가_섞이지_않는다(sessions):
    a, _ = sessions
    key, scope, h = _key(), _scope(), _hash({"parcels": ["1"]})

    await ci.reserve(db=a, key=key, scope=scope, endpoint="registry.bulk", request_hash=h)
    await ci.settle(db=a, key=key, scope=scope, endpoint="registry.bulk")
    other = await ci.reserve(db=a, key=key, scope=scope, endpoint="registry.analyze",
                             request_hash=h)
    assert other.state == ci.STATE_RESERVED


@pytest.mark.asyncio
async def test_죽은_선점은_만료_뒤_인수된다(sessions):
    """서버가 처리 중에 죽으면 키가 영구히 409 로 잠긴다 — 그걸 막는 인수 경로."""
    a, b = sessions
    key, scope, h = _key(), _scope(), _hash({"parcels": ["1"]})

    await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    # 선점을 TTL 보다 오래된 것으로 만든다(= 처리하던 프로세스가 죽었다).
    await a.execute(text(
        "UPDATE charge_idempotency SET created_at = now() - make_interval(secs => :age) "
        "WHERE scope_id = :s AND endpoint = :e AND idempotency_key = :k"
    ), {"age": ci._INFLIGHT_TTL_S + 60, "s": scope, "e": _ENDPOINT, "k": key})
    await a.commit()

    taken = await ci.reserve(db=b, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    assert taken.state == ci.STATE_RESERVED, "죽은 선점이 키를 영구히 잠갔다"


@pytest.mark.asyncio
async def test_프루닝이_만료행을_지운다(sessions):
    """`idempotency_key` 에 없어서 문제가 됐던 부분 — 무한 증식 방지."""
    a, _ = sessions
    key, scope, h = _key(), _scope(), _hash({"parcels": ["1"]})

    await ci.reserve(db=a, key=key, scope=scope, endpoint=_ENDPOINT, request_hash=h)
    await a.execute(text(
        "UPDATE charge_idempotency SET created_at = now() - make_interval(secs => :age) "
        "WHERE scope_id = :s AND endpoint = :e AND idempotency_key = :k"
    ), {"age": ci._SETTLED_TTL_S + 60, "s": scope, "e": _ENDPOINT, "k": key})
    await a.commit()

    assert await ci.prune_expired(a) >= 1
    left = (await a.execute(text(
        "SELECT count(*) FROM charge_idempotency WHERE idempotency_key = :k"
    ), {"k": key})).scalar()
    assert left == 0


# ── 구조 락(개인정보) ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_이_테이블은_응답_본문을_담을_칸이_없다(sessions):
    """★이 계약을 코드가 아니라 **스키마**로 못 박는다.

    응답 재생 방식이 문제였던 이유는 저장 대상이 등기부 전문·무인증 `pdf_url` 이라는 점이다.
    본문을 담을 칸 자체가 없으면 나중에 누가 "재생도 넣자"고 해도 **스키마에서 먼저 막힌다**.
    (칸이 생기면 이 테스트가 빨개진다 — 그때 개인정보 보존기간을 다시 논의하라는 신호다.)
    """
    a, _ = sessions
    await ci.ensure_schema(a)
    cols = {r[0] for r in (await a.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'charge_idempotency'"
    ))).all()}
    assert cols, "테이블이 없다 — schema_guard 가 안 돌았다(공허 진리 가드)"
    forbidden = {c for c in cols if any(
        t in c.lower() for t in ("body", "response", "payload", "pdf", "content")
    )}
    assert not forbidden, f"응답 본문을 담을 수 있는 칸이 생겼다: {sorted(forbidden)}"
