"""CAD 파라메트릭 자동 보정 API 라우터 (Phase 15).

건축물 설계안의 건폐율/용적률/높이 법규 적합성을 검증하고,
위반 시 자동 보정된 설계안을 반환한다.

엔드포인트:
- POST /api/v1/cad-correction/check      — 법규 검증
- POST /api/v1/cad-correction/auto-correct — 자동 보정
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from apps.api.services.cad_auto_correction_service import (
    BuildingModel,
    CadAutoCorrectionService,
    RegulationLimit,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ──────────────────────────────────────────────
# 요청/응답 스키마
# ──────────────────────────────────────────────


class BuildingPayload(BaseModel):
    """건축물 설계 데이터 요청 본문."""

    site_area_sqm: float = Field(..., gt=0, description="대지면적 (㎡)")
    building_area_sqm: float = Field(..., gt=0, description="건축면적 (㎡)")
    num_floors: int = Field(..., ge=1, description="층수")
    floor_height_m: float = Field(default=3.0, gt=0, description="층고 (m)")


class RegulationPayload(BaseModel):
    """법규 제한 기준 요청 본문."""

    max_bcr: float = Field(..., gt=0, le=100, description="건폐율 상한 (%)")
    max_far: float = Field(..., gt=0, description="용적률 상한 (%)")
    max_height_m: float = Field(default=0.0, ge=0, description="높이 상한 (m), 0이면 제한 없음")


class CheckRequest(BaseModel):
    """법규 검증 요청."""

    building: BuildingPayload
    regulation: RegulationPayload


class AutoCorrectRequest(BaseModel):
    """자동 보정 요청."""

    building: BuildingPayload
    regulation: RegulationPayload
    max_iter: int = Field(default=100, ge=1, le=1000, description="최대 보정 반복 횟수")


class ViolationResponse(BaseModel):
    """위반 사항 응답."""

    item: str
    current_value: float
    limit_value: float
    excess: float


class CheckResponse(BaseModel):
    """법규 검증 응답."""

    is_compliant: bool
    violations: list[ViolationResponse]
    building_info: dict[str, Any]


class CorrectionResponse(BaseModel):
    """자동 보정 응답."""

    original: dict[str, Any]
    corrected: dict[str, Any]
    violations_before: list[dict[str, Any]]
    violations_after: list[dict[str, Any]]
    iterations: int
    is_compliant: bool
    corrections_applied: list[str]


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────


@router.post("/check", response_model=CheckResponse)
async def check_compliance(
    req: CheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CheckResponse:
    """설계안의 법규 적합성을 검증한다."""
    logger.info(
        "CAD 법규 검증 요청",
        site_area=req.building.site_area_sqm,
        building_area=req.building.building_area_sqm,
    )

    building = BuildingModel(
        site_area_sqm=req.building.site_area_sqm,
        building_area_sqm=req.building.building_area_sqm,
        num_floors=req.building.num_floors,
        floor_height_m=req.building.floor_height_m,
    )
    regulation = RegulationLimit(
        max_bcr=req.regulation.max_bcr,
        max_far=req.regulation.max_far,
        max_height_m=req.regulation.max_height_m,
    )

    violations = CadAutoCorrectionService.check_compliance(building, regulation)

    return CheckResponse(
        is_compliant=len(violations) == 0,
        violations=[
            ViolationResponse(
                item=v.item,
                current_value=v.current_value,
                limit_value=v.limit_value,
                excess=v.excess,
            )
            for v in violations
        ],
        building_info={
            "bcr": building.bcr,
            "far": building.far,
            "height_m": building.total_height_m,
            "gross_floor_area_sqm": building.gross_floor_area_sqm,
        },
    )


@router.post("/auto-correct", response_model=CorrectionResponse)
async def auto_correct(
    req: AutoCorrectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> CorrectionResponse:
    """법규 위반 항목에 대한 자동 보정을 수행한다."""
    logger.info(
        "CAD 자동 보정 요청",
        site_area=req.building.site_area_sqm,
        building_area=req.building.building_area_sqm,
        num_floors=req.building.num_floors,
    )

    building = BuildingModel(
        site_area_sqm=req.building.site_area_sqm,
        building_area_sqm=req.building.building_area_sqm,
        num_floors=req.building.num_floors,
        floor_height_m=req.building.floor_height_m,
    )
    regulation = RegulationLimit(
        max_bcr=req.regulation.max_bcr,
        max_far=req.regulation.max_far,
        max_height_m=req.regulation.max_height_m,
    )

    result = CadAutoCorrectionService.auto_correct(
        building, regulation, max_iter=req.max_iter
    )

    logger.info(
        "CAD 자동 보정 완료",
        is_compliant=result.is_compliant,
        iterations=result.iterations,
    )

    return CorrectionResponse(
        original=result.original,
        corrected=result.corrected,
        violations_before=result.violations_before,
        violations_after=result.violations_after,
        iterations=result.iterations,
        is_compliant=result.is_compliant,
        corrections_applied=result.corrections_applied,
    )
