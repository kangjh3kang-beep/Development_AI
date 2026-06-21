"""실무 전문가 페르소나 라우터 — 분양대행·도시계획 동시.

페르소나 백엔드는 오케스트레이션 레이어다(기존 서비스 primitive 재사용·본문 무변경).
과금(R4): use_llm 기본 false=무과금. use_llm=True일 때만 LLM 한도 게이트(enforce_llm_quota)를
핸들러 내부에서 분기 적용하고, 과금은 관리자가 analysis_modules에 키를 설정한 경우에만(미설정=무료).
계정격리(R6): get_current_user(tenant_id) 필수. 산출물(PDF/PPT)은 기존 빌더 재사용.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.persona import PersonaAnalyzeRequest
from app.services.persona.registry import get_persona, list_personas
from app.services.persona.runner import run_persona
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

router = APIRouter(prefix="/personas", tags=["실무 전문가 페르소나"])


def _ctx(req: PersonaAnalyzeRequest) -> dict[str, Any]:
    return {
        "project_id": req.project_id,
        "site_id": req.site_id,
        "address": req.address,
        "parcels": req.parcels,
        "bcode": req.bcode,
        # pnu는 시장보고서(LAWD_CD 도출)·규제분석 정밀조회에 쓰이므로 ctx에 포함한다.
        # runner.py(분양 build_report·regulation.analyze)가 ctx.get("pnu")로 읽는다.
        "pnu": req.pnu,
        "equity_won": req.equity_won,
        # 설계(designer)·시공(constructor) SSOT 입력 — runner._run_designer/_run_constructor 가 소비.
        # 미공급 시 각 파이프라인이 폴백/추정/partial 로 정직 강등(무목업).
        "total_gfa_sqm": req.total_gfa_sqm,
        "land_area_sqm": req.land_area_sqm,
        "zone_code": req.zone_code,
        "building_type": req.building_type,
        # R11 핸드오프 — 디벨로퍼 종합(_consume_handoff)이 ctx['report_contracts']로 읽는다.
        "report_contracts": req.report_contracts,
    }


async def _enforce_llm_if_needed(db: AsyncSession, use_llm: bool) -> None:
    """use_llm=True일 때만 LLM 한도 게이트 적용(무과금 경로는 통과)."""
    if not use_llm:
        return
    from app.core.billing_deps import enforce_llm_quota
    await enforce_llm_quota(db)


@router.get("", summary="페르소나 목록(레지스트리 메타)")
async def list_personas_endpoint(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return {"personas": list_personas()}


@router.post("/{key}/analyze", summary="페르소나 실무 분석(오케스트레이션)")
async def analyze_persona(
    key: str,
    req: PersonaAnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not get_persona(key):
        raise HTTPException(status_code=404, detail=f"알 수 없는 페르소나: {key}")
    await _enforce_llm_if_needed(db, req.use_llm)
    return await run_persona(key, db, _ctx(req), use_llm=req.use_llm)


@router.post("/{key}/analyze/pdf", summary="페르소나 분석 PDF")
async def analyze_persona_pdf(
    key: str,
    req: PersonaAnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    spec = get_persona(key)
    if not spec:
        raise HTTPException(status_code=404, detail=f"알 수 없는 페르소나: {key}")
    await _enforce_llm_if_needed(db, req.use_llm)
    report = await run_persona(key, db, _ctx(req), use_llm=req.use_llm)

    if key == "urban_planner":
        from app.services.persona import urban_report
        pdf = urban_report.to_pdf(report)
        fname = "urban_permit_review.pdf"
    elif key == "sales_agent":
        # 분양대행 PDF = 시장조사보고서 빌더 재사용(주소·법정동코드 확보 시).
        pdf = await _sales_pdf(req, report)
        fname = "sales_pricing_report.pdf"
    elif key == "developer":
        # 디벨로퍼 PDF = 사업계획서(전용 렌더러·urban 패턴 복제).
        from app.services.persona import developer_report
        pdf = developer_report.to_pdf(report)
        fname = "developer_business_plan.pdf"
    elif key == "designer":
        from app.services.persona import designer_report
        pdf = designer_report.to_pdf(report)
        fname = "design_review.pdf"
    elif key == "constructor":
        from app.services.persona import constructor_report
        pdf = constructor_report.to_pdf(report)
        fname = "construction_cost_estimate.pdf"
    else:  # pragma: no cover
        raise HTTPException(status_code=400, detail="해당 페르소나는 PDF를 지원하지 않습니다.")

    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/{key}/analyze/pptx", summary="페르소나 분석 PPTX(분양대행)")
async def analyze_persona_pptx(
    key: str,
    req: PersonaAnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if key != "sales_agent":
        raise HTTPException(status_code=400, detail="PPTX는 분양대행(sales_agent)만 지원합니다.")
    if not get_persona(key):
        raise HTTPException(status_code=404, detail=f"알 수 없는 페르소나: {key}")
    await _enforce_llm_if_needed(db, req.use_llm)
    address, lawd, pnu = _sales_market_args(req)
    if not (address and lawd):
        raise HTTPException(status_code=400,
                            detail="분양대행 PPTX는 주소와 법정동코드(bcode/pnu)가 필요합니다.")
    from app.services.market.market_report_service import MarketReportService
    svc = MarketReportService()
    rep = await svc.build_report(address, lawd, pnu, use_llm=req.use_llm, options={})
    pptx = svc.to_pptx(rep)
    return StreamingResponse(
        iter([pptx]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="sales_pricing.pptx"'},
    )


def _sales_market_args(req: PersonaAnalyzeRequest) -> tuple[str | None, str | None, str | None]:
    """분양대행 시장보고서 인자(주소·법정동코드·pnu) 해석."""
    address = req.address
    pnu = getattr(req, "pnu", None) or None
    lawd = (req.bcode or "")[:5] if req.bcode else ((pnu or "")[:5] if pnu else None)
    if lawd and len(lawd) < 5:
        lawd = None
    return address, lawd, pnu


async def _sales_pdf(req: PersonaAnalyzeRequest, report: dict[str, Any]) -> bytes:
    """분양대행 PDF — 시장조사보고서 빌더 재사용(R8). 주소·법정동코드 미확보면 명확히 차단."""
    address, lawd, pnu = _sales_market_args(req)
    if not (address and lawd):
        # report.address(suggest가 해석한 주소)·lawd_cd 폴백
        address = address or report.get("address")
        lawd = lawd or None
    if not (address and lawd):
        raise HTTPException(status_code=400,
                            detail="분양대행 PDF는 주소와 법정동코드(bcode/pnu)가 필요합니다.")
    from app.services.market.market_report_service import MarketReportService
    svc = MarketReportService()
    rep = await svc.build_report(address, lawd, pnu, use_llm=req.use_llm, options={})
    # 페르소나 분양가 책정 섹션을 rep에 가산(to_pdf가 rep.get으로 안전접근).
    rep["persona_pricing"] = report.get("artifacts", {}).get("price_tiers")
    return svc.to_pdf(rep)
