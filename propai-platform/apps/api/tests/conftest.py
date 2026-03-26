"""공유 테스트 픽스처.

모든 백엔드 테스트에서 공통으로 사용하는 픽스처를 정의한다.
- async DB 세션 (SQLite in-memory) — 통합 테스트용
- 경량 FastAPI TestClient — DB 없이 라우터 테스트용
- 인증된 사용자 컨텍스트
- 테넌트 격리 픽스처
"""

import contextlib
import os
import sys
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.auth.jwt_handler import CurrentUser, create_access_token
from apps.api.config import Settings
from apps.api.database.session import get_db

# ──────────────────────────────────────────────
# 고정 테스트 ID
# ──────────────────────────────────────────────

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
TEST_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000003")

# ──────────────────────────────────────────────
# 테스트 설정
# ──────────────────────────────────────────────


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """테스트 전용 설정."""
    return Settings(
        database_url="sqlite+aiosqlite://",
        timescale_url="sqlite+aiosqlite://",
        redis_url="redis://localhost:6379/15",
        debug=True,
        jwt_secret="test-secret-key-for-testing-only",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=60,
        anthropic_api_key="test-key",
        openai_api_key="test-key",
    )


# ──────────────────────────────────────────────
# 경량 FastAPI 클라이언트 (DB 없음, 라우터 테스트용)
# ──────────────────────────────────────────────
# PostgreSQL 전용 타입(JSONB, ARRAY, PostGIS)으로 인해
# SQLite 기반 스키마 생성이 불가하므로, 라우터 테스트에는
# DB 세션을 Mock으로 대체하는 경량 클라이언트를 사용한다.


@pytest_asyncio.fixture
async def lite_app(test_settings: Settings) -> FastAPI:
    """DB 없이 라우터만 로드하는 경량 FastAPI 앱."""
    # python-multipart 설치 보장
    with contextlib.suppress(ImportError):
        import multipart  # noqa: F401

    from apps.api.main import app as _app

    # DB 세션을 AsyncMock으로 오버라이드
    async def override_get_db():
        mock = AsyncMock()
        mock.execute = AsyncMock()
        mock.commit = AsyncMock()
        yield mock

    _app.dependency_overrides[get_db] = override_get_db

    yield _app

    _app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(lite_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """인증 없는 HTTP 테스트 클라이언트 (경량)."""
    async with AsyncClient(
        transport=ASGITransport(app=lite_app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client(
    lite_app: FastAPI,
) -> AsyncGenerator[AsyncClient, None]:
    """인증된 HTTP 테스트 클라이언트 (admin 역할).

    앱의 실제 JWT 시크릿으로 토큰을 생성하여 인증을 통과한다.
    """
    from apps.api.config import get_settings

    app_settings = get_settings()
    token = create_access_token(
        user_id=TEST_USER_ID,
        tenant_id=TEST_TENANT_ID,
        role="admin",
        settings=app_settings,
    )
    async with AsyncClient(
        transport=ASGITransport(app=lite_app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac


# ──────────────────────────────────────────────
# 인증 컨텍스트 픽스처
# ──────────────────────────────────────────────

@pytest.fixture
def current_user() -> CurrentUser:
    """테스트용 인증 사용자 컨텍스트."""
    return CurrentUser(
        user_id=TEST_USER_ID,
        tenant_id=TEST_TENANT_ID,
        role="admin",
    )


@pytest.fixture
def viewer_user() -> CurrentUser:
    """읽기 전용 뷰어 사용자."""
    return CurrentUser(
        user_id=uuid4(),
        tenant_id=TEST_TENANT_ID,
        role="viewer",
    )


# ──────────────────────────────────────────────
# Mock 헬퍼
# ──────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    """완전한 Mock DB 세션. 서비스 단위 테스트용."""
    mock = AsyncMock()
    mock.execute = AsyncMock()
    mock.commit = AsyncMock()
    mock.rollback = AsyncMock()
    mock.flush = AsyncMock()
    mock.add = lambda x: None
    return mock
