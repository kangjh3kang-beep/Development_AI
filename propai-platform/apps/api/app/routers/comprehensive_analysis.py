"""종합 부지분석 API 라우터.

주소 하나만 입력하면 7개 카테고리 자동 분석 보고서를 반환.
LLM 프로바이더를 선택하여 AI 해석에 사용할 모델을 지정할 수 있다.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.billing_deps import enforce_llm_quota
from app.services.auth.auth_service import get_current_user

# P2-2 보안: 종합분석 LLM 호출 라우트 인증 강제(무인증·무쿼터 LLM 호출 → 미과금 비용남용 차단).
# ★전수감사 보강: 사용자별 LLM 쿼터(enforce_llm_quota)를 라우터 레벨로 부착해 한도초과(402)
#   차단을 /comprehensive·/similar-market·/site-layout 전 경로에 일관 적용(경로별 과금정책 불일치 해소).
router = APIRouter(dependencies=[Depends(get_current_user), Depends(enforce_llm_quota)])


class ComprehensiveAnalysisRequest(BaseModel):
    address: str = Field(..., description="분석 대상 주소")
    llm_provider: str | None = Field(
        None, description="LLM 프로바이더 (anthropic/openai/google). 미지정 시 기본값 사용."
    )
    llm_model: str | None = Field(
        None, description="LLM 모델 ID (예: claude-sonnet-4-20250514, gpt-4o-mini). "
        "미지정 시 프로바이더 기본 모델 사용."
    )
    project_id: str | None = Field(
        None, description="프로젝트 ID(원장 성장루프 체인 스코프). 미지정 시 주소/PNU 기반 체인."
    )
    # ★다필지 통합분석: 33필지 등 다필지 업로드 시 필지목록(면적·용도지역 포함)을 전달하면
    #   종합분석이 '통합면적' 기준으로 산출된다(미전달 시 대표주소 단일필지 = N=1). 단일/다필지 일원화.
    parcels: list[dict] | None = Field(
        None,
        description="필지목록 [{pnu,address,area_sqm,zone_type}]. 다필지 통합분석용(미지정 시 단일).",
    )


@router.post("/comprehensive")
async def run_comprehensive_analysis(req: ComprehensiveAnalysisRequest, current_user=Depends(get_current_user)):
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    service = ComprehensiveAnalysisService()
    # Phase 1: 성장루프 체인 스코프(tenant_id+project_id)를 분석에 배선
    return await service.analyze(
        address=req.address,
        llm_provider=req.llm_provider,
        llm_model=req.llm_model,
        tenant_id=str(getattr(current_user, "tenant_id", "") or "") or None,
        project_id=req.project_id,
        parcels=req.parcels,
    )


class SimilarMarketRequest(BaseModel):
    address: str = Field(..., description="분석 대상 주소")
    land_area_sqm: float | None = Field(None, description="대지면적(㎡). 미지정 시 자동감지.")
    region: str = Field("서울", description="지역(공사비 권역).")
    equity_won: int = Field(10_000_000_000, description="자기자본(원). ROE 산정용.")
    use_llm: bool = Field(False, description="AI 해석 포함 여부.")
    with_senior: bool = Field(True, description="시니어 금융전문가 자문(DSCR 등) 포함 여부.")
    top_n: int = Field(3, ge=1, le=5, description="유사건축물 시장조사 가산 상위 추천 수.")


@router.post("/similar-market")
async def run_similar_market_feasibility(
    req: SimilarMarketRequest, current_user=Depends(get_current_user)
):
    """Stage 3 — 유사건축물 시장조사·사업성.

    검증된 사업성 엔진(auto_recommend_top3: 인허가 게이트·특이부지·senior 금융)의 사업유형별
    추천에, 설계 참조 라이브러리(시드 코퍼스)에서 검색한 유사 설계 도면을 가산해 반환한다.
    호출자 귀속(향후 사용량 쿼터)을 위해 current_user를 받는다(현재 설계 참조는 시드 tenant 스코프).
    """
    from app.services.land_intelligence.similar_market_service import (
        similar_market_feasibility,
    )

    return await similar_market_feasibility(
        address=req.address,
        land_area_sqm=req.land_area_sqm,
        region=req.region,
        equity_won=req.equity_won,
        use_llm=req.use_llm,
        with_senior=req.with_senior,
        top_n=req.top_n,
    )


class SiteLayoutRequest(BaseModel):
    parcel_geojson: dict | None = Field(
        None, description="대지 경계 GeoJSON geometry(WGS84). 미지정 시 pnu로 조회."
    )
    pnu: str | None = Field(None, description="필지 PNU(parcel_geojson 미지정 시 VWorld 조회).")
    zone_type: str = Field("", description="용도지역.")
    building_type: str = Field("", description="건축유형(빌라류면 판상 전용).")
    far_pct: float | None = Field(None, description="가용 용적률(%). 미지정 시 통념 폴백.")
    bcr_pct: float | None = Field(None, description="건폐율 상한(%). 동수 캡에 사용.")
    land_area_sqm: float | None = Field(None, description="대지면적(㎡). 미지정 시 폴리곤 면적.")
    priority: str = Field("balanced", description="배치 우선순위: balanced|daylight|density.")
    use_llm: bool = Field(False, description="LLM 부지맞춤 조언 포함 여부(기하는 결정론 불변).")


@router.post("/site-layout")
async def run_site_layout(req: SiteLayoutRequest, current_user=Depends(get_current_user)):
    """Stage 4 — 토지모양·향·접도 기반 배치도(buildable footprint + 동배치) on 구역도.

    대지 폴리곤을 세트백 오프셋해 buildable footprint를 만들고, 동을 그리드 샘플링으로 배치해
    일조준수·yield·조망 멀티오브젝티브로 최적안을 산출한다. 폴리곤 미확보 시 정직 고지.
    """
    from app.services.cad.site_layout_service import (
        attach_layout_llm_advice,
        build_site_layout,
    )

    geojson = req.parcel_geojson
    # parcel_geojson 미지정 + pnu 있으면 VWorld로 경계 조회(graceful).
    if not geojson and req.pnu:
        try:
            from app.services.external_api.vworld_service import VWorldService

            parcel = await VWorldService().get_parcel_by_pnu(req.pnu)
            geojson = (parcel or {}).get("geometry")
        except Exception:  # noqa: BLE001 — 조회 실패는 honest 빈 배치로 진행
            geojson = None

    layout = build_site_layout(
        parcel_geojson=geojson,
        zone_type=req.zone_type,
        building_type=req.building_type,
        far_pct=req.far_pct,
        bcr_pct=req.bcr_pct,
        land_area_sqm=req.land_area_sqm,
        priority=req.priority,
    )
    return await attach_layout_llm_advice(layout, use_llm=req.use_llm)


@router.get("/llm-providers")
async def list_llm_providers():
    """사용 가능한 LLM 프로바이더 목록 반환.

    API 키가 환경변수에 설정된 프로바이더만 반환한다.
    """
    from app.services.ai.llm_provider import get_available_providers

    return {"providers": get_available_providers()}
