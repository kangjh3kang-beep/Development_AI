"""CoVe O4: GraphQL REST 대비 요청 감소율 벤치마크.

기준: ≥ 80% 감소 (Gemini 주 담당, Claude Code 보조)
실행: pytest tests/benchmarks/bench_graphql.py -v
"""

import pytest

pytestmark = pytest.mark.benchmark


class TestGraphQLEfficiency:
    """GraphQL 요청 감소율 검증."""

    @pytest.mark.skip(reason="Hasura + 전체 스택 필요 — Gemini 주도")
    def test_request_reduction_rate(self) -> None:
        """동일 데이터 취합 시 REST 대비 GraphQL 요청 수 80% 이상 감소."""
        pass
