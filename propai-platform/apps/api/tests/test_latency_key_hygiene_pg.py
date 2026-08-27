"""latency 모집단에서 **4xx 를 빼는** 필터를 실 Postgres 로 태우는 락 (2026-08-27).

## 왜 실 DB 인가

이 변경의 실체는 **SQL 술어 한 줄**이다:

    AND (status_code IS NULL OR status_code < 400 OR status_code >= 500)

술어의 의미는 파이썬 스텁으로 **원리적으로** 태울 수 없다 — 스텁은 SQL 문자열의 조각을
보고 답을 고르므로, `< 400` 을 `< 500` 으로 바꾸든 `>= 500` 절을 지우든 **같은 값**을 돌려준다.
(같은 함정이 `#889` 에서 실측됐다: 유의미 변이 16개 중 12개 생존.)

## 게이트 정책 (형제 `test_selection_contamination_sql_pg.py` 와 동일)

`TEST_PG_DSN` 이 **설정돼 있는데 못 붙으면 fail**, 설정이 없으면 skip.
`CI` 환경변수에 기대지 않는다 — 확인하지 않은 전제이고, 틀리면 이 락이 **조용히 사라진다**.
★CI 는 `-n auto` **병렬**이므로 **테스트마다 전용 스키마**로 격리한다
(집계 SQL 에 필터가 없으면 옆 워커의 행이 섞인다 — `#889` 에서 실측).

## ★이 락이 **못 보는** 것

`_analyze_latency_regression` 전체가 아니라 **모집단 질의**만 태운다. baseline 자기참조 ·
tenant 혼입 · n=20 p95 잡음은 **별건**이고 이 파일은 그것들을 잠그지 않는다.
"""
from __future__ import annotations

import contextlib
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

_W1 = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)
_W0 = _W1 - timedelta(hours=1)


@pytest_asyncio.fixture
async def db():
    """테스트마다 전용 스키마 — 병렬에서 옆 워커의 행이 섞이지 않게."""
    schema = "lat_t_" + uuid.uuid4().hex[:10]
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
        # ★DDL 을 손으로 쓰지 않는다 — **프로덕션 ORM 메타데이터**로 만든다.
        import apps.api.database.models.platform_event  # noqa: F401
        from apps.api.database.models.base import Base

        # ★analyzer 는 `platform_insights` 도 읽는다(baseline 조회) — 둘 다 만든다.
        #   손으로 DDL 을 쓰지 않고 **프로덕션 메타데이터**에서 파생한다.
        names = [n for n in ("platform_events", "platform_insights") if n in Base.metadata.tables]
        assert "platform_events" in names, f"모델 메타데이터에 테이블이 없다: {names}"
        tables = [Base.metadata.tables[n] for n in names]
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables, checkfirst=True))
        cur = (await conn.execute(text("SELECT current_schema()"))).scalar()
        assert cur == schema, f"search_path 가 안 먹었다: {cur}"

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


async def _seed(db, *, route, n, status, latency, event_type="api_call"):
    for _ in range(n):
        await db.execute(text(
            "INSERT INTO platform_events (event_id, event_type, surface, route, "
            " status_code, latency_ms, created_at) "
            "VALUES (:e, :t, 'api', :r, :s, :l, :c)"),
            {"e": uuid.uuid4().hex, "t": event_type, "r": route,
             "s": status, "l": latency, "c": _W0 + timedelta(minutes=1)})


async def _keys(db) -> dict[str, int]:
    """실제 analyzer 를 태우고 **어떤 key 가 판정 모집단에 들어왔는지** 돌려준다."""
    out = await az._analyze_latency_regression(db, _W0, _W1, None)
    return {i["metrics_json"]["key"]: i["metrics_json"]["samples"] for i in out}


async def test_scanner_404_keys_are_excluded_but_real_routes_survive(db):
    """★두 모집단이 **같은 실행에서** 갈린다 — 스캐너는 빠지고 진짜 라우트는 남는다."""
    await _seed(db, route="/.env", n=30, status=404, latency=5)          # 전건 404 스캐너
    await _seed(db, route="/api/v1/projects", n=30, status=200, latency=900)
    await db.commit()

    keys = await _keys(db)
    assert "/.env" not in keys, "404 스캐너가 모집단에 남았다"
    assert keys.get("/api/v1/projects") == 30, keys
    # ★공허 방지 — 판정이 하나도 없으면 위 단언이 거저 참이다
    assert keys, "판정이 0건이다 — 이 락이 공허하다"


async def test_5xx_is_kept(db):
    """★★`status < 400` 으로 자르면 **타임아웃 라우트가 가장 필요할 때 사라진다**.

    라이브 7일 5xx 는 **0건**이라 이 케이스는 프로덕션 데이터로는 확인할 수 없다 —
    그래서 **합성 입력으로** 태운다(현재 위반 0건인 것을 잠그는 유일한 방법).
    """
    await _seed(db, route="/api/v1/slow", n=25, status=504, latency=30000)
    await db.commit()
    keys = await _keys(db)
    assert keys.get("/api/v1/slow") == 25, f"5xx 를 모집단에서 뺐다 — 장애가 숨는다: {keys}"


async def test_null_status_is_kept_for_llm_calls(db):
    """★`llm_call` 은 HTTP 상태가 없다(라이브 73건). 빼면 LLM 지연을 못 본다."""
    await _seed(db, route=None, n=25, status=None, latency=8000, event_type="llm_call")
    await db.execute(text("UPDATE platform_events SET service = 'llm' WHERE route IS NULL"))
    await db.commit()
    keys = await _keys(db)
    assert keys.get("llm") == 25, f"NULL status 를 뺐다: {keys}"


async def test_mixed_key_keeps_only_non_4xx_samples(db):
    """★같은 key 안에서 **4xx 표본만** 빠진다(key 통째로 빠지지 않는다)."""
    await _seed(db, route="/api/v1/auth/me", n=25, status=200, latency=900)
    await _seed(db, route="/api/v1/auth/me", n=40, status=401, latency=3)
    await db.commit()
    keys = await _keys(db)
    # 4xx 40건이 빠지고 25건만 남는다 — 65 도 40 도 아니다
    assert keys.get("/api/v1/auth/me") == 25, f"혼합 key 의 표본 수가 틀렸다: {keys}"


async def test_key_falls_below_floor_when_only_4xx_remains(db):
    """★대조군 — 4xx 를 빼고 나면 하한에 못 미치는 key 는 **판정되지 않는다**."""
    await _seed(db, route="/api/v1/rare", n=5, status=200, latency=900)
    await _seed(db, route="/api/v1/rare", n=40, status=404, latency=3)
    await db.commit()
    keys = await _keys(db)
    assert "/api/v1/rare" not in keys, f"하한 미달인데 판정됐다: {keys}"
    # ★그리고 그것이 **보류로 계상**돼야 한다 — 조용히 사라지면 커버리지가 거짓말한다
    cov: dict[str, dict] = {}
    await az._analyze_latency_regression(db, _W0, _W1, cov)
    assert cov["latency_regression"]["withheld"] >= 1, cov


async def test_boundary_status_codes_are_classified_correctly(db):
    """★★경계를 **정확히** 태운다(독립 리뷰 F4).

    종전 시드는 `{200, 401, 404, 504, NULL}` 이라 **정확히 400 도 500 도 없었다.**
    그래서 `< 400` → `<= 400` · `>= 500` → `> 500` 변이가 **행위 테스트를 전부 통과**했다.
    라이브에는 `status_code = 400` 이 7일 **825건** 실재한다.
    """
    await _seed(db, route="/api/v1/b399", n=25, status=399, latency=100)   # 4xx 아님 → 남는다
    await _seed(db, route="/api/v1/b400", n=25, status=400, latency=100)   # ★경계 — 4xx → 빠진다
    await _seed(db, route="/api/v1/b499", n=25, status=499, latency=100)   # 4xx → 빠진다
    await _seed(db, route="/api/v1/b500", n=25, status=500, latency=100)   # ★경계 — 5xx → 남는다
    await db.commit()

    keys = await _keys(db)
    assert keys, "판정이 0건이다 — 이 락이 공허하다"
    # ★파티션 — 네 경계가 **서로 다르게** 갈린다
    assert "/api/v1/b399" in keys, f"399 를 4xx 로 잘못 뺐다: {sorted(keys)}"
    assert "/api/v1/b400" not in keys, f"400(4xx 시작)을 안 뺐다: {sorted(keys)}"
    assert "/api/v1/b499" not in keys, f"499 를 안 뺐다: {sorted(keys)}"
    assert "/api/v1/b500" in keys, f"500(5xx 시작)을 뺐다 — 장애가 숨는다: {sorted(keys)}"


def test_filter_is_in_the_population_query_specifically():
    """★필터가 **모집단 질의에** 있는가.

    ★★2026-08-27 독립 리뷰 F5 — 종전 판은 `ast.walk(fn)` 으로 **함수 전체**의 문자열을
      한 덩어리로 합쳤다. **독스트링**과 **baseline 질의**까지 섞여, *"모집단 질의에
      있는가"* 를 **안 잠갔다**(독스트링이 그 술어를 논하기만 해도 통과).
      → **`platform_events` 를 읽는 문자열만** 골라 본다.

    ★그리고 `"< 400"` 같은 **공백에 민감한 리터럴**을 쓰지 않는다 — 종전 판은 `< 400` 을
      `<400` 으로 **포매팅만 바꿔도 빨개지는 위양성**이었다(리뷰 F4). 의미는 위의
      **경계 행위 테스트**가 잠그고, 여기서는 *"모집단 질의가 status_code 를 본다"* 까지만.
    """
    import ast
    import inspect
    import textwrap

    fn = ast.parse(textwrap.dedent(inspect.getsource(az._analyze_latency_regression))).body[0]

    def _strings(needle: str) -> list[str]:
        return [
            n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and needle in n.value
        ]

    pop = _strings("platform_events")
    assert pop, "모집단 질의(platform_events)를 못 찾았다 — 조회기 의심(공허한 참 방지)"
    assert "status_code" in " ".join(pop), f"모집단 질의가 status_code 를 안 본다: {pop}"

    # ★음성 대조군 — baseline 질의에는 이 조건이 **없어야** 한다(있으면 잘못 새어 든 것)
    base = _strings("platform_insights")
    assert base, "baseline 질의를 못 찾았다 — 조회기 의심"
    assert "status_code" not in " ".join(base), "baseline 질의에 status_code 가 새어 들어갔다"
