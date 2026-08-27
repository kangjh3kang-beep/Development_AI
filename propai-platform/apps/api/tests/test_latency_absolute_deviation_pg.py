"""절대편차 **배선**을 실 Postgres 로 태우는 락.

★순수 함수만 잠그면 배선은 무잠금이다 — 이 저장소에서 하루에 네 번 데인 자리다
  (`#889`: 스텁 기반 유의미 변이 16개 중 **12개 생존**). 여기서는 `_analyze_latency_regression`
  **전체**를 태워 *"평소값 조회 → 절대편차 판정 → metrics_json 에 실림"* 이 이어지는지 본다.

## 게이트 정책 (형제 `test_selection_contamination_sql_pg.py` 와 동일)

`TEST_PG_DSN` 이 **설정됐는데 못 붙으면 fail**, 미설정이면 skip.
★CI 는 `-n auto` 병렬이므로 **테스트마다 전용 스키마**로 격리한다 — `build_layer2_status`
  계열이 전역 집계를 읽어 옆 워커의 행이 섞였던 전례가 있다(`#889` 실측).
"""
from __future__ import annotations

import contextlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.growth import analyzer as az

_EXPLICIT_DSN = os.environ.get("TEST_PG_DSN")
_DSN = _EXPLICIT_DSN or "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db"

pytestmark = pytest.mark.asyncio

_W1 = datetime(2026, 8, 27, 8, 5, tzinfo=UTC)
_W0 = _W1 - timedelta(hours=1)


@pytest_asyncio.fixture
async def db():
    schema = "absdev_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(_DSN, future=True)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    except Exception as e:  # noqa: BLE001
        await admin.dispose()
        if _EXPLICIT_DSN:
            pytest.fail(f"TEST_PG_DSN 이 설정됐는데 실 Postgres 준비 실패 — 무잠금이다: {e}")
        pytest.skip(f"로컬에 Postgres 없음(스킵): {e}")

    engine = create_async_engine(
        _DSN, future=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with engine.begin() as conn:
        # ★DDL 을 손으로 쓰지 않는다 — **프로덕션 메타데이터**로 만든다
        import apps.api.database.models.platform_event  # noqa: F401
        from apps.api.database.models.base import Base

        names = [n for n in ("platform_events", "platform_insights") if n in Base.metadata.tables]
        assert "platform_events" in names and "platform_insights" in names, names
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[Base.metadata.tables[n] for n in names], checkfirst=True))
        assert (await conn.execute(text("SELECT current_schema()"))).scalar() == schema

    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        try:
            yield s
        finally:
            with contextlib.suppress(Exception):
                await s.rollback()
    await engine.dispose()
    with contextlib.suppress(Exception):
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


async def _events(db, *, route, n, latency):
    for _ in range(n):
        await db.execute(text(
            "INSERT INTO platform_events (event_id, event_type, surface, route, "
            " status_code, latency_ms, created_at) "
            "VALUES (:e,'api_call','api',:r,200,:l,:c)"),
            {"e": uuid.uuid4().hex, "r": route, "l": latency,
             "c": _W0 + timedelta(minutes=1)})


async def _history(db, *, route, p95s, itype="latency_baseline"):
    """그 route 의 과거 `p95_ms` 이력을 심는다(평소값의 재료)."""
    for i, p in enumerate(p95s):
        # ★`id` 는 DB 기본값이 없다(앱이 uuid4 로 만든다 — `platform_event.py:101`)
        await db.execute(text(
            "INSERT INTO platform_insights (id, insight_type, window_start, window_end, "
            " metrics_json, severity, narrative, recommended_action, status) "
            "VALUES (CAST(:i AS uuid), :t, :ws, :we, CAST(:m AS jsonb), 'info', 'n', 'none', 'open')"),
            {"i": str(uuid.uuid4()), "t": itype,
             "ws": _W0 - timedelta(hours=i + 2), "we": _W0 - timedelta(hours=i + 1),
             "m": json.dumps({"key": route, "p95_ms": p, "baseline_p95": p})})


async def _run(db):
    out = await az._analyze_latency_regression(db, _W0, _W1, None)
    return {i["metrics_json"]["key"]: i for i in out}


async def test_absolute_axis_fires_end_to_end(db):
    """★★전 구간 — 평소값 조회부터 `triggers` 에 실리기까지."""
    r = "/api/v1/zoning/parcel-boundaries"
    await _history(db, route=r, p95s=[23000.0, 23524.0, 24000.0, 23100.0])
    await _events(db, route=r, n=25, latency=66230)
    await db.commit()

    got = await _run(db)
    assert r in got, f"판정이 안 나왔다 — 이 락이 공허하다: {list(got)}"
    m = got[r]["metrics_json"]
    assert "absolute" in m["triggers"], f"절대편차 축이 안 걸렸다: {m}"
    assert got[r]["severity"] == "warn"
    assert got[r]["insight_type"] == "latency_regression"
    # ★평소값이 응답에 실린다 — 사람이 「왜 울렸는지」를 알 수 있어야 한다
    assert m["typical_p95"] is not None and m["typical_windows"] >= 3


async def test_calm_route_does_not_fire_end_to_end(db):
    """★★두 모집단 — 같은 실행에서 정상 route 는 **울리지 않는다**."""
    r = "/api/v1/auth/login"
    await _history(db, route=r, p95s=[590.0, 594.0, 600.0, 588.0])
    await _events(db, route=r, n=25, latency=594)
    await db.commit()

    got = await _run(db)
    assert r in got
    m = got[r]["metrics_json"]
    assert m["triggers"] == [], f"정상인데 울렸다: {m}"
    assert got[r]["severity"] == "info"
    assert got[r]["insight_type"] == "latency_baseline"


async def test_too_few_windows_withholds_absolute_axis(db):
    """★평소값을 만들 창이 모자라면 절대편차는 **판정하지 않는다**(비율만 남는다)."""
    r = "/api/v1/new-route"
    await _history(db, route=r, p95s=[100.0])          # 창 1개 — 하한 미달
    await _events(db, route=r, n=25, latency=99999)
    await db.commit()

    got = await _run(db)
    m = got[r]["metrics_json"]
    assert "absolute" not in m["triggers"], f"창이 모자란데 절대편차가 걸렸다: {m}"
    assert m["typical_p95"] is None, "「모름」을 수치로 위장했다"
    assert m["typical_windows"] == 1


async def test_typical_is_not_dragged_by_the_outage_itself(db):
    """★★장애 시간창이 이력에 쌓여도 **평소값이 밀리면 안 된다** — 밀리면 다음 장애를 놓친다."""
    r = "/api/v1/analysis-ledger/history"
    # 정상 4창 + 장애 2창이 이미 이력에 있다
    await _history(db, route=r, p95s=[3000.0, 3045.0, 3100.0, 3050.0, 13763.0, 20000.0])
    await _events(db, route=r, n=25, latency=13763)
    await db.commit()

    got = await _run(db)
    m = got[r]["metrics_json"]
    assert m["typical_p95"] < 5000, f"평소값이 장애에 밀렸다: {m['typical_p95']}"
    assert "absolute" in m["triggers"], "평소값이 밀려 장애를 놓쳤다"


async def test_ratio_axis_still_works_independently(db):
    """★절대편차를 넣었다고 **비율 축이 죽으면 안 된다**(둘은 보완재다).

    `/api/v1/ai/status`: 평소 70ms → 3,282ms = 47배. 편차 3.2초 < 5초라
    **절대편차로는 안 잡히고 비율로만** 잡혀야 한다.
    """
    r = "/api/v1/ai/status"
    await _history(db, route=r, p95s=[70.0, 70.0, 72.0, 68.0])
    await _events(db, route=r, n=25, latency=3282)
    await db.commit()

    got = await _run(db)
    m = got[r]["metrics_json"]
    assert "ratio" in m["triggers"], f"비율 축이 죽었다: {m}"
    assert "absolute" not in m["triggers"], f"절대편차가 이걸 잡으면 안 된다: {m}"
    assert got[r]["severity"] == "warn"


async def test_absolute_axis_alone_drives_severity(db):
    """★★**절대편차만** 걸리는 경우 — 비율은 임계 미만인데 severity 가 warn 이어야 한다.

    종전 종단 테스트는 **비율 축도 함께 발화**해서, `sev = ratio_sev or abs_sev` 를
    `sev = ratio_sev` 로 바꾸는 변이가 **생존**했다(실측). 즉 절대편차가 `severity` 에
    기여하는지가 **원리적으로 안 잠겨** 있었다.

    평소 23,524ms · 현재 33,000ms → 비율 **1.40배**(임계 1.5 미만) · 편차 **9,476ms**(임계 5초 초과).
    """
    r = "/api/v1/zoning/parcel-boundaries"
    await _history(db, route=r, p95s=[23524.0, 23524.0, 23524.0, 23524.0])
    await _events(db, route=r, n=25, latency=33000)
    await db.commit()

    got = await _run(db)
    m = got[r]["metrics_json"]
    # ★두 모집단이 같은 실행에서 갈린다 — 비율은 조용하고 절대편차만 운다
    assert "ratio" not in m["triggers"], f"비율이 걸렸다 — 이 케이스가 절대편차를 고립 못 시킨다: {m}"
    assert "absolute" in m["triggers"], f"절대편차가 안 걸렸다: {m}"
    # ★그리고 그것이 **severity 까지** 밀어야 한다(W1 변이가 여기서 죽는다)
    assert got[r]["severity"] == "warn", f"절대편차가 severity 에 반영되지 않았다: {got[r]}"
    assert got[r]["insight_type"] == "latency_regression"
    assert got[r]["recommended_action"] == "heal"
