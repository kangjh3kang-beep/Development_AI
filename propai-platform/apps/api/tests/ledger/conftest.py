"""원장 통합테스트 공용 픽스처.

원장 서비스 함수는 인자로 세션을 받지 않고 내부에서 ``async_session_factory()``를
열기 때문에, 동일 ``settings.DATABASE_URL``을 가리키는 세션을 직접 열어 시드/정리한다.
DB 미가용(인프라 미기동) 시 모듈 전체 skip(정직 — 거짓 통과 금지).
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from sqlalchemy import text

# apps/api 를 import 경로에 추가(기존 tests/conftest.py와 동일 규약).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
async def ledger_db():
    """실 Postgres 세션(없으면 skip). 시드·검증·정리 전용(원장 함수와는 별도 세션)."""
    from app.core.database import async_session_factory

    try:
        async with async_session_factory() as probe:
            await probe.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 미가용 — 원장 통합테스트 skip: {str(e)[:80]}")

    async with async_session_factory() as db:
        yield db


@pytest.fixture
async def tnt(ledger_db):
    """테스트 격리용 유니크 tenant_id. 종료 시 해당 테넌트 원장행 정리."""
    t = f"test-{uuid.uuid4().hex[:12]}"
    yield t
    await ledger_db.execute(
        text("DELETE FROM analysis_ledger WHERE tenant_id = :t"), {"t": t}
    )
    await ledger_db.commit()
