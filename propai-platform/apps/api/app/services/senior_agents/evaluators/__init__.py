"""시니어 정량 평가기 — decision_rule을 실제 입력 수치로 PASS/WARN/BLOCK 평가.

결정론·무DB·무목업: 필요한 입력이 없으면 해당 평가는 생략(가짜 수치 금지·정직 강등).
EVALUATORS[agent_key] = 평가함수(inputs: dict) -> list[RuleEvaluation]. orchestrator.consult가
context["inputs"]가 있으면 호출해 자문에 실측 판정을 첨부한다(없으면 프레임워크까지).
"""

from app.services.senior_agents.evaluators.accountant import evaluate_accounting
from app.services.senior_agents.evaluators.appraisal import evaluate_appraisal
from app.services.senior_agents.evaluators.architect import evaluate_architect
from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    worst_verdict,
)
from app.services.senior_agents.evaluators.bim import evaluate_bim
from app.services.senior_agents.evaluators.deliberation import evaluate_deliberation
from app.services.senior_agents.evaluators.financial import evaluate_financial
from app.services.senior_agents.evaluators.legal import evaluate_legal
from app.services.senior_agents.evaluators.qs import evaluate_qs
from app.services.senior_agents.evaluators.tax import evaluate_tax
from app.services.senior_agents.evaluators.urban import evaluate_urban

# 에이전트 키 → 정량 평가함수. 10개 도메인(법무사·감정평가사 통합 권리분석 + 적산(QS) 추가).
EVALUATORS = {
    "senior_financial_advisor": evaluate_financial,
    "senior_urban_planner": evaluate_urban,
    "senior_architect": evaluate_architect,
    "senior_tax_advisor": evaluate_tax,
    "senior_accountant": evaluate_accounting,
    "senior_bim_specialist": evaluate_bim,
    "senior_deliberation_member": evaluate_deliberation,
    "senior_legal_scrivener": evaluate_legal,
    "senior_appraiser": evaluate_appraisal,
    "senior_quantity_surveyor": evaluate_qs,
}

__all__ = [
    "EVALUATORS", "RuleEvaluation",
    "evaluate_financial", "evaluate_urban", "evaluate_architect",
    "evaluate_tax", "evaluate_accounting", "evaluate_bim", "evaluate_deliberation",
    "evaluate_legal", "evaluate_appraisal", "evaluate_qs",
    "worst_verdict", "PASS", "WARN", "BLOCK",
]
