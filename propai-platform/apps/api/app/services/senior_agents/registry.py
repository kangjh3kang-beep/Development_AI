"""시니어 에이전트 레지스트리 — spec 등록·조회. 후속 에이전트는 SPECS에 추가만 하면 된다.

P0는 도시계획 PoC 1종. 설계·세무·금융·BIM·심의·회계는 후속(각 도메인 트랙·보드 claim).
"""

from __future__ import annotations

from app.services.senior_agents.spec import SeniorAgentSpec
from app.services.senior_agents.specs.urban_planner import URBAN_PLANNER_SPEC

SENIOR_AGENT_REGISTRY: dict[str, SeniorAgentSpec] = {
    URBAN_PLANNER_SPEC.key: URBAN_PLANNER_SPEC,
}


def get_senior_agent(key: str) -> SeniorAgentSpec | None:
    return SENIOR_AGENT_REGISTRY.get(key)


def list_senior_agents() -> list[SeniorAgentSpec]:
    return list(SENIOR_AGENT_REGISTRY.values())


def validate_registry() -> dict[str, list[str]]:
    """전 spec 무결성 — 판단자격 미달 decision_rule(분류기/근거없음) 키 목록 반환.

    빈 dict = 전부 통과(모든 rule이 condition·judgment·basis·tradeoff 보유).
    """
    issues: dict[str, list[str]] = {}
    for spec in SENIOR_AGENT_REGISTRY.values():
        bad = [r.rule_id for r in spec.invalid_rules()]
        if bad:
            issues[spec.key] = bad
    return issues
