"""부지기반(site basis) 게이트 응답 스키마 — 명세 P7 최소 사상(WP-G).

P2(dev_act_permit_gate)·P4(access_basis)가 공유하는 상태 어휘(PASS/CONDITIONAL/BLOCKED/
REQUIRES_AUTHORITY_CONFIRMATION) 문자열과 P3 권리확정 여부(bool)를 입력받아, artifact_status
(DRAFT/ANALYZED/REVIEW_REQUIRED/APPROVED/STALE)·basis_status(ADVISORY/AUTHORIZED)를 반환한다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SiteBasisAssessRequest(BaseModel):
    """P0 게이트 자동집계 요청 — 이미 산출된 P2·P4 게이트 status와 P3 확정 여부를 전달."""

    pnu: str | None = Field(None, description="PNU(체인 식별)")
    address: str | None = Field(None, description="주소(체인 식별 — PNU 없을 때 보조)")
    project_id: str | None = Field(None, description="프로젝트 ID(체인 식별)")
    access_status: str | None = Field(
        None, description="P4 access_basis 종합 status(PASS/CONDITIONAL/BLOCKED/REQUIRES_AUTHORITY_CONFIRMATION)"
    )
    dev_act_status: str | None = Field(
        None, description="P2 dev_act_permit_gate status(동일 어휘)"
    )
    rights_confirmed: bool | None = Field(
        None, description="P3 권리분석 확정 여부(보수 게이트 — None/False는 모두 미확정으로 취급)"
    )


class SiteBasisApproveRequest(BaseModel):
    """인간승인 액션 요청 — 승인 시점 P0 재확인 값(미제공 시 저장된 gates 스냅샷 재사용)."""

    access_status: str | None = Field(None, description="승인 시점 재확인용(선택)")
    dev_act_status: str | None = Field(None, description="승인 시점 재확인용(선택)")
    rights_confirmed: bool | None = Field(None, description="승인 시점 재확인용(선택)")


class GateResultOut(BaseModel):
    """P0 게이트 1건 판정(name/clear/status/reason)."""

    name: str
    clear: bool
    status: str | None = None
    reason: str


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
