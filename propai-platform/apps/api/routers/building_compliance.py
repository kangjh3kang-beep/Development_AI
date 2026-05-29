"""v44.0 건축 법규 검증 / 자동 보정 API 라우터 (G96~G99).

CAD 설계 데이터의 건폐율·용적률·높이·구조 법규 준수 여부를 검증하고,
위반 시 자동 보정 대안을 생성한다.
"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.session import get_db
from apps.api.services.building_compliance_service import BuildingComplianceService

router = APIRouter()


class DesignPayload(BaseModel):
    """CAD 설계 데이터 요청 본문."""

    points: list[dict[str, Any]] = Field(default_factory=list)
    lines: list[dict[str, Any]] = Field(default_factory=list)
    surfaces: list[dict[str, Any]] = Field(default_factory=list)
    floor_count: int = 1
    building_height_m: float = 0.0
    scale: float = 10.0


class CheckRequest(BaseModel):
    project_id: str
    design: DesignPayload


class AutoCorrectRequest(BaseModel):
    project_id: str
    design: DesignPayload
    violation_type: str


# ── 응답 스키마 ──


class ComplianceCheckResult(BaseModel):
    """건축 법규 검증 결과."""
    project_id: str | None = None
    overall_status: str = "unknown"
    results: list[dict[str, Any]] = Field(default_factory=list)
    bcr: float | None = None
    far: float | None = None
    height_ok: bool | None = None


class AutoCorrectResult(BaseModel):
    """자동 보정 결과."""
    original_violation: str = ""
    corrected_design: dict[str, Any] = Field(default_factory=dict)
    correction_summary: str = ""


@router.post("/check", response_model=ComplianceCheckResult)
async def check_compliance(
    req: CheckRequest,
    db: AsyncSession = Depends(get_db),
):
    """설계 데이터의 건축 법규 준수 여부를 검증한다."""
    svc = BuildingComplianceService(db=db)
    return await svc.check_compliance(
        project_id=req.project_id,
        design_raw=req.design.model_dump(),
    )


@router.post("/auto-correct")
async def auto_correct(
    req: AutoCorrectRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """법규 위반 항목에 대한 자동 보정 대안을 생성한다."""
    svc = BuildingComplianceService(db=db)
    return await svc.auto_correct(
        project_id=req.project_id,
        design_raw=req.design.model_dump(),
        violation_type=req.violation_type,
    )
