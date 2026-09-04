"""2층 관측 표면의 **SQL 을 실 Postgres 로 태우는** 락 (2026-08-27).

## 왜 실 DB 인가 (이 파일의 존재 이유)

독립 리뷰(H1)가 실측으로 보였다: `test_realtx_layer2_status.py` 의 `_FakeDb` 는 SQL
**문자열의 특징 조각**으로 답을 고르므로, **조각만 남으면 의미를 무엇으로 바꾸든 같은
값을 돌려준다.** 유의미 변이 16개 중 **12개가 생존**했다:

    updated_at >  first_seen_at  →  >=        SURVIVED   재관측 정의 붕괴
    split_part(scope_key,'|',2)  →  ,1)       SURVIVED   시군구가 아니라 유형을 셈
    split_part(...,3) = ANY      →  ,1) =     SURVIVED   신선도가 월이 아니라 유형으로 필터
    max(last_scanned_at)         →  min(...)  SURVIVED
    = ANY(:months)               →  <> ALL    SURVIVED   조건 반전
    interval '1 second'          →  '1 year'  SURVIVED
    GROUP BY kind                →  BY field  SURVIVED
    to_regclass(...)             →  없는 테이블 SURVIVED  항상 「미배포」

★그리고 `split_part` 는 **이 저장소 최초 사용**이라(선례 0건) 특히 미검증이었다.

## 게이트 정책 (형제 `test_selection_contamination_sql_pg.py` 와 동일)

`TEST_PG_DSN` 이 **설정돼 있는데 못 붙으면 fail**(누군가 DB 를 주기로 해 놓고 안 준 것),
설정이 없으면 skip(로컬 편의). `CI` 환경변수에 기대지 않는다 — 그건 확인하지 않은
전제이고, 틀리면 이 락이 **조용히 사라진다**.

## ★이 파일이 **못 보는** 것

프로덕션 `search_path` 값은 재지 않았다(**미측정**). `to_regclass` 를 무자격으로 바꾼
것(리뷰 M2)이 옳다는 근거는 *"DDL 도 무자격이라 같은 규칙을 따른다"* 는 **추론**이다.
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

from app.services.land_intelligence import realtx_layer2_status as S
from app.services.land_intelligence import realtx_store as store
from app.tasks import realtx_sync_task as T

_EXPLICIT_DSN = os.environ.get("TEST_PG_DSN")
_DSN = _EXPLICIT_DSN or "postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db"

pytestmark = pytest.mark.asyncio

_NOW = datetime(2026, 8, 27, 3, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def db():
    """★**테스트마다 전용 스키마**를 만들고 `search_path` 를 거기로 돌린다.

    ## 왜 스키마 격리인가 (2026-08-27 · CI 실패에서 배웠다)

    `build_layer2_status` 는 **전역 집계**(`SELECT count(*) FROM realtx_corrections`)를 읽는다.
    CI 는 `pytest -n auto` 로 **병렬** 실행하므로, 옆 워커가 넣은 정정 행이 내 집계에 섞여
    판정이 `미시험` → **`모순`** 으로 뒤집혔다(실측 재현).
    → 행 단위 태그(`lawd_cd LIKE 'T%'`)로는 **전역 집계를 격리할 수 없다.**
      **창·키가 아니라 스키마 자체**를 갈라야 한다.

    ## ★부수 소득 — 이것이 `to_regclass` 무자격 선택을 **검증**한다

    서비스는 `to_regclass(t)` 를 **무자격**으로 묻는다(리뷰 M2 — DDL 도 무자격이라
    `search_path` 를 따른다). 그 판단은 종전 **추론**이었는데, 이 픽스처가
    `search_path` 를 `public` 이 **아닌** 곳으로 돌리므로 **관측이 된다** —
    `public.` 을 못 박은 구현이면 여기서 `미배포` 가 나와 죽는다.
    """
    schema = "rtx_t_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(_DSN, future=True, poolclass=None)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    except Exception as e:  # noqa: BLE001
        await admin.dispose()
        if _EXPLICIT_DSN:
            pytest.fail(f"TEST_PG_DSN 이 설정됐는데 실 Postgres 준비 실패 — 무잠금이다: {e}")
        pytest.skip(f"로컬에 Postgres 없음(스킵): {e}")

    # ★`search_path` 를 커넥션 설정으로 준다(세션 `SET` 은 풀러에서 남의 커넥션으로 샌다).
    engine = create_async_engine(
        _DSN, future=True,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with engine.begin() as conn:
        # ★DDL 을 손으로 쓰지 않는다 — **생산자의 DDL 상수**를 그대로 태운다.
        for ddl in (store._TRADES_DDL, store._CORRECTIONS_DDL, store._SCAN_STATE_DDL):
            await conn.execute(text(ddl))
        # ★이 픽스처가 실제로 public 밖에 있는지 단언(공허 방지)
        row = (await conn.execute(text("SELECT current_schema()"))).first()
        assert row and row[0] == schema, f"search_path 가 안 먹었다: {row}"

    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s:
        try:
            yield s
        finally:
            with contextlib.suppress(Exception):
                await s.rollback()
    await engine.dispose()
    # ★정리는 **teardown 에서 무조건** — 스키마째 지우므로 잔재가 원리적으로 없다
    with contextlib.suppress(Exception):
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()


def _tag() -> str:
    """읽기 좋으라고 붙이는 접두 — **격리는 스키마가 한다**(위 픽스처 참조)."""
    return "T" + uuid.uuid4().hex[:4]


async def _seed_trade(db, *, lawd, ym, prop="apt", reobserved=False):
    key = f"k-{uuid.uuid4().hex[:12]}"
    await db.execute(text(store._UPSERT_SQL), store.upsert_params(
        {"prop_type": prop, "dong": "d", "jibun": "1", "area_m2": 1.0, "floor": 1,
         "price_10k_won": 1, "deal_date": "2026년 6월 1일", "building_name": "b",
         "cancel_type": "", "cancel_date": "", "registered_date": "",
         "dealing_type": "중개거래", "buyer_type": "", "seller_type": "",
         "share_dealing_type": ""},
        key, lawd, ym, prop))
    if reobserved:
        # ★두 번째 upsert = 재관측. `updated_at` 이 **1초 넘게** 뒤여야 한다.
        await db.execute(text(
            "UPDATE realtx_trades SET first_seen_at = now() - interval '10 seconds' "
            "WHERE trade_key = :k"), {"k": key})
    return key


async def _seed_scan(db, *, lawd, ym, prop="apt", when=None, baseline=True):
    await db.execute(text(
        "INSERT INTO realtx_scan_state (scope_key, baseline_done, last_scanned_at) "
        "VALUES (:k, :b, :t) ON CONFLICT (scope_key) DO UPDATE "
        "SET baseline_done = EXCLUDED.baseline_done, last_scanned_at = EXCLUDED.last_scanned_at"),
        {"k": store.scope_key(prop, lawd, ym), "b": baseline, "t": when or _NOW})


async def test_split_part_indices_match_the_producers_scope_key(db):
    """★`split_part` 인덱스가 `scope_key()` 의 **실제 자리**와 맞는가.

    이 저장소 **최초 사용**이라 선례가 없다. 인덱스를 손으로 `2`·`3` 이라 적었으니
    생산자 출력으로 **왕복 검증**한다 — `,1)` 로 바뀌면 여기서 죽는다.
    """
    lawd, ym = _tag(), "202606"
    key = store.scope_key("apt", lawd, ym)
    row = (await db.execute(text(
        "SELECT split_part(:k, '|', 1), split_part(:k, '|', 2), split_part(:k, '|', 3)"),
        {"k": key})).first()
    assert row == ("apt", lawd, ym), (key, row)

    # ★서비스 SQL 이 **그 인덱스를 쓰는지** — 상수에서 파생해 대조한다
    assert "split_part(scope_key, '|', 2)" in S._SQL_SIGUNGU_EVER
    assert "split_part(scope_key, '|', 3)" in S._SQL_LAST_SCAN_IN


async def test_reobserved_counts_only_rows_touched_again(db):
    """★`updated_at > first_seen_at` — `>=` 로 바꾸면 **전 행이 재관측**이 된다."""
    lawd = _tag()
    await _seed_trade(db, lawd=lawd, ym="202606", reobserved=False)
    await _seed_trade(db, lawd=lawd, ym="202606", reobserved=False)
    await _seed_trade(db, lawd=lawd, ym="202607", reobserved=True)
    await db.commit()

    scoped = S._SQL_REOBSERVED + " AND lawd_cd = :l"
    n = (await db.execute(text(scoped), {"l": lawd})).scalar()
    total = (await db.execute(text(S._SQL_STORED + " WHERE lawd_cd = :l"), {"l": lawd})).scalar()
    # ★두 모집단이 갈린다 — 갈리지 않으면 `>=` 변이가 통과한다
    assert (total, n) == (3, 1), (total, n)


async def test_last_scan_filter_selects_by_month_not_by_type(db):
    """★`= ANY(:months)` 가 **월**로 거르는가 — `,1)` 이나 `<> ALL` 이면 죽는다."""
    lawd = _tag()
    await _seed_scan(db, lawd=lawd, ym="202608", when=_NOW - timedelta(hours=1))
    await _seed_scan(db, lawd=lawd, ym="202602", when=_NOW - timedelta(days=30))
    await db.commit()

    scoped = S._SQL_LAST_SCAN_IN + " AND scope_key LIKE :p"
    recent = (await db.execute(text(scoped), {"months": ["202608"], "p": f"%|{lawd}|%"})).first()
    tail = (await db.execute(text(scoped), {"months": ["202602"], "p": f"%|{lawd}|%"})).first()

    assert recent[2] == 1 and tail[2] == 1, (recent, tail)
    # ★두 모집단이 갈린다 — 필터가 월을 안 보면 둘이 같아진다
    assert recent[0] != tail[0]
    assert recent[0] > tail[0]


async def test_min_not_max_decides_staleness(db):
    """★★리뷰 H2 — 스코프 하나가 신선해도 **최고령**으로 판정해야 한다."""
    lawd = _tag()
    await _seed_scan(db, lawd=lawd, ym="202608", prop="apt", when=_NOW - timedelta(hours=1))
    await _seed_scan(db, lawd=lawd, ym="202608", prop="land", when=_NOW - timedelta(days=30))
    await db.commit()

    scoped = S._SQL_LAST_SCAN_IN + " AND scope_key LIKE :p"
    row = (await db.execute(text(scoped), {"months": ["202608"], "p": f"%|{lawd}|%"})).first()
    newest, oldest, n = row
    assert n == 2
    # ★`min` 이 실제로 최고령을 준다 — `min`→`max` 변이가 여기서 죽는다
    assert oldest < newest
    assert S.freshness(oldest, _NOW, S.STALE_RECENT_DAYS)["stale"] is True
    assert S.freshness(newest, _NOW, S.STALE_RECENT_DAYS)["stale"] is False


async def test_schema_probe_follows_search_path(db):
    """★★`to_regclass` 를 **무자격**으로 묻는가(리뷰 M2) — 3종 전부 본다.

    ★이 픽스처의 `search_path` 는 `public` 이 **아니다**. 그러므로 이 테스트가 통과한다는
      것은 *"무자격 프로브가 `search_path` 를 따른다"* 가 **관측**이라는 뜻이다 —
      `public.` 을 못 박은 종전 구현이면 여기서 `0` 이 나와 죽는다.
    """
    cur = (await db.execute(text("SELECT current_schema()"))).scalar()
    assert cur != "public", f"이 락이 공허하다 — search_path 가 public 이다: {cur}"
    n = (await db.execute(text(S._SQL_SCHEMA_PRESENT),
                          {"tables": list(S._LAYER2_TABLES)})).scalar()
    assert n == len(S._LAYER2_TABLES), n
    # ★음성 대조군 — 없는 테이블은 세지 않는다(항상-참 방지)
    missing = (await db.execute(text(S._SQL_SCHEMA_PRESENT),
                                {"tables": ["zzz_not_a_table"]})).scalar()
    assert missing == 0


async def test_corrections_group_by_kind_not_field(db):
    """★`GROUP BY kind` — `field` 로 바뀌면 축이 달라진다."""
    lawd = _tag()
    for kind, field in (("cancelled", "cancel_type"), ("cancelled", "cancel_type"),
                        ("registry_added", "registered_date")):
        await db.execute(text(
            "INSERT INTO realtx_corrections (trade_key, lawd_cd, deal_ym, kind, field, "
            "old_value, new_value, twin_group_size) VALUES (:t,:l,:y,:k,:f,'','',1)"),
            {"t": uuid.uuid4().hex, "l": lawd, "y": "202606", "k": kind, "f": field})
    await db.commit()

    scoped = S._SQL_CORRECTIONS_BY_KIND.replace(
        "FROM realtx_corrections", "FROM realtx_corrections WHERE lawd_cd = :l")
    rows = dict((await db.execute(text(scoped), {"l": lawd})).fetchall())
    assert rows == {"cancelled": 2, "registry_added": 1}, rows


async def test_end_to_end_verdict_on_real_postgres(db):
    """★★전 구간 — 실 DB 위에서 `build_layer2_status` 가 **미시험**을 내는가.

    라이브 프로덕션 스냅샷(2026-08-27T00:0xZ · 저장 4,898 · 재관측 0 · 정정 0)과
    같은 모양을 만들어 태운다.
    """
    lawd = _tag()
    for ym in T.recent_months(_NOW, T.RECENT_MONTHS):
        await _seed_trade(db, lawd=lawd, ym=ym, reobserved=False)
        await _seed_scan(db, lawd=lawd, ym=ym, when=_NOW - timedelta(hours=2))
    await db.commit()

    out = await S.build_layer2_status(db, now=_NOW)
    # ★스키마가 격리돼 있으므로 **정확히** 단언할 수 있다. 종전엔 병렬 워커의 행이 섞여
    #   `("미시험","상태소실")` 로 느슨하게 열어 뒀는데, 그 느슨함이 곧 무잠금이었다.
    assert out["detection"]["state"] == "미시험", out["detection"]
    assert out["stored_rows"] == T.RECENT_MONTHS          # 내가 심은 것만 보인다
    assert out["reobserved_rows"] == 0
    assert out["corrections"]["total"] == 0
    assert out["collection"]["recent"]["stale"] is False  # 2시간 전 = 신선

    # ★두 모집단 — 재관측을 만들면 **같은 실행에서** 판정이 갈린다
    await _seed_trade(db, lawd=lawd, ym=T.recent_months(_NOW, T.RECENT_MONTHS)[0], reobserved=True)
    await db.commit()
    after = await S.build_layer2_status(db, now=_NOW)
    assert after["reobserved_rows"] == 1
    assert after["detection"]["state"] == "관측됨_정정없음", after["detection"]
