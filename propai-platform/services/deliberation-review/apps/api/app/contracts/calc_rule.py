"""R1.5 — 산정규칙 계약. CalcRule(파라미터화) + CalcRuleSet(versioned, 기준일 선택).

제외규정 임계수치는 params로 주입(하드코딩 금지, INV-11). effective_date로 유효 버전 선택.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.core.errors import RuleContractError


class CalcRule(BaseModel):
    """시행령 제119조 산정방법 1건의 규칙화."""

    rule_id: str
    target_variable: str
    exclusion_logic_ref: str
    params: dict[str, float] = Field(default_factory=dict)
    basis_article: str
    effective_date: date


class VersionedRules(BaseModel):
    """한 버전의 산정규칙 파라미터 묶음(기준일 결속)."""

    version: str
    effective_date: date
    params: dict[str, float] = Field(default_factory=dict)


class CalcRuleSet(BaseModel):
    """버전별 산정규칙 집합. 기준일에 유효한 최신 버전 선택."""

    versions: list[VersionedRules] = Field(default_factory=list)

    def effective_on(self, base_date: date) -> VersionedRules:
        applicable = [v for v in self.versions if v.effective_date <= base_date]
        if not applicable:
            raise RuleContractError(f"no calc rule version effective on {base_date}")
        return max(applicable, key=lambda v: v.effective_date)
