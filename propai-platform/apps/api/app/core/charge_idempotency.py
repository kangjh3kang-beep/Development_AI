"""과금 단위 멱등 — **응답을 재생하지 않는다. 중복 청구만 막는다.**

## 왜 `app/core/idempotency.py` 를 그대로 쓰지 않는가

그 모듈은 **응답 재생기**다(요청 지문 → 저장된 응답 바이트 → 그대로 반환). 설계 승인·제출번들
에서는 옳다 — 바탕 연산이 결정적이고 무료라, 같은 입력이면 같은 바이트가 정답이다.

등기 발급·권리분석에 그 계약을 그대로 옮기면 **재생하려는 바이트가 문제**가 된다:

| 옮겼을 때 생기는 것 | 왜 |
|---|---|
| 개인정보 영구 사본 | 저장 대상이 등기부 전문(`pdf_base64`)과 **무인증 30일 URL**(`pdf_url`)이다. `idempotency_key` 테이블엔 만료도 프루닝도 없어, 30일 TTL 삭제(`/registry/cleanup`)를 **우회하는 사본**이 무기한 쌓인다 |
| 대량 요청에서 무음 재과금 | 8MB 초과 시 본문 미저장 → 재생 불가 → **재실행**으로 강등된다. 100필지 bulk 는 일상적으로 그 선을 넘는다 — 돈이 가장 많이 걸린 요청이 정확히 멱등성이 꺼지는 요청이 된다 |
| 부분 성공 영구 동결 | 20필지 중 5건만 발급된 응답이 저장되면, 같은 키 재시도는 **재생**이라 나머지 15건이 영영 조회되지 않는다 |
| 영구 stale | 만료가 없으니 3개월 전 권리분석이 계속 재생된다. **등기부는 변한다**(근저당·소유자) |

## 그래서 계약을 바꾼다

우리가 막고 싶은 것은 바이트가 아니라 **돈**이다.

- `Idempotency-Key` 는 **한 번의 과금 단위**를 가리킨다(응답 스냅샷이 아니다).
- 같은 키 재요청 → **정상 실행하되 과금만 건너뛴다.** 읽기는 기존 캐시(권리분석 6시간/7일)가
  흡수하므로 외부 발급이 다시 나가지도 않는다(`issued_count` 는 캐시 적중을 0건으로 센다).
  → 부분 성공은 재시도가 마저 채우고, 결과는 항상 최신이며, **본문을 한 바이트도 저장하지 않는다.**
- 동시 요청 → 두 번째는 **409**(선점 행이 있으므로). 이것이 이 모듈의 존재 이유다:
  `lookup`/`save` 만으로는 **둘 다 miss 를 받아 둘 다 과금한다** — 발급이 수 초 걸리는 동안
  선점이 없기 때문이다. `ON CONFLICT DO NOTHING` 은 저장 행만 지키지 부작용은 이미 다 난 뒤다.

## 스코프 — 테넌트만으로는 부족하다

`idempotency_key` 의 유니크는 `(tenant, endpoint, key)` 라 **같은 회사 소속 타인**이 같은 키를
쓰면 남이 결제한 결과를 재생받는다. 이 라우터는 이미 그보다 엄격한 계약을 세웠다
(`routers/registry.py` 의 잡 조회 IDOR 가드 — "등기 결과는 제출자만"). 그래서 여기 스코프는
**테넌트+사용자**다.

## 영속 계약

alembic 신규 헤드 없음 — `CREATE TABLE IF NOT EXISTS` 기반 schema_guard(멱등·lazy·부팅안전).
`idempotency.py`·outbox·design_run_store 와 같은 선례. 원장(`coin_ledger_events`) 무접촉.

## fail-open 과 그 정직한 한계

DB 를 못 쓰면 종전과 동일하게 실행·과금한다(멱등 보호만 사라진다). ★이 선택의 대가는
**보호가 꺼져도 조용하다**는 것이다 — 그래서 `reserve` 는 `UNAVAILABLE` 을 **명시 상태로**
돌려주고 호출부가 그 사실을 로그에 남긴다. "배선했는데 무잠금"을 무음으로 두지 않는다.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.idempotency import compute_request_hash, normalize_key

logger = structlog.get_logger(__name__)

__all__ = [
    "STATE_CONFLICT",
    "STATE_IN_FLIGHT",
    "STATE_RESERVED",
    "STATE_SETTLED",
    "STATE_UNAVAILABLE",
    "Reservation",
    "compute_request_hash",
    "normalize_key",
    "prune_expired",
    "release",
    "reserve",
    "scope_id",
    "settle",
]

# ── 상태 ─────────────────────────────────────────────────────────────────
STATE_RESERVED = "reserved"        # 내가 선점했다 — 실행하고 **과금하라**. 끝나면 settle.
STATE_IN_FLIGHT = "in_flight"      # 다른 요청이 처리 중 — 호출부는 409.
STATE_SETTLED = "settled"          # 이 키로 이미 청구됐다 — 실행하되 **과금하지 마라**.
STATE_CONFLICT = "conflict"        # 같은 키, 다른 요청 — 호출부는 422(키 오사용).
STATE_UNAVAILABLE = "unavailable"  # 저장소를 못 씀 — fail-open(종전대로 실행·과금).

# 선점이 이보다 오래되면 **죽은 요청**으로 보고 인수한다(서버가 중간에 죽으면 키가 영구히
# 잠기기 때문). 등기 일괄 조회의 실제 상한(프론트 타임아웃 120초)보다 넉넉히 잡는다.
_INFLIGHT_TTL_S = 600
# 정산 기록의 보존 기간. 이 뒤엔 같은 키가 다시 과금된다 — 무기한이면 키 하나로 영원히
# 무료가 되고, 그건 매출 누수다(과소청구도 결함이다).
_SETTLED_TTL_S = 86_400  # 24h

_SCHEMA_READY = False

_DDL = (
    "CREATE TABLE IF NOT EXISTS charge_idempotency ("
    "  id bigserial PRIMARY KEY,"
    "  scope_id text NOT NULL,"          # 테넌트+사용자 — 교차 재생 차단
    "  endpoint text NOT NULL,"
    "  idempotency_key text NOT NULL,"
    "  request_hash text NOT NULL,"
    "  state text NOT NULL,"
    "  created_at timestamptz NOT NULL DEFAULT now(),"
    "  settled_at timestamptz"
    ")"
)
_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_charge_idem_scope "
    "ON charge_idempotency (scope_id, endpoint, idempotency_key)",
    # 프루닝용 — 만료 삭제가 전체 스캔이 되지 않도록.
    "CREATE INDEX IF NOT EXISTS ix_charge_idem_created ON charge_idempotency (created_at)",
)


def scope_id(tenant_id: Any, user_id: Any) -> str:
    """키 공간의 소유자 — **테넌트+사용자**. 둘 다 문자열로 강제한다.

    ★`CurrentUser.tenant_id`/`user_id` 는 `UUID` 다. text 컬럼에 UUID 객체를 그대로 바인딩하면
      드라이버에 따라 던지거나 조용히 다른 표현으로 저장된다 — 어느 쪽이든 **무음 무력화**다.
    """
    return f"{tenant_id or ''}:{user_id or ''}"


@dataclass
class Reservation:
    """`reserve()` 결과 — 상태와, 과금해도 되는지."""

    state: str

    @property
    def billable(self) -> bool:
        """이번 호출에서 과금해도 되는가.

        ★`unavailable`(저장소 장애)도 True 다 — fail-open 은 **과금을 막지 않는다**.
          여기서 False 를 내면 DB 장애가 곧 전량 무료가 된다(과소청구).
        """
        return self.state in (STATE_RESERVED, STATE_UNAVAILABLE)

    @property
    def owns_reservation(self) -> bool:
        """settle/release 로 마무리해야 하는 상태인가."""
        return self.state == STATE_RESERVED


async def ensure_schema(db: Any, force: bool = False) -> bool:
    """테이블·인덱스를 멱등 보장. 실패는 graceful(rollback 후 False)."""
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return True
    from sqlalchemy import text

    try:
        await db.execute(text(_DDL))
        for ix in _INDEXES:
            await db.execute(text(ix))
        await db.commit()
        _SCHEMA_READY = True
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("charge_idempotency schema_guard 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def reserve(
    *, db: Any, key: str, scope: str, endpoint: str, request_hash: str
) -> Reservation:
    """키를 **선점**한다. 실행·과금 **전에** 부른다(그게 이 모듈의 전부다).

    ★순서가 계약이다 — 선점이 실행보다 **앞**이어야 동시 요청이 갈라진다. 뒤에 두면
      `idempotency.save` 와 똑같아져 둘 다 실행·과금한 뒤에야 충돌을 안다.
    """
    from sqlalchemy import text

    if not await ensure_schema(db):
        return Reservation(STATE_UNAVAILABLE)

    params = {"scope": scope, "ep": endpoint, "key": key, "rh": request_hash}
    try:
        # ① 빈자리면 내가 잡는다. 경쟁에서 진 쪽은 0행을 받는다(그게 신호다).
        got = (await db.execute(text(
            "INSERT INTO charge_idempotency "
            "(scope_id, endpoint, idempotency_key, request_hash, state) "
            "VALUES (:scope, :ep, :key, :rh, 'in_flight') "
            "ON CONFLICT (scope_id, endpoint, idempotency_key) DO NOTHING "
            "RETURNING id"
        ), params)).first()
        await db.commit()
        if got is not None:
            return Reservation(STATE_RESERVED)

        # ② 이미 행이 있다 — 지문·상태·나이를 본다.
        row = (await db.execute(text(
            "SELECT request_hash, state, created_at, "
            "       EXTRACT(EPOCH FROM (now() - created_at)) AS age_s "
            "FROM charge_idempotency "
            "WHERE scope_id = :scope AND endpoint = :ep AND idempotency_key = :key"
        ), params)).first()
        if row is None:
            # 조회 사이에 프루닝이 지웠다 — 한 번 더 잡아 본다(못 잡으면 fail-open).
            return Reservation(STATE_UNAVAILABLE)

        stored_hash, state, created_at, age_s = row[0], row[1], row[2], float(row[3] or 0)
        if stored_hash != request_hash:
            return Reservation(STATE_CONFLICT)

        ttl = _INFLIGHT_TTL_S if state == "in_flight" else _SETTLED_TTL_S
        if age_s <= ttl:
            return Reservation(STATE_IN_FLIGHT if state == "in_flight" else STATE_SETTLED)

        # ③ 만료 — 인수한다. `created_at` 을 함께 걸어(낙관적 잠금) 두 인수자가 다 이기지 않게.
        res = await db.execute(text(
            "UPDATE charge_idempotency "
            "SET state = 'in_flight', created_at = now(), settled_at = NULL "
            "WHERE scope_id = :scope AND endpoint = :ep AND idempotency_key = :key "
            "  AND created_at = :seen"
        ), {**params, "seen": created_at})
        await db.commit()
        return Reservation(STATE_RESERVED if res.rowcount == 1 else STATE_IN_FLIGHT)
    except Exception as e:  # noqa: BLE001
        logger.warning("charge_idempotency reserve 실패(fail-open)", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return Reservation(STATE_UNAVAILABLE)


async def settle(*, db: Any, key: str, scope: str, endpoint: str) -> bool:
    """과금까지 끝났음을 확정한다. **반드시 과금 뒤**에 부른다.

    ★앞에서 부르면 과금 실패가 '청구 완료'로 박제되고, 사용자는 돈을 안 냈는데 재시도에서도
      청구되지 않는다(과소청구는 아무도 신고하지 않으므로 영원히 안 드러난다).
    """
    from sqlalchemy import text

    try:
        await db.execute(text(
            "UPDATE charge_idempotency SET state = 'settled', settled_at = now() "
            "WHERE scope_id = :scope AND endpoint = :ep AND idempotency_key = :key"
        ), {"scope": scope, "ep": endpoint, "key": key})
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("charge_idempotency settle 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def release(*, db: Any, key: str, scope: str, endpoint: str) -> bool:
    """실행이 실패했으니 선점을 **푼다** — 그래야 사용자가 같은 키로 다시 시도할 수 있다.

    ★이게 없으면 한 번 실패한 키가 `_INFLIGHT_TTL_S` 동안 409 로 막힌다. 실패는 재시도의
      가장 흔한 이유인데 그 재시도를 우리가 막는 꼴이 된다.
    ★`state='in_flight'` 인 행만 지운다 — 이미 정산된 행을 지우면 중복청구 방지가 풀린다.
    """
    from sqlalchemy import text

    try:
        await db.execute(text(
            "DELETE FROM charge_idempotency "
            "WHERE scope_id = :scope AND endpoint = :ep AND idempotency_key = :key "
            "  AND state = 'in_flight'"
        ), {"scope": scope, "ep": endpoint, "key": key})
        await db.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("charge_idempotency release 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return False


async def prune_expired(db: Any, *, older_than_s: int = _SETTLED_TTL_S) -> int:
    """만료 행을 지운다. 무한 증식 방지 — `idempotency_key` 에 없어서 문제가 됐던 그 부분이다."""
    from sqlalchemy import text

    if not await ensure_schema(db):
        return 0
    try:
        res = await db.execute(text(
            "DELETE FROM charge_idempotency "
            "WHERE created_at < now() - make_interval(secs => :age)"
        ), {"age": int(older_than_s)})
        await db.commit()
        return int(res.rowcount or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("charge_idempotency prune 실패", err=str(e)[:160])
        with contextlib.suppress(Exception):
            await db.rollback()
        return 0
