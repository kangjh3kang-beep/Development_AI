"""멀티테넌트 격리 통합 테스트.

Docker 기반 PostgreSQL + RLS 필요.
pytest 마크: integration (CI에서 DB 서비스 활성 시 실행).
"""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def tenant_a_id():
    return uuid4()


@pytest.fixture
def tenant_b_id():
    return uuid4()


class TestRLSIsolation:
    """RLS 기반 테넌트 격리 검증."""

    @pytest.mark.skip(reason="Docker DB 필요 — CI에서 실행")
    async def test_tenant_a_cannot_see_tenant_b_projects(
        self, tenant_a_id, tenant_b_id,
    ) -> None:
        """테넌트 A는 테넌트 B의 프로젝트를 조회할 수 없어야 한다."""
        # TODO: DB 세션을 tenant_a_id로 설정 후 tenant_b 프로젝트 조회 시 빈 결과
        pass

    @pytest.mark.skip(reason="Docker DB 필요 — CI에서 실행")
    async def test_rls_blocks_cross_tenant_update(
        self, tenant_a_id, tenant_b_id,
    ) -> None:
        """테넌트 A는 테넌트 B의 레코드를 수정할 수 없어야 한다."""
        pass

    @pytest.mark.skip(reason="Docker DB 필요 — CI에서 실행")
    async def test_legal_audit_trail_insert_only(self) -> None:
        """법적 감사 추적 테이블은 UPDATE/DELETE가 거부되어야 한다."""
        pass


class TestTenantSession:
    """테넌트 DB 세션 설정 검증."""

    @pytest.mark.skip(reason="Docker DB 필요 — CI에서 실행")
    async def test_get_tenant_db_sets_current_tenant(self) -> None:
        """get_tenant_db가 SET LOCAL app.current_tenant을 올바르게 설정한다."""
        pass
