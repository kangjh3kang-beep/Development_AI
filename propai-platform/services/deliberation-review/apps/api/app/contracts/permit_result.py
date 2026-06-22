"""인·허가/심의 프로세스 산출 계약 — 로드맵 + 단계별 심의 계측 + 대응 + 검증.

모든 정량 계측은 calc_trace(measured/limit/basis/source — 설명가능성)·legal_refs 동반. 값은 JSON 직렬화 위해 float.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.contracts.rationale import LegalRef


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
    # 설명가능성 기본화 — 근거조문 해소(법령명·조항·요지·시행일·1차출처 링크). 미해소 시 [](식별자만, 무음 금지).
    legal_basis: list[LegalRef] = Field(default_factory=list)


class CapacityEnvelope(BaseModel):
    """매스 캐파 검증(Phase 2b) — 엔진 SSOT(용적/건폐) 기반 최대 허용 규모 + 제공 매스 적정성 검증(생성 아님).

    ★검증 전용: 최대 연면적/건축면적을 SSOT 한도로 산정하고 제공 매스(proposed_gfa)와 대조(부합/미흡/미상).
    정북일조·심의 완화 등 추가 제약은 별도(design_gen solar_envelope 소관) — caveat로 표면화(과대 단정 금지).
    """

    max_gfa_sqm: float | None = None        # 최대 연면적 = 대지면적 × 용적률
    max_footprint_sqm: float | None = None  # 최대 건축면적 = 대지면적 × 건폐율
    plot_area_sqm: float | None = None
    far_pct: float | None = None
    bcr_pct: float | None = None
    proposed_gfa_sqm: float | None = None
    conformance: str = "미상"               # 부합 | 미흡 | 미상(캐파/제공 매스 부재)
    margin_sqm: float | None = None         # 여유 = 최대연면적 − 제공연면적(계산식)
    legal_basis: list[LegalRef] = Field(default_factory=list)
    caveat: str = "SSOT 한도(용적·건폐) 기반 최대 캐파 — 정북일조·완화 등 추가 제약 별도(design_gen 소관)"


class OutcomePrediction(BaseModel):
    """단계 승인 가능성 예측(Phase 2a) — 결정론 휴리스틱. ★정밀 확률(%) 미생성(학습모델 없이 날조 금지).

    likelihood 등급 + 도출근거(rationale)+투입신호(basis)+한계(caveat) 동반(설명가능성). pluggable ML은 후속.
    """

    likelihood: str = "미상"           # 높음 | 보통 | 낮음 | 미상
    predictor: str = "heuristic_v1"
    rationale: str = ""                # 왜 이 등급인지(도출 근거)
    basis: list[str] = Field(default_factory=list)   # 투입 신호(완결성/부합도/검증)
    caveat: str = "결정론 휴리스틱 — 통계/학습모델 아님, 위원 재량 미반영"


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
    outcome: OutcomePrediction | None = None   # Phase 2a 승인 가능성 예측(outcome_predictor 설정 단계만)
    capacity: CapacityEnvelope | None = None   # Phase 2b 매스 캐파 검증(설계 massing 단계만)


class ProcessResult(BaseModel):
    """프로세스 산출(프로세스-불문) — permit·design 공유. spec_id로 프로세스 종류 구분."""

    spec_id: str
    spec_version: str
    run_id: str | None = None
    roadmap: list[str] = Field(default_factory=list)        # 단계 순서(위상정렬)
    stages: list[StageResult] = Field(default_factory=list)
    overall_conformance: str = "HELD"                       # 종합(worst-of)
    overall_verification: str = "NEEDS_REVIEW"              # 최악 검증상태
    overall_outcome: str = "미상"                           # Phase 2a 종합 승인 가능성(높음/보통/낮음/미상)


# 후방호환 별칭 — 기존 permit 코드 무파손(시스템1 동일 타입).
PermitProcessResult = ProcessResult
