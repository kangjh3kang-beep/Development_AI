"""프로젝트 단위 per-field 데이터 조회 계약 — 분석 결과를 프로젝트로 집계해 필드별 값 제공(읽기 측).

쓰기 측(save_analysis가 X-Project-Id를 project_id로 적재)의 대응 조회 — '각 데이터값을 필드별로 제공'
요구의 읽기 경로. 한 프로젝트에 귀속된 모든 분석 run의 legal_quantity/finding을 필드 단위로 반환(어느 run에서
왔는지 analysis_id로 추적). 테넌트 격리는 store가 보장(#8a). 값은 JSON 직렬화 위해 float로 정규화.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectQuantity(BaseModel):
    """프로젝트 내 법정 산정값 1건(필드별) — 출처 run(analysis_id)·스냅샷 추적 가능."""

    analysis_id: str | None = None
    snapshot_id: str | None = None
    variable_id: str
    value: float | None = None
    unit: str | None = None
    status: str | None = None
    confidence: float | None = None
    calc_rule_version: str | None = None


class ProjectFinding(BaseModel):
    """프로젝트 내 판정 1건(필드별) — 출처 run·근거조문·게이팅상태 동반."""

    analysis_id: str | None = None
    snapshot_id: str | None = None
    rule_id: str
    verdict: str
    gated_status: str | None = None
    basis_article: str | None = None
    measured_value: float | None = None
    limit_value: float | None = None
    composite_confidence: float | None = None
    requires_committee: bool = False


class ProjectFieldData(BaseModel):
    """프로젝트 단위 per-field 데이터 번들 — 귀속된 분석들의 필드별 값 집계.

    run_count는 프로젝트에 귀속된 distinct 분석 run 수(per-field 행의 max_rows 캡과 무관하게 정확).
    quantities/findings는 max_rows로 상한(거대 응답 방어) — 상한 도달 시 truncated=True로 표면화(무음 절단 금지).
    """

    project_id: str
    run_count: int = 0
    truncated: bool = False
    quantities: list[ProjectQuantity] = Field(default_factory=list)
    findings: list[ProjectFinding] = Field(default_factory=list)
