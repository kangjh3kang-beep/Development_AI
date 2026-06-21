"""인·허가/심의 프로세스 스펙 계약(선언 데이터 = "스킬" 본체).

버전드 단계 그래프. 법정 한도는 보유하지 않고 ssot_ref로 규제 SSOT를 참조(INV-3). 단계 추가·법 개정 =
스펙/SSOT 버전 갱신(코드 무변경). applicability로 사업유형·용도지역별 단계 on/off(데이터 구동).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CriterionKind(str, Enum):
    QUANTITATIVE = "QUANTITATIVE"   # reg SSOT 한도 대비 정량 부합도
    QUALITATIVE = "QUALITATIVE"     # L3-C 등급 매핑


class CriterionRef(BaseModel):
    """단계 심의 기준 1건 — 한도는 ssot_ref로 SSOT 참조(직접 수치 보유 금지)."""

    criterion_id: str
    kind: CriterionKind
    ssot_ref: str | None = None        # QUANTITATIVE: 산정변수 id(target_variable). QUALITATIVE: rubric id
    measure: str = "limit_ratio"        # 부합도 산식 식별자(측정 방식 — 법정 수치 아님)
    basis_article: str | None = None


class StageSpec(BaseModel):
    """인허가/심의 단계 1건."""

    stage_id: str
    name: str
    stage_type: str                     # "본허가" | "의제심의"
    predecessors: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    criteria_refs: list[CriterionRef] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    authority: str | None = None        # 관계기관
    submittals: list[str] = Field(default_factory=list)
    # applicability: dev_type/use_zone 조건(없으면 항상 적용). 데이터 구동 on/off.
    applies_dev_types: list[str] = Field(default_factory=list)   # 비면 모든 사업유형
    applies_zones: list[str] = Field(default_factory=list)        # 비면 모든 용도지역
    outcome_predictor: str | None = None  # Phase 2 슬롯(Phase 1 = None)


class PermitProcessSpec(BaseModel):
    """버전드 프로세스 스펙 — 재현(snapshot 결속)·확장(스펙 추가)."""

    spec_id: str
    version: str
    effective_date: str                 # ISO date(축 결속·재현)
    stages: list[StageSpec] = Field(default_factory=list)
