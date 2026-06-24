"""시공/ESG AI 라우터.

BIM4D 시공 일정 생성, ZEB 에너지 시뮬레이션, 기후 리스크 분석, 하자 분류.
"""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    ClimateRiskRequest,
    ClimateRiskResponse,
    ConstructionScheduleRequest,
    ConstructionScheduleResponse,
    DefectClassificationRequest,
    DefectClassificationResponse,
    ZEBEnergyRequest,
    ZEBEnergyResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.construction_ai_service import ConstructionAIService

router = APIRouter()


@router.post("/schedule", response_model=ConstructionScheduleResponse)
async def generate_schedule(
    body: ConstructionScheduleRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> ConstructionScheduleResponse:
    """표준품셈 기반 13공정 시공 일정을 생성한다."""
    service = ConstructionAIService(db)
    result = service.generate_construction_schedule(
        total_area_sqm=body.total_area_sqm,
        floors_above=body.floors_above,
        floors_below=body.floors_below,
        structure_type=body.structure_type,
    )
    # 표준 근거 블록(#5): 실제 산출한 공기·CPM 값과 산식·출처만 가산(graceful·무목업).
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        items = [
            {"label": "총 공사기간(일)", "value": result.get("total_duration_days"),
             "basis": "국토부 표준품셈 13공정 소요일 × 면적/층수/구조 보정 → CPM(주공정선) 최장경로"},
            {"label": "주공정선 공정수", "value": len(result.get("critical_path") or []),
             "basis": "여유시간(total float)=0 공정 = 공기 좌우 핵심공정"},
        ]
        result["evidence"] = build_evidence_block(
            items=items,
            legal_ref_keys=["construction_tech", "construction_industry"],
            sources=["국토교통부 건설공사 표준품셈"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 일정 결과를 막지 않음.
        pass
    return ConstructionScheduleResponse(**result)


@router.post("/zeb-energy", response_model=ZEBEnergyResponse)
async def estimate_zeb_energy(
    body: ZEBEnergyRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> ZEBEnergyResponse:
    """ZEB 에너지 시뮬레이션을 수행한다."""
    service = ConstructionAIService(db)
    result = service.estimate_zeb_energy(
        total_area_sqm=body.total_area_sqm,
        floors=body.floors,
        window_wall_ratio=body.window_wall_ratio,
        insulation_grade=body.insulation_grade,
    )
    # 표준 근거 블록(#5): 실제 산출한 에너지·자립률·등급 값과 산식·출처만 가산(graceful·무목업).
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        items = [
            {"label": "연간 에너지요구량(kWh)", "value": result.get("annual_energy_demand_kwh"),
             "basis": "열관류율(U값)×외피면적×난방도일(HDD2800)/냉방도일(CDD800) + 조명·환기·급탕(EnergyPlus 간소모델)"},
            {"label": "연간 재생에너지(kWh)", "value": result.get("annual_renewable_generation_kwh"),
             "basis": "지붕 60%×PV효율 20%×서울 일사량 3.5kWh/㎡·일×365"},
            {"label": "에너지 자립률(%)", "value": result.get("energy_independence_rate"),
             "basis": "재생에너지 생산량 ÷ 총 에너지요구량 × 100"},
            {"label": "ZEB 등급", "value": result.get("zeb_grade"),
             "basis": "에너지 자립률 구간별 ZEB 등급표(자립률 100%↑=1등급)"},
        ]
        result["evidence"] = build_evidence_block(
            items=items,
            legal_ref_keys=["zeb_certification", "building_energy_rating", "green_building"],
            sources=["기상청 난방·냉방도일(KMA)"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 에너지 결과를 막지 않음.
        pass
    return ZEBEnergyResponse(**result)


@router.post("/climate-risk", response_model=ClimateRiskResponse)
async def analyze_climate_risk(
    body: ClimateRiskRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "read")),
    db: AsyncSession = Depends(get_db),
) -> ClimateRiskResponse:
    """기후 리스크를 분석한다."""
    service = ConstructionAIService(db)
    result = await service.analyze_climate_risk(
        project_id=body.project_id,
        lat=body.lat,
        lon=body.lon,
        construction_period_months=body.construction_period_months,
    )
    # 표준 근거 블록(#5): 실제 산출한 리스크 점수·등급 값과 산식·출처만 가산(graceful·무목업).
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        items = [
            {"label": "홍수 리스크", "value": result.get("flood_risk_score"),
             "basis": "위도(남부)·경도(해안) 기반 보정(기본 0.25 + 해안 0.20 + 남부 0.10)"},
            {"label": "폭염 리스크", "value": result.get("heat_risk_score"),
             "basis": "RCP 8.5 시나리오 기본 0.30 + 남부 0.25"},
            {"label": "종합 등급", "value": result.get("overall_risk_level"),
             "basis": "(홍수×0.5 + 폭염×0.5) 종합점수 구간 판정"},
        ]
        result["evidence"] = build_evidence_block(
            items=items,
            sources=["기상청 RCP 8.5 기후변화 시나리오(KMA)"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 기후 결과를 막지 않음.
        pass
    return ClimateRiskResponse(**result)


@router.post("/defect-classify", response_model=DefectClassificationResponse)
async def classify_defect(
    body: DefectClassificationRequest,
    current_user: CurrentUser = Depends(RequirePermission("design", "write")),
    db: AsyncSession = Depends(get_db),
) -> DefectClassificationResponse:
    """하자 사진을 AI로 분류한다."""
    service = ConstructionAIService(db)
    result = await service.classify_defect_image(
        project_id=body.project_id,
        image_url=body.image_url,
        location=body.location,
    )
    # 표준 근거 블록(#5): AI가 실제 판정한 하자유형·심각도·신뢰도와 판정근거만 가산(graceful·무목업).
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        items = [
            {"label": "하자 유형", "value": result.get("defect_type"),
             "basis": "Claude Vision 사진 판독(하자 유형 분류표 매칭)"},
            {"label": "심각도", "value": result.get("severity"),
             "basis": "AI 판정(MINOR/MODERATE/MAJOR/CRITICAL)"},
            {"label": "판정 신뢰도", "value": result.get("confidence"),
             "basis": "AI 비전 모델 자기 신뢰도(0=판독불가 시 전문가 점검 권고)"},
        ]
        result["evidence"] = build_evidence_block(
            items=items,
            legal_ref_keys=["construction_tech"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 하자 분류 결과를 막지 않음.
        pass
    return DefectClassificationResponse(**result)
