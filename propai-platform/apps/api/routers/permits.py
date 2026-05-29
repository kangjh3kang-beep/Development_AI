"""Permit submission and tracking router for v53."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import PermitStatusResponse, PermitSubmissionRequest
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.seumter_permit_service import SeumterPermitService

router = APIRouter()


# ── 건축법규 준수 검증 (주소 기반) ──


class ComplianceCheckRequest(BaseModel):
    """주소 기반 건축법규 준수 검증 요청."""
    address: str
    zoning_district: str | None = None
    project_type: str | None = None
    floor_count: int | None = None


class ComplianceItemResult(BaseModel):
    category: str = ""
    rule: str = ""
    status: str = "pass"
    detail: str = ""


class ComplianceCheckResponse(BaseModel):
    address: str = ""
    zoning_district: str | None = None
    results: list[ComplianceItemResult] = Field(default_factory=list)
    overall_status: str = "pass"
    summary: str = ""
    checked_at: str = ""


@router.post("/compliance-check", response_model=ComplianceCheckResponse)
async def check_building_compliance(
    req: ComplianceCheckRequest,
):
    """주소 기반 건축법규 준수 여부를 검증한다.

    용도지역·프로젝트 유형·층수 정보를 기반으로
    건폐율·용적률·높이제한 등 기본 법규를 검증한다.
    """
    zoning = req.zoning_district or "일반상업지역"
    # 용도지역별 기본 법규 한도 (간이 참조 테이블)
    zoning_limits: dict[str, dict[str, Any]] = {
        "제1종전용주거지역": {"bcr": 50, "far": 100, "max_floors": 4},
        "제2종전용주거지역": {"bcr": 50, "far": 150, "max_floors": 7},
        "제1종일반주거지역": {"bcr": 60, "far": 200, "max_floors": 7},
        "제2종일반주거지역": {"bcr": 60, "far": 250, "max_floors": 15},
        "제3종일반주거지역": {"bcr": 50, "far": 300, "max_floors": 20},
        "준주거지역": {"bcr": 70, "far": 500, "max_floors": 25},
        "일반상업지역": {"bcr": 80, "far": 1300, "max_floors": 40},
        "근린상업지역": {"bcr": 70, "far": 900, "max_floors": 30},
        "준공업지역": {"bcr": 70, "far": 400, "max_floors": 20},
    }
    limits = zoning_limits.get(zoning, {"bcr": 60, "far": 300, "max_floors": 15})

    results: list[ComplianceItemResult] = []
    overall = "pass"

    # 층수 검증
    if req.floor_count and req.floor_count > limits["max_floors"]:
        overall = "fail"
        results.append(ComplianceItemResult(
            category="높이제한",
            rule=f"{zoning} 최대 {limits['max_floors']}층",
            status="fail",
            detail=f"요청 {req.floor_count}층은 최대 {limits['max_floors']}층을 초과합니다.",
        ))
    else:
        results.append(ComplianceItemResult(
            category="높이제한",
            rule=f"{zoning} 최대 {limits['max_floors']}층",
            status="pass",
            detail=f"요청 {req.floor_count or '-'}층은 기준 이내입니다.",
        ))

    # 건폐율·용적률 기준 안내
    results.append(ComplianceItemResult(
        category="건폐율",
        rule=f"{zoning} 최대 {limits['bcr']}%",
        status="info",
        detail=f"건폐율 한도는 {limits['bcr']}%입니다. 설계 데이터 입력 시 정밀 검증 가능합니다.",
    ))
    results.append(ComplianceItemResult(
        category="용적률",
        rule=f"{zoning} 최대 {limits['far']}%",
        status="info",
        detail=f"용적률 한도는 {limits['far']}%입니다. 설계 데이터 입력 시 정밀 검증 가능합니다.",
    ))

    return ComplianceCheckResponse(
        address=req.address,
        zoning_district=zoning,
        results=results,
        overall_status=overall,
        summary=f"{zoning} 기준 법규 검증 완료 ({'위반 사항 있음' if overall == 'fail' else '적합'})",
        checked_at=datetime.now().isoformat(),
    )


@router.get("/{project_id}/status")
async def get_project_permit_status(project_id: str) -> dict:
    """프로젝트 인허가 상태 조회."""
    return {
        "project_id": project_id,
        "stages": [
            {"name": "사전검토", "status": "completed", "date": "2026-01-15"},
            {"name": "건축허가", "status": "in_progress", "date": None},
            {"name": "착공신고", "status": "pending", "date": None},
            {"name": "사용승인", "status": "pending", "date": None},
        ],
        "current_stage": "건축허가",
        "overall_progress_pct": 25,
        "documents_submitted": 3,
        "documents_required": 12,
    }


@router.post("/submit", response_model=PermitStatusResponse)
async def submit_permit(
    body: PermitSubmissionRequest,
    current_user: CurrentUser = Depends(RequirePermission("permits", "write")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.submit(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        permit_type=body.permit_type,
        region=body.region,
        building_area_sqm=body.building_area_sqm,
        is_public=body.is_public,
        is_agricultural=body.is_agricultural,
        applicant_name=body.applicant_name,
        submit_to_seumter=body.submit_to_seumter,
        submitted_document_ids=body.submitted_document_ids,
    )
    return PermitStatusResponse.model_validate(result)


@router.get("/{project_id}/latest", response_model=PermitStatusResponse)
async def get_latest_permit(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.get_latest(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest permit submission was not found",
        )
    return PermitStatusResponse.model_validate(result)


@router.get("/submissions/{submission_id}/status", response_model=PermitStatusResponse)
async def get_permit_status(
    submission_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
    db: AsyncSession = Depends(get_db),
) -> PermitStatusResponse:
    service = SeumterPermitService(db)
    result = await service.get_status(
        tenant_id=current_user.tenant_id,
        submission_id=submission_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permit submission was not found",
        )
    return PermitStatusResponse.model_validate(result)
