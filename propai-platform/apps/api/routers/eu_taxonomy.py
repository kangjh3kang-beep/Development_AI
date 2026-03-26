"""EU Taxonomy 적합성 검증 엔드포인트.

POST /api/v1/eu-taxonomy/check — EU Taxonomy 검증
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.eu_taxonomy_service import (
    BuildingData,
    EuTaxonomyChecker,
)

router = APIRouter()


# ── 요청/응답 스키마 ──


class EuTaxonomyCheckRequest(BaseModel):
    """EU Taxonomy 검증 요청."""

    primary_energy_demand_kwh_m2: float = Field(
        ..., description="1차 에너지 소요량 (kWh/m2/yr)"
    )
    renewable_energy_ratio: float = Field(
        ..., ge=0, le=1, description="재생에너지 비율 (0~1)"
    )
    embodied_carbon_kgco2e_m2: float = Field(
        ..., ge=0, description="내재탄소 (kgCO2e/m2)"
    )
    water_usage_liters_per_day: float = Field(
        ..., ge=0, description="일일 물 사용량 (L/person/day)"
    )
    waste_recycling_rate: float = Field(
        ..., ge=0, le=1, description="건설 폐기물 재활용률 (0~1)"
    )
    green_ratio: float = Field(
        ..., ge=0, le=1, description="녹지율 (0~1)"
    )
    has_climate_risk_assessment: bool = Field(
        ..., description="기후위험 평가 수행 여부"
    )
    has_social_safeguards: bool = Field(
        ..., description="사회적 안전장치(ILO 핵심 노동 기준) 준수 여부"
    )
    gross_floor_area_sqm: float = Field(
        ..., gt=0, description="연면적 (m2)"
    )


class TaxonomyCriterionResponse(BaseModel):
    """개별 기준 결과."""

    name: str
    category: str
    passed: bool
    actual_value: float | str
    threshold: float | str
    rationale: str


class EuTaxonomyCheckResponse(BaseModel):
    """EU Taxonomy 검증 응답."""

    alignment: str = Field(..., description="Aligned | Partially Aligned | Not Aligned")
    criteria: list[TaxonomyCriterionResponse]
    passed_count: int
    total_count: int
    recommendations: list[str]


# ── 엔드포인트 ──


@router.post("/check", response_model=EuTaxonomyCheckResponse)
async def check_eu_taxonomy(
    body: EuTaxonomyCheckRequest,
    current_user: CurrentUser = Depends(RequirePermission("eu_taxonomy", "read")),
    db: AsyncSession = Depends(get_db),
) -> EuTaxonomyCheckResponse:
    """EU Taxonomy 적합성을 검증한다.

    건축물의 TSC/DNSH/MSS 기준 충족 여부를 판정하고,
    미충족 항목에 대한 개선 권고사항을 제공한다.
    """
    building = BuildingData(
        primary_energy_demand_kwh_m2=body.primary_energy_demand_kwh_m2,
        renewable_energy_ratio=body.renewable_energy_ratio,
        embodied_carbon_kgco2e_m2=body.embodied_carbon_kgco2e_m2,
        water_usage_liters_per_day=body.water_usage_liters_per_day,
        waste_recycling_rate=body.waste_recycling_rate,
        green_ratio=body.green_ratio,
        has_climate_risk_assessment=body.has_climate_risk_assessment,
        has_social_safeguards=body.has_social_safeguards,
        gross_floor_area_sqm=body.gross_floor_area_sqm,
    )

    # EuTaxonomyChecker는 DB를 사용하지 않지만, 향후 기록 저장을 위해 인스턴스화
    _checker = EuTaxonomyChecker(db)
    result = EuTaxonomyChecker.check(building)

    return EuTaxonomyCheckResponse(
        alignment=result.alignment,
        criteria=[
            TaxonomyCriterionResponse(
                name=c.name,
                category=c.category,
                passed=c.passed,
                actual_value=c.actual_value,
                threshold=c.threshold,
                rationale=c.rationale,
            )
            for c in result.criteria
        ],
        passed_count=result.passed_count,
        total_count=result.total_count,
        recommendations=result.recommendations,
    )
