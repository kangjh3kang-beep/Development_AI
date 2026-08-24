"""선택 오염 집계 SQL 을 **실 Postgres 로 태우는** 락 (2026-08-24).

## 왜 실 DB 인가 (이 파일의 존재 이유)

`_analyze_selection_contamination` 의 위험은 파이썬이 아니라 **SQL** 에 있다:

  · `payload->>'spread_km'` 에 숫자가 아닌 값이 오면 `::numeric` 이 **예외**를 던진다.
  · 그 예외는 `analyze_window` 의 광역 `except` 가 삼켜 **그 윈도우의 인사이트가 전부 사라진다**
    — 내 지표가 남의 지표를 죽인다. 그런데 로그만 남고 테스트는 초록이다.
  · 수집 엔드포인트 `POST /api/v1/growth/events` 는 **익명 허용**이라 임의 payload 가 실제로 온다.

그래서 정규식 가드를 넣었는데, **POSIX 정규식·`~` 연산자·`CASE` 안에서의 캐스팅 지연**이
진짜 Postgres 에서 성립하는지는 파이썬 단위테스트로 **원리적으로** 확인할 수 없다.
문자열 검사(`test_K`)는 "정규식이 SQL 에 있다"까지만 말하고 "그게 실제로 막는다"는 말하지 못한다.

## 게이트 정책

`TEST_PG_DSN` 이 **설정돼 있는데 못 붙으면 fail**(누군가 DB 를 주기로 해 놓고 안 준 것),
설정이 없으면 skip(로컬 편의). `CI` 환경변수에 기대지 않는다 —
그건 내가 확인하지 않은 전제이고, 틀리면 이 락이 조용히 사라진다.
"""
from __future__ import annotations

import contextlib
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.growth import analyzer as az

_EXPLICIT_DSN = os.environ.get("TEST_PG_DSN")
_DSN = _EXPLICIT_DSN or "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db"

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(_DSN, future=True)
    try:
        # ★테이블을 손으로 CREATE 하지 않는다 — **프로덕션 ORM 메타데이터**로 만든다.
        #   손으로 쓰면 모델이 바뀔 때 내 테스트만 옛 스키마로 남아 조용히 갈라진다.
        import apps.api.database.models.platform_event  # noqa: F401
        from apps.api.database.models.base import Base

        tbl = Base.metadata.tables["platform_events"]
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[tbl], checkfirst=True))
    except Exception as e:  # noqa: BLE001
        await engine.dispose()
        if _EXPLICIT_DSN:
            pytest.fail(f"TEST_PG_DSN 이 설정됐는데 실 Postgres 준비 실패 — 무잠금이다: {e}")
        pytest.skip(f"로컬에 Postgres 없음(스킵): {e}")
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        try:
            yield s
        finally:
            # ★정리는 **teardown 에서 무조건** 한다. 종전엔 테스트 본문 끝에 뒀더니
            #   단언이 실패한 순간(변이 검증 중) DELETE 에 도달하지 못해 **잔재 153건**이
            #   쌓였고, 그 뒤 코드를 원복하고도 테스트가 계속 빨갰다 — 내 검증이 자기
            #   증거를 오염시킨 것이다. 실패해도 지워야 다음 실행이 깨끗하다.
            with contextlib.suppress(Exception):
                await s.rollback()
                await s.execute(
                    text("DELETE FROM platform_events WHERE service LIKE 'pgtest.%'")
                )
                await s.commit()
    await engine.dispose()


def _isolated_window(tag: int):
    """이 테스트만의 **먼 과거** 윈도우.

    ★`_CONTAM_SQL` 에는 service 필터가 없다(프로덕션은 전 테넌트를 집계해야 하니 옳다).
      그래서 `now-1h` 같은 창을 쓰면 **다른 테스트·다른 세션이 남긴 행**이 같은 창에 들어와
      건수 단언이 흔들린다. 실제로 그렇게 깨졌다. 창 자체를 격리한다.
    """
    from datetime import UTC, datetime, timedelta

    base = datetime(2001, 1, 1, tzinfo=UTC) + timedelta(days=tag)
    return base, base + timedelta(hours=1)


async def _seed(db, rows: list[dict]) -> str:
    """이 테스트 전용 마커 service 로 격리 삽입(다른 행과 섞이지 않게)."""
    marker = f"pgtest.{uuid.uuid4().hex[:12]}"
    for r in rows:
        await db.execute(text(
            "INSERT INTO platform_events (event_type, surface, service, payload, created_at) "
            "VALUES (:t, 'web', :svc, CAST(:p AS jsonb), :ts)"
        ), {
            "t": "selection_contamination_observation", "svc": marker,
            "p": r["payload"], "ts": r["ts"],
        })
    await db.commit()
    return marker


async def test_A_오염_SQL_이_실제_Postgres_에서_실행되고_집계가_맞다(db):
    from datetime import timedelta

    w0, w1 = _isolated_window(11)
    ts = w0 + timedelta(minutes=5)

    _marker = await _seed(db, [
        {"payload": '{"verdict":"multi_region","spread_km":15.94,"region_groups":2,"malformed_rows":0}', "ts": ts},
        {"payload": '{"verdict":"multi_region","spread_km":290.33,"region_groups":3,"malformed_rows":0}', "ts": ts},
        {"payload": '{"verdict":"multi_region","spread_km":null,"region_groups":2,"malformed_rows":0}', "ts": ts},
        {"payload": '{"verdict":"malformed","spread_km":null,"region_groups":1,"malformed_rows":4}', "ts": ts},
        # ★독성 행 — 익명 수집이라 실제로 올 수 있는 값. 이것 때문에 이 파일이 존재한다.
        {"payload": '{"verdict":"multi_region","spread_km":"열다섯","region_groups":2,"malformed_rows":"많음"}', "ts": ts},
        # 윈도우 밖(경계가 실제로 작동하는지) — 포함되면 안 된다.
        {"payload": '{"verdict":"malformed","spread_km":null,"region_groups":1,"malformed_rows":99}', "ts": w0 - timedelta(hours=2)},
        # 모르는 verdict — 집계에서 배제돼야 한다.
        {"payload": '{"verdict":"single_site","spread_km":0.1,"region_groups":1,"malformed_rows":0}', "ts": ts},
    ])

    rows = (await db.execute(text(
        az._CONTAM_SQL
    ), {"w0": w0, "w1": w1})).fetchall()
    agg = {r[0]: r for r in rows}

    # 공허 진리 가드 — 아무것도 안 나오면 아래 단언이 전부 무의미하다.
    assert agg, "집계 결과가 비었다 — SQL 이 대상을 못 찾았다"

    mr = agg.get("multi_region")
    assert mr is not None, "multi_region 군이 없다"
    # 윈도우 안 multi_region 4건(정상 3 + 독성 1). ★독성 행이 **버려지지 않고 세어진다** —
    #   숫자 하나가 깨졌다고 관측 자체를 없애면 빈도가 과소집계된다.
    assert int(mr[1]) == 4, f"multi_region 건수 불일치: {mr[1]}"
    # ★독성 문자열이 최대값 계산을 오염시키지 않는다(290.33 그대로).
    assert float(mr[2]) == pytest.approx(290.33), f"max_spread 오염: {mr[2]}"

    mal = agg.get("malformed")
    assert mal is not None and int(mal[1]) == 1          # 윈도우 밖 1건은 제외됐다
    assert int(mal[3]) == 4                               # malformed_rows 합
    assert mal[2] is None, "좌표가 없으면 **미상**이어야 한다 — 0 이 아니다"

    # 모르는 verdict 는 아예 군이 만들어지지 않는다.
    assert "single_site" not in agg



async def test_B_독성_payload_만_있어도_예외가_나지_않는다(db):
    """★가장 중요한 회귀 — 정규식 가드를 빼면 여기서 **DataError** 가 난다.

    그 예외는 프로덕션에서 `analyze_window` 의 광역 except 에 삼켜져
    **그 윈도우의 모든 인사이트**를 조용히 없앤다.
    """
    from datetime import timedelta

    w0, w1 = _isolated_window(22)
    _marker = await _seed(db, [
        {"payload": '{"verdict":"multi_region","spread_km":"DROP TABLE","malformed_rows":"NaN"}',
         "ts": w0 + timedelta(minutes=1)},
        {"payload": '{"verdict":"malformed","spread_km":"-","malformed_rows":"-"}',
         "ts": w0 + timedelta(minutes=2)},
    ])

    rows = (await db.execute(text(az._CONTAM_SQL), {"w0": w0, "w1": w1})).fetchall()
    agg = {r[0]: r for r in rows}
    assert agg, "독성 행만 있을 때 집계가 비었다 — 관측이 통째로 사라진다"
    assert int(agg["multi_region"][1]) == 1
    assert agg["multi_region"][2] is None, "숫자가 아니면 **미상**으로 남아야 한다"
    assert int(agg["malformed"][3]) == 0, "숫자가 아닌 행수는 0 으로 센다"

