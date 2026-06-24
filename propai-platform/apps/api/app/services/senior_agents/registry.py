"""시니어 에이전트 레지스트리 — spec 등록·조회. 후속 에이전트는 register()로 추가.

P0는 도시계획 PoC 1종. 설계·세무·금융·BIM·심의·회계는 후속(각 도메인 트랙·보드 claim).
★불변성: 내부 _REGISTRY는 register()로만 변경(판단자격 검사). 외부엔 읽기전용 view(MappingProxyType) 노출.
"""

from __future__ import annotations

from types import MappingProxyType

from app.services.senior_agents.spec import SeniorAgentSpec
from app.services.senior_agents.specs.urban_planner import URBAN_PLANNER_SPEC

_REGISTRY: dict[str, SeniorAgentSpec] = {}


def register(spec: SeniorAgentSpec, *, replace: bool = False) -> None:
    """spec 등록 — 키 중복(replace 아니면)·판단자격 미달 시 거부(무결성 게이트)."""
    if not isinstance(spec, SeniorAgentSpec):
        raise TypeError("SeniorAgentSpec 인스턴스만 등록 가능")
    if not spec.key:
        raise ValueError("spec.key 필수")
    if spec.key in _REGISTRY and not replace:
        raise ValueError(f"중복 키: {spec.key}(replace=True로 교체)")
    bad = [r.rule_id for r in spec.invalid_rules()]
    if bad:
        raise ValueError(f"판단자격 미달 decision_rule(분류기/근거없음): {bad}")
    _REGISTRY[spec.key] = spec


# 읽기전용 공개 view(외부 변조 차단).
SENIOR_AGENT_REGISTRY: MappingProxyType[str, SeniorAgentSpec] = MappingProxyType(_REGISTRY)


def get_senior_agent(key: str) -> SeniorAgentSpec | None:
    return _REGISTRY.get(key)


def list_senior_agents() -> list[SeniorAgentSpec]:
    return list(_REGISTRY.values())


def validate_registry() -> dict[str, list[str]]:
    """전 spec 무결성 — 판단자격 미달 decision_rule 키 목록(빈 dict=전부 통과)."""
    return {spec.key: bad for spec in _REGISTRY.values()
            if (bad := [r.rule_id for r in spec.invalid_rules()])}


# ── 기본 spec 등록(register 게이트 경유) ──
register(URBAN_PLANNER_SPEC)
