"""부지기반(site basis) 게이트 응답 스키마 — 명세 P7 최소 사상(WP-G).

P2(dev_act_permit_gate)·P4(access_basis)가 공유하는 상태 어휘(PASS/CONDITIONAL/BLOCKED/
REQUIRES_AUTHORITY_CONFIRMATION) 문자열과 P3 권리확정 여부(bool)를 입력받아, artifact_status
(DRAFT/ANALYZED/REVIEW_REQUIRED/APPROVED/STALE)·basis_status(ADVISORY/AUTHORIZED)를 반환한다.

★신뢰경계(트러스트 바운더리 — 분리 리뷰 MEDIUM-3): access_status/dev_act_status는 기본적으로
호출자 자기신고(요청 본문 그대로)다 — 인증된 호출자라도 이 값 자체의 진위를 서버가 검증하지
않는다는 뜻이다(위조 가능한 입력). site_context를 함께 보내면 서버가 access_basis_service·
dev_act_permit_gate로 재도출해 자기신고값과 교차검증하고(불일치 시 보수값 채택), 응답의
gates[].source에 "server_derived"(재도출값 채택)/"server_derived_conflict_resolved"(불일치
조정)/"caller_declared"(재도출 재료 없어 자기신고 신뢰)/"unknown"(미신고)로 그 출처를 명시한다.
site_context 없이 caller_declared로만 판정되면 자동판정은 ANALYZED로 승격하지 않는다
(REVIEW_REQUIRED 상한 — 미검증 자기신고만으로 인간승인 대기자격을 얻지 못하게 하는 보수 정책).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SiteBasisAssessRequest(BaseModel):
    """P0 게이트 자동집계 요청 — 이미 산출된 P2·P4 게이트 status와 P3 확정 여부를 전달.

    ★access_status/dev_act_status는 자기신고(caller_declared)다 — 신뢰경계는 모듈 docstring
    참조. site_context를 함께 제공하면 서버가 권위 서비스로 재도출·교차검증한다.
    """

    pnu: str | None = Field(None, description="PNU(체인 식별)")
    address: str | None = Field(None, description="주소(체인 식별 — PNU 없을 때 보조)")
    project_id: str | None = Field(None, description="프로젝트 ID(체인 식별)")
    access_status: str | None = Field(
        None, description=(
            "P4 access_basis 종합 status(PASS/CONDITIONAL/BLOCKED/REQUIRES_AUTHORITY_CONFIRMATION) — "
            "자기신고(caller_declared). site_context 제공 시 서버 재도출값과 교차검증됨."
        ),
    )
    dev_act_status: str | None = Field(
        None, description=(
            "P2 dev_act_permit_gate status(동일 어휘) — 자기신고(caller_declared). "
            "site_context 제공 시 서버 재도출값과 교차검증됨."
        ),
    )
    rights_confirmed: bool | None = Field(
        None, description="P3 권리분석 확정 여부(보수 게이트 — None/False는 모두 미확정으로 취급)"
    )
    site_context: dict[str, Any] | None = Field(
        None, description=(
            "부지분석 result와 동형(road_side·zone_type·land_category 등) 판정 재료(선택). "
            "제공 시 access_basis_service.assess_access·dev_act_permit_gate.assess_dev_act_permit로 "
            "서버측 재도출해 access_status/dev_act_status 자기신고값과 교차검증한다(신뢰경계 강화)."
        ),
    )


class SiteBasisApproveRequest(BaseModel):
    """인간승인 액션 요청 — 승인 시점 P0 재확인 값(미제공 시 저장된 gates 스냅샷 재사용)."""

    access_status: str | None = Field(None, description="승인 시점 재확인용(선택)")
    dev_act_status: str | None = Field(None, description="승인 시점 재확인용(선택)")
    rights_confirmed: bool | None = Field(None, description="승인 시점 재확인용(선택)")


class GateResultOut(BaseModel):
    """P0 게이트 1건 판정(name/clear/status/reason/source)."""

    name: str
    clear: bool
    status: str | None = None
    reason: str
    source: str = Field(
        "caller_declared",
        description="신뢰경계 출처 — server_derived/server_derived_conflict_resolved/caller_declared/unknown",
    )


class SiteBasisResult(BaseModel):
    """부지기반 게이트 조회/판정 응답 — artifact_status·basis_status 분리."""

    run_id: str
    artifact_status: str = Field(..., description="DRAFT/ANALYZED/REVIEW_REQUIRED/APPROVED/STALE")
    basis_status: str = Field(..., description="ADVISORY/AUTHORIZED — AUTHORIZED는 인간승인 경유만")
    gates: list[GateResultOut] = Field(default_factory=list)
    content_hash: str | None = None
    stale_propagated: list[str] = Field(
        default_factory=list, description="이번 판정으로 STALE 강등된 기존 승인 run_id 목록"
    )
    approved_by: str | None = None
    ledger_hash: str | None = Field(None, description="analysis_ledger content_hash(피드백 조인키)")
    noop_preserved_approval: bool | None = Field(
        None, description="true면 동일 내용 재분석이 기존 APPROVED를 무음 취소하지 않고 그대로 보존됨(no-op)"
    )
