"""ESG router for G84."""

from fastapi import APIRouter, Depends
from packages.schemas.models import ESGAssessmentRequest, ESGAssessmentResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing_deps import enforce_llm_quota
from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.esg_service import ESGService

router = APIRouter()


@router.post(
    "/assessment",
    response_model=ESGAssessmentResponse,
    dependencies=[Depends(enforce_llm_quota)],
)
async def run_esg_assessment(
    body: ESGAssessmentRequest,
    current_user: CurrentUser = Depends(RequirePermission("esg", "write")),
    db: AsyncSession = Depends(get_db),
) -> ESGAssessmentResponse:
    """Create ESG, carbon, and GRESB assessment outputs."""
    service = ESGService(db)
    report, footprint, assessment = await service.assess(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        reporting_period=body.reporting_period,
        gross_floor_area_sqm=body.gross_floor_area_sqm,
        scope1_tco2e=body.scope1_tco2e,
        scope2_tco2e=body.scope2_tco2e,
        scope3_tco2e=body.scope3_tco2e,
        energy_independence_rate=body.energy_independence_rate,
        climate_risk_score=body.climate_risk_score,
        lost_time_incident_rate=body.lost_time_incident_rate,
        community_programs_count=body.community_programs_count,
        board_independence_ratio=body.board_independence_ratio,
        disclosures=body.disclosures,
    )
    carbon_total = footprint.scope1_tco2e + footprint.scope2_tco2e + footprint.scope3_tco2e

    # LLM(Claude) ESG 해석 — 실패해도 평가 결과는 정상 반환(graceful fallback).
    # use_llm=False면 LLM 내러티브를 건너뛰고 규칙기반 수치결과만 반환(명시실행).
    ai: dict = {}
    try:
        if not body.use_llm:
            raise RuntimeError("use_llm=False — AI 내러티브 생략")
        from app.services.ai.esg_interpreter import EsgInterpreter

        gfa = body.gross_floor_area_sqm or 0
        interp = await EsgInterpreter().generate_interpretation({
            "carbon_emissions": {
                "total_emissions_tco2": carbon_total,
                "emissions_per_sqm": (round(carbon_total / gfa, 4) if gfa else None),
                "scope1": footprint.scope1_tco2e,
                "scope2": footprint.scope2_tco2e,
                "scope3": footprint.scope3_tco2e,
            },
            "gresb_score": {
                "total_score": assessment.score,
                "peer_ranking": assessment.rating,
            },
            "building_info": {"total_gfa_sqm": gfa},
        })
        if isinstance(interp, dict):
            ai = interp
    except Exception:
        ai = {}

    # 표준 근거 블록(#5): ESG/GRESB 실제 산출 점수·탄소·산식·법령링크를 가산.
    # graceful(실패해도 평가 결과는 정상 반환)·무목업(실값/실산식만, 빈 패널 금지).
    evidence = None
    try:
        from app.services.data_validation.evidence_contract import build_evidence_block

        gfa = body.gross_floor_area_sqm or 0
        # 탄소 강도(kgCO2e/㎡) = 총탄소(tCO2e)×1000 / 연면적(㎡). 음수/0면 None.
        intensity = round(carbon_total * 1000 / gfa, 2) if gfa else None
        items = []
        if report.environmental_score is not None:
            items.append({
                "label": "환경(E) 점수",
                "value": report.environmental_score,
                "basis": "탄소강도·에너지자립률·기후위험 기반 결정론 산식(0~100)",
            })
        if report.social_score is not None:
            items.append({
                "label": "사회(S) 점수",
                "value": report.social_score,
                "basis": "재해율(LTIR)·지역사회 프로그램 수 기반 산식(0~100)",
            })
        if report.governance_score is not None:
            items.append({
                "label": "지배구조(G) 점수",
                "value": report.governance_score,
                "basis": "이사회 독립성 비율 기반 산식(58 + 비율×42)",
            })
        if assessment.score is not None:
            items.append({
                "label": "종합 ESG 점수",
                "value": assessment.score,
                "basis": "E×0.45 + S×0.25 + G×0.30 가중평균",
            })
        if assessment.rating is not None:
            items.append({
                "label": "GRESB 등급",
                "value": assessment.rating,
                "basis": "종합점수 임계 판정(>=85 5Star, >=75 4Star, >=65 3Star, >=55 2Star)",
            })
        items.append({
            "label": "총 탄소배출량(tCO2e)",
            "value": carbon_total,
            "basis": "Scope1 + Scope2 + Scope3 합계",
        })
        if intensity is not None:
            items.append({
                "label": "탄소 강도(kgCO2e/㎡)",
                "value": intensity,
                "basis": "총탄소(tCO2e)×1000 / 연면적(㎡)",
            })
        evidence = build_evidence_block(
            items=items,
            legal_ref_keys=["green_building", "energy_efficiency",
                            "zeb_certification", "building_energy_rating"],
            sources=["GRESB 2025 평가 기준"],
        )
    except Exception:  # noqa: BLE001 — 근거 블록 실패는 결과를 막지 않음.
        evidence = None

    return ESGAssessmentResponse(
        assessment_id=assessment.id,
        project_id=report.project_id,
        reporting_period=report.reporting_period,
        status=report.status,
        environmental_score=report.environmental_score,
        social_score=report.social_score,
        governance_score=report.governance_score,
        overall_score=assessment.score,
        gresb_rating=assessment.rating,
        carbon_total_tco2e=carbon_total,
        disclosures=report.disclosures_json or [],
        action_plan=assessment.action_plan,
        evidence=evidence,
        ai_carbon_assessment=ai.get("carbon_assessment"),
        ai_reduction_strategy=ai.get("reduction_strategy"),
        ai_certification_pathway=ai.get("certification_pathway"),
        ai_zeb_roadmap=ai.get("zeb_roadmap"),
        ai_esg_investment_impact=ai.get("esg_investment_impact"),
        ai_regulatory_outlook=ai.get("regulatory_outlook"),
    )
