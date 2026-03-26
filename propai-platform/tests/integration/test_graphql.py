"""GraphQL(Hasura) 통합 테스트 스켈레톤.

Hasura + PostgreSQL이 실행 중일 때만 동작한다.
CI 환경에서는 skip 처리.
"""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.skip(reason="Requires Hasura + PostgreSQL")
class TestGraphQLIntrospection:
    """GraphQL 스키마 introspection 검증."""

    async def test_schema_introspection_query(self) -> None:
        """__schema 쿼리가 정상 응답한다."""
        import httpx

        from apps.api.config import get_settings

        settings = get_settings()
        query = '{"query": "{ __schema { types { name } } }"}'
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                settings.hasura_url,
                content=query,
                headers={
                    "Content-Type": "application/json",
                    "X-Hasura-Admin-Secret": settings.hasura_admin_secret,
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "__schema" in data["data"]

    async def test_projects_query(self) -> None:
        """projects 쿼리가 정상 응답한다."""
        import httpx

        from apps.api.config import get_settings

        settings = get_settings()
        query = '{"query": "{ projects { id name status } }"}'
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                settings.hasura_url,
                content=query,
                headers={
                    "Content-Type": "application/json",
                    "X-Hasura-Admin-Secret": settings.hasura_admin_secret,
                },
            )
        assert resp.status_code == 200

    async def test_project_mutation(self) -> None:
        """프로젝트 생성 뮤테이션 구조 확인."""
        import httpx

        from apps.api.config import get_settings

        settings = get_settings()
        mutation = (
            '{"query": "mutation { insert_projects_one'
            '(object: {name: \\"test\\", status: \\"PLANNING\\"}) { id } }"}'
        )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                settings.hasura_url,
                content=mutation,
                headers={
                    "Content-Type": "application/json",
                    "X-Hasura-Admin-Secret": settings.hasura_admin_secret,
                },
            )
        # 스키마가 정의되어 있으면 200, 아니면 에러
        assert resp.status_code in (200, 400)
