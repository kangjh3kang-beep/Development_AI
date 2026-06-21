"""인·허가/심의 프로세스 산출 계약 — 로드맵 + 단계별 심의 계측 + 대응 + 검증.

모든 정량 계측은 calc_trace(measured/limit/basis/source — 설명가능성)·legal_refs 동반. 값은 JSON 직렬화 위해 float.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CriterionResult(BaseModel):
    criterion_id: str
    kind: str
    measured: float | None = None
    limit: float | None = None
    conformance: str = "HELD"          # 부합 | 조건부 | 미흡 | HELD(미상)
    margin: float | None = None         # 계산식(리터럴 아님): (limit-measured)/limit
    grade: str | None = None            # QUALITATIVE 등급
    calc_trace: dict | None = None
    legal_refs: list[str] = Field(default_factory=list)
    basis_article: str | None = None


class StageResult(BaseModel):
    stage_id: str
    name: str
    stage_type: str
    status: str = "DONE"               # DONE | HELD | NEEDS_INPUT
    conformance: str = "HELD"          # 단계 종합(worst-of)
    criteria: list[CriterionResult] = Field(default_factory=list)
    verification_status: str = "NEEDS_REVIEW"   # CONFIRMED | NEEDS_REVIEW | BLOCKED
    remediation: list[str] = Field(default_factory=list)   # 대응 패키지(보완 가이드)
    issues: list[str] = Field(default_factory=list)        # 예상 쟁점
    authority: str | None = None
    submittals: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)


class ProcessResult(BaseModel):
    """프로세스 산출(프로세스-불문) — permit·design 공유. spec_id로 프로세스 종류 구분."""

    spec_id: str
    spec_version: str
    run_id: str | None = None
    roadmap: list[str] = Field(default_factory=list)        # 단계 순서(위상정렬)
    stages: list[StageResult] = Field(default_factory=list)
    overall_conformance: str = "HELD"                       # 종합(worst-of)
    overall_verification: str = "NEEDS_REVIEW"              # 최악 검증상태


# 후방호환 별칭 — 기존 permit 코드 무파손(시스템1 동일 타입).
PermitProcessResult = ProcessResult
