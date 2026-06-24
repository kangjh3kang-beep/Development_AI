"""Energy estimation endpoints for v43 rollout."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    EnergyCertificationRequest,
    EnergyCertificationResponse,
    KepcoCalculationRequest,
    KepcoCalculationResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.energy_service import EnergyService

router = APIRouter()


@router.post("/kepco/calculate", response_model=KepcoCalculationResponse)
async def calculate_kepco_bill(
    body: KepcoCalculationRequest,
    current_user: CurrentUser = Depends(RequirePermission("energy", "read")),
    db: AsyncSession = Depends(get_db),
) -> KepcoCalculationResponse:
    service = EnergyService(db)
    result = await service.calculate_kepco_bill(
        tenant_id=current_user.tenant_id,
        usage_kwh=body.usage_kwh,
        contract_type=body.contract_type,
        demand_kw=body.demand_kw,
    )

    # 표준 근거 블록(#5): 실제 산출한 요금 구성·합계와 그 산식·출처를 가산(graceful·무목업).
    evidence = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence = build_evidence_block(
            items=[
                {"label": "전력량요금(원)", "value": result.get("energy_charge_krw"),
                 "basis": "사용량(kWh) × KEPCO 단가(계약종별)"},
                {"label": "기본요금(원)", "value": result.get("base_charge_krw"),
                 "basis": "계약전력(kW) × 기본요금단가(계약종별)"},
                {"label": "기후환경요금(원)", "value": result.get("climate_fund_krw"),
                 "basis": "전력량요금 × 3.7%(기후환경요금률)"},
                {"label": "연료비조정액(원)", "value": result.get("fuel_adjustment_krw"),
                 "basis": "사용량(kWh) × 연료비조정단가"},
                {"label": "부가가치세(원)", "value": result.get("vat_krw"),
                 "basis": "(기본+전력량+연료비조정+기후환경) × 10%"},
                {"label": "청구합계(원)", "value": result.get("total_bill_krw"),
                 "basis": "소계 + 부가가치세 합산"},
            ],
            sources=["한국전력공사(KEPCO) 전기요금 계약종별 단가표"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 요금 결과를 막지 않음(가산·정직).
        pass

    return KepcoCalculationResponse(**result, evidence=evidence)


@router.post("/certification", response_model=EnergyCertificationResponse)
async def estimate_energy_certification(
    body: EnergyCertificationRequest,
    current_user: CurrentUser = Depends(RequirePermission("energy", "read")),
    db: AsyncSession = Depends(get_db),
) -> EnergyCertificationResponse:
    service = EnergyService(db)
    record = await service.certify_energy(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        total_area_sqm=body.total_area_sqm,
        floors=body.floors,
        window_wall_ratio=body.window_wall_ratio,
        insulation_grade=body.insulation_grade,
        bems_saving_rate=body.bems_saving_rate,
    )

    # 표준 근거 블록(#5): 실제 산출한 에너지등급·ZEB·수요량 값과 그 산식·근거(녹색건축물법)를 가산.
    evidence = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        evidence = build_evidence_block(
            items=[
                {"label": "건축물 에너지효율등급", "value": record.energy_grade,
                 "basis": "BEMS 절감 반영 후 연간 에너지수요(kWh/㎡·년) 구간 판정",
                 "legal_ref_key": "building_energy_rating"},
                {"label": "제로에너지건축물(ZEB) 등급", "value": record.zeb_grade,
                 "basis": "에너지자립률 구간 판정(신재생 발전량 ÷ 에너지수요)",
                 "legal_ref_key": "zeb_certification"},
                {"label": "연간 에너지수요(kWh)", "value": record.annual_energy_demand_kwh,
                 "basis": "ZEB 약식 추정 수요 − BEMS 절감량(수요×절감률)"},
                {"label": "에너지자립률(%)", "value": record.energy_independence_rate,
                 "basis": "연간 신재생 발전량 ÷ 연간 에너지수요"},
                {"label": "BEMS 절감량(kWh)", "value": record.bems_saving_kwh,
                 "basis": "원수요 × BEMS 절감률"},
            ],
            legal_ref_keys=["building_energy_rating", "zeb_certification", "green_building"],
            sources=["녹색건축물 조성 지원법 제17조(에너지효율등급·ZEB 인증)"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 인증 결과를 막지 않음(가산·정직).
        pass

    return EnergyCertificationResponse(
        energy_grade=record.energy_grade,
        zeb_grade=record.zeb_grade,
        annual_energy_demand_kwh=record.annual_energy_demand_kwh,
        annual_renewable_generation_kwh=record.annual_renewable_generation_kwh,
        energy_independence_rate=record.energy_independence_rate,
        bems_saving_rate=record.bems_saving_rate,
        bems_saving_kwh=record.bems_saving_kwh,
        recommendations=list(record.recommendations_json or []),
        evidence=evidence,
    )
