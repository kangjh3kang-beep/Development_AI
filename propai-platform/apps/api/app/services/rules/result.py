"""RuleResult — 규칙 평가 1건의 결과 + 감사가능 trace.

status는 새 어휘를 만들지 않고 기존 Fact 신뢰상태 계약(W2-1, app.services.provenance.
fact_status.FactStatus)을 그대로 재사용한다(정합점 — UNKNOWN/CONFLICT 보존 어휘 통일):
- DERIVED : 산식/비교가 정상 평가됨(결정론적 규칙 산출).
- UNKNOWN : 입력 결손·미시행 규칙 등으로 평가 불가(0/기본값 대체 금지 — 그대로 전파).
- CONFLICT: 같은 target_variable에 서로 다른 규칙이 상충하는 값을 낸 경우(evaluate_many).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.provenance.fact_status import FactStatus
from app.services.rules.contracts import Unit


class RuleTraceEntry(BaseModel):
    """평가 1단계 — 심의엔진 CalcTraceEntry(rule_id·basis_article·note) 필드명 계승."""

    rule_id: str
    basis_article: str = ""
    note: str


class RuleTrace(BaseModel):
    entries: list[RuleTraceEntry] = Field(default_factory=list)


class RuleResult(BaseModel):
    """규칙 평가 결과 1건 — 값 + 감사가능 trace(INV-10 계승: 모든 출력은 trace 동반)."""

    rule_id: str
    target_variable: str
    value: float | None
    unit: Unit
    status: FactStatus
    compliant: bool | None = None  # limit/comparator 없거나 미확정이면 None(정직 — 임의 판정 금지)
    basis_article: str
    trace: RuleTrace


__all__ = ["RuleResult", "RuleTrace", "RuleTraceEntry"]
