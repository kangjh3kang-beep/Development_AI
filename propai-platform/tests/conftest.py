"""PropAI 테스트 공통 설정.

마커 등록, 공유 fixture, 비동기 백엔드 설정.
"""

import os

import pytest


# ──────────────────────────────────────
# pytest 마커 등록
# ──────────────────────────────────────
def pytest_configure(config: pytest.Config) -> None:
    """커스텀 마커를 등록한다."""
    config.addinivalue_line("markers", "unit: 단위 테스트 (외부 의존성 없음)")
    config.addinivalue_line("markers", "integration: 통합 테스트 (DB/서비스 스택 필요)")
    config.addinivalue_line("markers", "benchmark: 성능 벤치마크")
    config.addinivalue_line("markers", "load: 부하 테스트 (Locust)")


# ──────────────────────────────────────
# 환경변수 기반 자동 스킵
# ──────────────────────────────────────
def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """integration/load 마커가 붙은 테스트를 환경변수 없으면 스킵한다."""
    skip_integration = pytest.mark.skip(reason="PROPAI_INTEGRATION_TEST 환경변수 필요")
    skip_load = pytest.mark.skip(reason="PROPAI_LOAD_TEST 환경변수 필요")

    for item in items:
        if "integration" in item.keywords and not os.environ.get("PROPAI_INTEGRATION_TEST"):
            item.add_marker(skip_integration)
        if "load" in item.keywords and not os.environ.get("PROPAI_LOAD_TEST"):
            item.add_marker(skip_load)


# ──────────────────────────────────────
# 공유 fixture
# ──────────────────────────────────────
@pytest.fixture()
def sample_tenant_id() -> str:
    """테스트용 테넌트 UUID."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture()
def sample_project_id() -> str:
    """테스트용 프로젝트 UUID."""
    return "00000000-0000-0000-0000-000000000010"


@pytest.fixture()
def anyio_backend() -> str:
    """비동기 테스트 백엔드."""
    return "asyncio"
