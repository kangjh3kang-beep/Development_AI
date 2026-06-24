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
    # 표준 근거 블록(#5) — 적합성·기준 충족현황·산식(기준값)·법령링크. 미부착 시 None.
    evidence: dict | None = Field(default=None)


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

    # 표준 근거 블록(#5): EU Taxonomy 실제 판정·기준 충족현황·기준값(산식)·법령링크 가산.
    # graceful(실패해도 검증 결과는 정상 반환)·무목업(실값/실 기준값/실 rationale만).
    evidence = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        items = [
            {
                "label": "적합성 판정",
                "value": result.alignment,
                "basis": "TSC 전부+DNSH 전부+MSS 전부 통과=Aligned, TSC 일부 통과=Partially, 그외 Not",
            },
            {
                "label": "기준 충족",
                "value": f"{result.passed_count}/{result.total_count}",
                "basis": "TSC(3)+DNSH(4)+MSS(1) 8개 기준 중 통과 개수",
            },
        ]
        # 개별 기준은 실제 판정 결과(actual_value·threshold·rationale)를 그대로 근거화.
        for c in result.criteria:
            items.append({
                "label": f"[{c.category}] {c.name}",
                "value": f"{'통과' if c.passed else '미통과'} (실측 {c.actual_value} / 기준 {c.threshold})",
                "basis": c.rationale,
            })
        evidence = build_evidence_block(
            items=items,
            # 국내 근거 법령(녹색건축물 조성 지원법·환경영향평가법). EU 규정 URL은
            # 레지스트리 미보유이므로 링크 없이 텍스트만(할루시네이션 링크 금지).
            legal_ref_keys=["green_building", "energy_efficiency",
                            "zeb_certification", "building_energy_rating", "env_impact"],
            sources=["EU Taxonomy Regulation (EU) 2020/852 TSC/DNSH/MSS"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 결과를 막지 않음.
        evidence = None

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
        evidence=evidence,
    )
