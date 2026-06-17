"""설명가능성 표준 — 결과값에 '왜 이 값인지(도출식·입력·법령)'를 동반.

값만 흐르던 산출에 부착해 사람이 도출 과정을 재현·검증 가능하게 한다. 결정론(입력 동일→동일).

- LegalRef: 조문 식별자를 법령명·조항호·요지·시행일·1차출처로 해소(services/explain/legal_refs 사전).
- RationaleInput: 도출에 투입된 피연산자(이름·값·출처).
- Rationale: summary(한 줄 이유)·formula(도출식)·inputs(피연산자)·legal_basis(근거조문)·caveats(한계).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LegalRef(BaseModel):
    ref_id: str                          # 사전 키(예: "국토계획법시행령§85")
    law: str                             # 법령/조례/운영기준명
    article: str                         # 조/항/호 또는 절
    summary: str                         # 규정 요지(사람이 읽는 근거)
    effective_date: str | None = None    # 시행일(YYYY-MM-DD) — 신선도/시점 적용 추적
    source: str | None = None            # 1차출처 URL/문서


class RationaleInput(BaseModel):
    name: str                            # 피연산자명(예: 대지면적)
    value: str | float | int | bool | None = None
    source: str | None = None            # 입력 출처(API 필드/계층)


class Rationale(BaseModel):
    summary: str                                       # 왜 이 값인지 한 줄
    formula: str | None = None                         # 도출식(예: 연면적÷대지×100)
    inputs: list[RationaleInput] = Field(default_factory=list)
    legal_basis: list[LegalRef] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)   # 한계/주의(이론상 최대·시점 의존 등)
