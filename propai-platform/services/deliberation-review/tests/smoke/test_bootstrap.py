"""Phase 0 수용 검증(AT-1..8). Docker 미가용 → AT-1은 앱 헬스체크로 적응(시스템 DB 사용)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ALEMBIC_DIR = REPO / "apps" / "api" / "alembic"


# AT-1 헬스체크 200 (compose 대신 앱 헬스 — Docker 미가용 적응)
def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


# AT-2 async db 세션 + PostGIS 활성
async def test_db_session_and_postgis(db):
    from sqlalchemy import text

    res = await db.execute(text("SELECT postgis_version()"))
    assert res.scalar()


# AT-3 공통 믹스인: UUID PK + org/proj + ts 컬럼 존재
def test_base_mixin_columns():
    from app.models import ProbeModel

    cols = set(ProbeModel.__table__.columns.keys())
    assert {"id", "organization_id", "project_id", "created_at", "updated_at"} <= cols


# AT-4 Alembic up/down 무결
def test_migrations_up_down():
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")  # 재상승: 이후 dev/test가 테이블을 가짐


# AT-5 input_hash 재현성(동일 입력, 키 순서 무관 동일 해시)
def test_input_hash_stable():
    from app.core.hashing import input_hash

    assert input_hash({"a": 1, "b": 2}) == input_hash({"b": 2, "a": 1})


# AT-6 static_scan: 하드코딩 수치 탐지 동작
SAMPLE_WITH_HARDCODE = "def f():\n    far_limit=300\n    return far_limit\n"
SAMPLE_CLEAN = "def f(far_limit):\n    return far_limit\n"


def test_static_scan_detects_literal():
    from tools.static_scan import static_scan

    assert "far_limit=300" in static_scan(SAMPLE_WITH_HARDCODE)
    assert static_scan(SAMPLE_CLEAN) == []


# AT-7 celery 앱 로딩 + redis 브로커
def test_celery_app_loads():
    from app.tasks.celery_app import celery_app

    assert celery_app.conf.broker_url.startswith("redis")


# AT-8 fixtures 로더 동작(페이즈별 하위 디렉터리 탐색)
def test_fixture_loader():
    from tests.fixtures.loader import load_fixture

    assert load_fixture("preflight", "pnu_multizone") is not None
