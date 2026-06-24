"""시니어 전문가 에이전트 — 코어 구조체·레지스트리(P0 foundation).

설계: senior_agents_spec_v3(수렴 ACCEPT). 기존 persona/interpreter/expert_panel/deliberation을
agentic 상위 계층으로 결합한다. 본 P0는 **공유 서비스 미접촉 신규 디렉토리**(additive)로,
코어 구조체(DecisionRule·SeniorAgentSpec)·confidence 캘리브레이션·registry + 도시계획 PoC spec만 둔다.
실 서비스 배선(legal KG·feasibility·persona registry·expert_panel)·LLM runner는 후속(보드 조율 필요).

★시니어의 정직한 경계: 인코딩 O(결정규칙·트레이드오프·실패모드·골든사례) / 위임(암묵지·협상) →
LLM 일반능력 + 면허전문가 인간게이트(대체 불가). 무목업·근거(verified)·면허책임 게이트.
"""

from app.services.senior_agents.confidence import (
    Interval,
    compute_confidence,
    confidence_label,
    make_interval,
    needs_expert_review,
)
from app.services.senior_agents.orchestrator import (
    DOMAIN_ROUTES,
    HIGH_RISK_AGENT_KEYS,
    SeniorConsultation,
    SeniorOrchestrator,
    senior_orchestrator,
)
from app.services.senior_agents.registry import (
    get_senior_agent,
    list_senior_agents,
    register,
    validate_registry,
)
from app.services.senior_agents.spec import (
    DecisionRule,
    Maturity,
    ReasoningStep,
    SeniorAgentSpec,
)

__all__ = [
    "DecisionRule", "Maturity", "ReasoningStep", "SeniorAgentSpec",
    "Interval", "compute_confidence", "confidence_label", "make_interval", "needs_expert_review",
    "get_senior_agent", "list_senior_agents", "register", "validate_registry",
    "SeniorOrchestrator", "SeniorConsultation", "senior_orchestrator",
    "DOMAIN_ROUTES", "HIGH_RISK_AGENT_KEYS",
]
