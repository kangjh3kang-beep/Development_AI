"""시니어 정량 평가기 — decision_rule을 실제 입력 수치로 PASS/WARN/BLOCK 평가.

결정론·무DB·무목업: 필요한 입력이 없으면 해당 평가는 생략(가짜 수치 금지·정직 강등).
EVALUATORS[agent_key] = 평가함수(inputs: dict) -> list[RuleEvaluation]. orchestrator.consult가
context["inputs"]가 있으면 호출해 자문에 실측 판정을 첨부한다(없으면 프레임워크까지).
"""

from app.services.senior_agents.evaluators.architect import evaluate_architect
from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    worst_verdict,
)
from app.services.senior_agents.evaluators.financial import evaluate_financial
from app.services.senior_agents.evaluators.urban import evaluate_urban

# 에이전트 키 → 정량 평가함수. 후속 도메인(BIM·세무·회계·심의)은 여기 추가.
EVALUATORS = {
    "senior_financial_advisor": evaluate_financial,
    "senior_urban_planner": evaluate_urban,
    "senior_architect": evaluate_architect,
}

__all__ = [
    "EVALUATORS", "RuleEvaluation",
    "evaluate_financial", "evaluate_urban", "evaluate_architect",
    "worst_verdict", "PASS", "WARN", "BLOCK",
]
