"""P1-5: analysis_ledger 동시 append 직렬화(advisory lock) + UNIQUE 백스톱 검증.

- _chain_lock_key: _chain_where 와 1:1 체인 식별 의미(순수·무DB).
- 실DB: 같은 체인 8개 동시 append → version 1..8 유일 + prev_hash 연속(포크 0).
- 마이그레이션 034 SQL 헤르메틱 검증: TEMP TABLE 섀도잉(실테이블 무접촉)으로
  중복 version 결정적 재번호 + UNIQUE 백스톱 인덱스 동작.
DB 미가용 시 skip(정직 — CI 무DB 환경 호환).
"""
from __future__ import annotations

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest

from app.services.ledger import analysis_ledger_service as ledger
from app.services.ledger.analysis_ledger_service import _chain_lock_key


class TestChainLockKey:
    """순수 락키 — 체인 식별 의미(_chain_where 미러) 검증."""

    def test_pnu_우선(self):
        assert _chain_lock_key("t1", "PNU1", "서울 주소", "p1", "site") == "t1|p:PNU1|p1|site"

    def test_주소_폴백(self):
        assert _chain_lock_key("t1", None, "서울 주소", None, "site") == "t1|a:서울 주소||site"

    def test_null_체인(self):
        assert _chain_lock_key(None, None, "", None, "site") == "|n:||site"

    def test_체인_분리(self):
        base = _chain_lock_key("t1", "P", "", None, "site")
        assert base != _chain_lock_key("t2", "P", "", None, "site")      # 테넌트 분리
        assert base != _chain_lock_key("t1", "P", "", "proj", "site")    # 프로젝트 분리
        assert base != _chain_lock_key("t1", "P", "", None, "design")    # 분석타입 분리


async def _db_up() -> bool:
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory, engine
        await engine.dispose()  # 교차-이벤트루프 풀 바인딩 초기화(테스트 격리)
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


async def _cleanup(tid: str) -> None:
    from sqlalchemy import text

    from app.core.database import async_session_factory
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id = :t"), {"t": tid})
        await db.commit()


async def test_concurrent_appends_no_duplicate_version():
    """레이스 재현 조건(같은 체인 동시 append)에서 advisory lock 이 버전을 직렬화한다."""
    if not await _db_up():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    tid = f"t-p1-5-{uuid.uuid4().hex[:8]}"
    pnu = f"41150{uuid.uuid4().hex[:9]}"
    try:
        results = await asyncio.gather(*[
            ledger.append_analysis(analysis_type="p1_5_race", payload={"i": i},
                                   tenant_id=tid, pnu=pnu, source="test")
            for i in range(8)
        ])
        assert all(r.get("ok") for r in results), results

        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            rows = (await db.execute(text(
                "SELECT version, content_hash, prev_hash FROM analysis_ledger "
                "WHERE tenant_id = :t ORDER BY version"), {"t": tid})).all()
        versions = [int(r[0]) for r in rows]
        assert versions == list(range(1, len(rows) + 1)), versions  # 중복/공백 없는 연속 버전
        for prev, cur in zip(rows, rows[1:], strict=False):
            assert cur[2] == prev[1]  # prev_hash 연속(해시체인 포크 0)
    finally:
        await _cleanup(tid)


def _load_migration_034():
    p = (Path(__file__).resolve().parents[2] / "database" / "migrations" / "versions"
         / "034_ledger_unique_version.py")
    spec = importlib.util.spec_from_file_location("mig_034_ledger_unique_version", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def test_migration_034_dedupe_and_unique_backstop_hermetic():
    """034 의 재번호 SQL·UNIQUE 인덱스를 TEMP TABLE 섀도잉으로 검증(실테이블 무접촉)."""
    if not await _db_up():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행")
    mod = _load_migration_034()
    from sqlalchemy import text

    from app.core.database import async_session_factory
    async with async_session_factory() as db:
        # 같은 세션에서 TEMP TABLE 이 public.analysis_ledger 를 섀도잉(search_path=pg_temp 우선).
        await db.execute(text(
            "CREATE TEMP TABLE analysis_ledger ("
            " id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
            " tenant_id text, pnu text, address_norm text, project_id text,"
            " analysis_type text NOT NULL, version int NOT NULL, payload jsonb NOT NULL,"
            " content_hash text NOT NULL, prev_hash text, source text, created_by text,"
            " created_at timestamptz DEFAULT now()) ON COMMIT DROP"))
        # 레이스로 생긴 중복 시나리오: 같은 체인에 version (1, 1, 2).
        for i, ver in enumerate((1, 1, 2)):
            await db.execute(text(
                "INSERT INTO analysis_ledger(tenant_id, pnu, analysis_type, version, payload, content_hash)"
                " VALUES ('t', 'P', 'x', :v, CAST(:p AS jsonb), :h)"),
                {"v": ver, "p": f'{{"i": {i}}}', "h": f"h{i}"})

        await db.execute(text(mod.DEDUPE_SQL))
        rows = (await db.execute(text(
            "SELECT version FROM analysis_ledger ORDER BY version"))).scalars().all()
        assert [int(v) for v in rows] == [1, 2, 3]  # (version, created_at, id) 순 결정적 재번호

        await db.execute(text(mod.UNIQUE_INDEX_SQL))  # 정리 후 UNIQUE 생성 성공
        with pytest.raises(Exception, match="(?i)unique|duplicate"):  # 중복 재삽입은 이제 차단
            await db.execute(text(
                "INSERT INTO analysis_ledger(tenant_id, pnu, analysis_type, version, payload, content_hash)"
                " VALUES ('t', 'P', 'x', 3, CAST('{}' AS jsonb), 'hdup')"))
        await db.rollback()  # TEMP TABLE·인덱스 폐기(ON COMMIT DROP + 미커밋)
