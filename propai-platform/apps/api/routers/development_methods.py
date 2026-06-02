"""개발방법 평가 라우터.

7가지 부동산 개발방법(단독, 합동, 환지, 도시개발, 도시정비, PPP, 리모델링)을
AHP 가중 평가하고 최적 방법을 추천하는 API.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.development_method_service import (
    DevelopmentMethodService,
    SiteProfile,
)

router = APIRouter()


# ── 요청/응답 스키마 ──


class SiteProfileRequest(BaseModel):
    """부지 프로파일 요청 스키마."""

    site_area_sqm: float = Field(gt=0, description="부지 면적 (m2)")
    zoning_type: str = Field(
        max_length=100,
        description="용도지역 (예: 제1종일반주거지역, 일반상업지역, 준공업지역)",
    )
    current_use: str = Field(
        max_length=50,
        description="현재 용도 (나대지, 주거, 상업, 공업, 농지)",
    )
    ownership_type: str = Field(
        max_length=50,
        description="소유 형태 (단독, 공유, 국유, 법인)",
    )
    road_frontage_m: float = Field(ge=0, description="접도 길이 (m)")
    transit_score: float = Field(ge=0, le=10, description="교통접근성 (0~10)")
    current_value_krw: float = Field(ge=0, description="현재 토지 가치 (원)")
    building_age_years: int | None = Field(
        default=None, ge=0, description="기존 건물 연수 (없으면 null)"
    )
    num_owners: int = Field(default=1, ge=1, description="소유자 수")


class DevelopmentMethodRequest(BaseModel):
    """개발방법 평가 요청 스키마."""

    project_id: UUID
    site_profile: SiteProfileRequest


class MethodScoreItem(BaseModel):
    """개별 개발방법 점수."""

    score: float = Field(description="가중 종합 점수")
    rank: int = Field(description="순위")


class DevelopmentMethodResponse(BaseModel):
    """개발방법 평가 응답 스키마."""

    id: UUID
    project_id: UUID
    site_area_sqm: float = Field(description="부지 면적 (m2)")
    zoning_type: str = Field(description="용도지역")
    recommended_method: str = Field(description="추천 개발방법")
    recommended_method_score: float = Field(description="추천 방법 가중 점수")
    bcr: float = Field(description="간이 BCR (비용효익비)")
    method_scores: dict[str, MethodScoreItem] = Field(
        description="7가지 방법별 점수 및 순위"
    )
    ahp_weights: dict[str, float] = Field(description="AHP 가중치")
    analysis_summary: str | None = Field(description="분석 요약")

    class Config:
        """Pydantic 모델 설정."""
        from_attributes = True


# ── 엔드포인트 ──


@router.post("/evaluate", response_model=DevelopmentMethodResponse)
async def evaluate_development_methods(
    body: DevelopmentMethodRequest,
    current_user: CurrentUser = Depends(RequirePermission("finance", "write")),
    db: AsyncSession = Depends(get_db),
) -> DevelopmentMethodResponse:
    """7가지 개발방법을 AHP 가중 평가하고 최적 방법을 추천한다.

    부지 프로파일(면적, 용도지역, 소유형태 등)을 입력하면
    단독개발, 합동개발, 환지방식, 도시개발, 도시정비,
    민관합작(PPP), 리모델링에 대한 종합 점수와 추천 결과를 반환한다.
    """
    # 요청 스키마 → SiteProfile dataclass 변환
    site_profile = SiteProfile(
        site_area_sqm=body.site_profile.site_area_sqm,
        zoning_type=body.site_profile.zoning_type,
        current_use=body.site_profile.current_use,
        ownership_type=body.site_profile.ownership_type,
        road_frontage_m=body.site_profile.road_frontage_m,
        transit_score=body.site_profile.transit_score,
        current_value_krw=body.site_profile.current_value_krw,
        building_age_years=body.site_profile.building_age_years,
        num_owners=body.site_profile.num_owners,
    )

    service = DevelopmentMethodService(db)
    result = await service.evaluate(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        site_profile=site_profile,
    )

    # JSON 필드를 Pydantic 스키마에 맞게 변환
    method_scores: dict[str, MethodScoreItem] = {}
    raw_scores: dict[str, Any] = result.method_scores_json or {}
    for method_name, score_data in raw_scores.items():
        method_scores[method_name] = MethodScoreItem(
            score=score_data["score"],
            rank=score_data["rank"],
        )

    ahp_weights: dict[str, float] = result.ahp_weights_json or {}

    return DevelopmentMethodResponse(
        id=result.id,
        project_id=result.project_id,
        site_area_sqm=result.site_area_sqm,
        zoning_type=result.zoning_type,
        recommended_method=result.recommended_method,
        recommended_method_score=result.recommended_method_score,
        bcr=result.bcr,
        method_scores=method_scores,
        ahp_weights=ahp_weights,
        analysis_summary=result.analysis_summary,
    )


# ── 다각도 개발 시나리오 시뮬레이션 (정책 적용판정 + 최적안 + 단순건축 폴백) ──

class ScenarioSimRequest(BaseModel):
    """개발 시나리오 시뮬레이션 요청 (인증 불필요·부지 공개데이터 기반)."""

    address: str
    parcels: list[str] | None = None  # 다필지 통합 시뮬레이션
    site: dict[str, Any] | None = None
    use_llm: bool = True


@router.post("/scenarios", summary="다각도 개발방식 시뮬레이션(정책별 적용판정·최적안)")
async def development_scenarios(body: ScenarioSimRequest) -> dict[str, Any]:
    """단일/다필지에 대해 도시개발법·지구단위·가로주택·모아주택·역세권 등 정책
    적용요건을 판정하고 정책별 예상 용적률·기부채납·실현성을 산정해 최적 사업방안을
    제안한다(미적용 시 단순 건축 폴백)."""
    from fastapi import HTTPException

    from app.services.development.scenario_simulator import DevelopmentScenarioSimulator

    if not body.address or not body.address.strip():
        raise HTTPException(status_code=400, detail="주소가 필요합니다.")
    return await DevelopmentScenarioSimulator().simulate(
        body.address.strip(), parcels=body.parcels, site=body.site or {}, use_llm=body.use_llm
    )
