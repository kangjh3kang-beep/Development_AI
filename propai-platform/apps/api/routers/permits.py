"""Permit submission and tracking router for v53."""

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import PermitStatusResponse, PermitSubmissionRequest
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_deps import enforce_llm_quota
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


@router.post(
    "/compliance-check",
    response_model=ComplianceCheckResponse,
    dependencies=[Depends(enforce_llm_quota)],
)
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


class PermitFeasibilityRequest(BaseModel):
    """용도지역 기반 개발방식별 인허가 가능성(허용/불가/복잡도) 조회 요청."""

    zone_type: str


class PermitFeasibilityItem(BaseModel):
    development_type: str = ""
    type_name: str = ""
    zone_type: str = ""
    is_permitted: bool = False
    permit_complexity: int = 3
    complexity_label: str = ""
    reason: str = ""


class PermitFeasibilityResponse(BaseModel):
    zone_type: str = ""
    permitted_count: int = 0
    total_count: int = 0
    items: list[PermitFeasibilityItem] = Field(default_factory=list)
    summary: str = ""


@router.post("/feasibility-matrix", response_model=PermitFeasibilityResponse)
async def get_permit_feasibility_matrix(
    req: PermitFeasibilityRequest,
) -> PermitFeasibilityResponse:
    """용도지역(zone_type) 기준 개발방식별 인허가 가능/불가·복잡도를 산출한다.

    permit_validator(ZONE_PERMIT_MATRIX·PERMIT_COMPLEXITY) 실엔진을 그대로 노출하여,
    해당 용도지역에서 어떤 개발방식이 가능/불가/조건부인지를 프로젝트별로 제공한다.
    """
    from app.services.feasibility.permit_validator import (
        DEVELOPMENT_TYPE_NAMES,
        check_permit_feasibility,
    )

    zone = (req.zone_type or "").strip()
    if not zone:
        raise HTTPException(status_code=400, detail="용도지역(zone_type)이 필요합니다.")

    items = [
        PermitFeasibilityItem(**check_permit_feasibility(code, zone))
        for code in DEVELOPMENT_TYPE_NAMES
    ]
    # 가능한 것 먼저, 그다음 복잡도 낮은 순
    items.sort(key=lambda x: (not x.is_permitted, x.permit_complexity))
    permitted = sum(1 for it in items if it.is_permitted)
    return PermitFeasibilityResponse(
        zone_type=zone,
        permitted_count=permitted,
        total_count=len(items),
        items=items,
        summary=f"{zone}에서 {permitted}/{len(items)}개 개발방식 인허가 가능",
    )


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


class AIPermitAnalysisRequest(BaseModel):
    """인.허가 AI 분석 요청."""

    address: str
    pnu: str | None = None
    site: dict[str, Any] | None = None  # 부지분석 결과(있으면 재수집 생략)
    parcels: list[str] | None = None  # 다필지 통합 개발 시 추가 필지 주소(2개 이상이면 통합 용적률 산정)
    use_llm: bool = True  # AI 내러티브(개발방식별 LLM 분석) 포함 여부(사용자 선택)
    refresh: bool = False  # True이면 저장본을 무시하고 재분석 후 덮어씀


@router.post("/ai-analysis", dependencies=[Depends(enforce_llm_quota)])
async def ai_permit_analysis(
    req: AIPermitAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("permits", "read")),
) -> dict[str, Any]:
    """부지분석+조례+상위법령을 종합해 개발방식별 인허가 가능성·문제점·해결방안을 AI 분석.

    parcels에 2개 이상의 필지 주소가 오면 용도지역이 다른 토지를 통합 개발할 때의
    면적가중평균(법정)·최적·최고 용적률을 관련법규와 함께 산정한다.

    첫 호출만 느리고, 이후 같은 입력은 저장본을 즉시 반환한다.
    req.refresh=True 를 보내면 재분석 후 저장본을 덮어쓴다.
    """
    from app.services.common.analysis_cache import _key, cache_get, cache_put
    from app.services.permit.permit_analysis_service import PermitAnalysisService

    if not req.address or not req.address.strip():
        raise HTTPException(status_code=400, detail="주소가 필요합니다.")

    addr = req.address.strip()
    # parcels를 정렬해 순서 무관하게 동일 키가 나오게 한다
    parcels_str = ",".join(sorted(req.parcels or []))
    cache_key = _key(addr, str(req.pnu), str(req.use_llm), parcels_str)

    # 저장본이 있고 재분석 요청이 아니면 즉시 반환
    if not req.refresh:
        cached = await cache_get("permit_ai_analysis", cache_key)
        if cached is not None:
            return cached

    # 실제 분석 실행 → 저장 → 반환
    result = await PermitAnalysisService().analyze(
        addr, req.site or {}, parcels=req.parcels, use_llm=req.use_llm
    )
    await cache_put("permit_ai_analysis", cache_key, result)
    return result
