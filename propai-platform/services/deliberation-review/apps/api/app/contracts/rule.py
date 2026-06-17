"""R3 — 룰/완화 계약. Rule(depends_on 의존, relaxations 완화전제). 완화는 DAG 엣지로 결속.

완화 전제(예: 공개공지 제공 → 용적률 완화)를 prerequisite_rule_id로 참조.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Relaxation(BaseModel):
    """완화/특례 1건. 전제 룰 결과를 참조하여 적용 여부 결정."""

    relaxation_id: str
    prerequisite_rule_id: str | None = None
    effect: str | None = None  # 예: far_relax, height_relax
    basis_article: str | None = None


class Rule(BaseModel):
    """판정 룰 1건. depends_on(평가 선행) + relaxations(완화 전제)."""

    rule_id: str
    target_variable: str | None = None
    comparator: str = "<="  # measured (comparator) limit → COMPLIANT
    depends_on: list[str] = Field(default_factory=list)
    relaxations: list[Relaxation] = Field(default_factory=list)
    basis_article: str | None = None
