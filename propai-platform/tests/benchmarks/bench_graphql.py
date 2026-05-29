"""CoVe O4: GraphQL REST 대비 요청 감소율 벤치마크.

기준: ≥ 80% 감소 (Gemini 주 담당, Claude Code 보조)
실행: pytest tests/benchmarks/bench_graphql.py -v
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.benchmark

_BASE = Path(__file__).resolve().parents[2]
_APOLLO_SOURCE = (_BASE / "apps" / "web" / "lib" / "apollo-client.ts").read_text(encoding="utf-8")
_PROVIDERS_SOURCE = (_BASE / "apps" / "web" / "lib" / "providers.tsx").read_text(encoding="utf-8")


class TestGraphQLEfficiency:
    """GraphQL 효율화 계약 검증.

    실트래픽 요청 감소율(>=80%)은 통합환경 부하테스트에서 측정하고,
    기본 CI에서는 GraphQL 런타임 스위치/프로바이더 배선을 항상 검증한다.
    """

    def test_graphql_runtime_config_is_wired(self) -> None:
        assert "NEXT_PUBLIC_GRAPHQL_URL" in _APOLLO_SOURCE
        assert "NEXT_PUBLIC_GRAPHQL_ENABLED" in _APOLLO_SOURCE
        assert "ApolloClient" in _APOLLO_SOURCE

    def test_apollo_provider_is_registered(self) -> None:
        assert "ApolloProvider" in _PROVIDERS_SOURCE
        assert "getApolloClient" in _PROVIDERS_SOURCE
