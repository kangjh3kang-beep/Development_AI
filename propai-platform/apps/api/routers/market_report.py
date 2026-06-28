"""시장조사보고서 라우터 — 구조화 JSON / PDF / PPTX 생성."""

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.billing_deps import enforce_llm_quota
from app.services.market.market_report_service import MarketReportService
from app.services.market.population_density_service import PopulationDensityService
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter(prefix="/api/v1/market", tags=["시장조사보고서"])


class MarketReportRequest(BaseModel):
    address: str
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    use_llm: bool = True  # AI 내러티브 분석 포함 여부(사용자 선택)
    # 선택형 분석 모듈 옵션. 프론트(P1)가 중첩 dict(detail 등)를 보내므로 dict[str, bool]로
    #   제한하면 Pydantic 422가 발생한다 → 값 타입을 풀어 어떤 형태의 옵션도 받도록 완화.
    options: dict | None = None
    # 다필지(통합분석) 필지목록. 프론트(ComprehensiveAnalysisPanel)가 2개 이상 업로드 시 전송.
    #   각 행 = {address, area_sqm, zone_type, farPct(실효), bcrPct(실효), farLegalPct?, bcrLegalPct?}.
    #   2개 이상이면 면적가중 통합면적으로 land_area를 산정한다(대표 1필지 고착 버그 해소).
    #   None/1개면 기존 단일필지 경로 그대로(무회귀).
    parcels: list[dict] | None = None


def _pnu_from_bcode(bcode: str, jibun: str) -> str | None:
    if not bcode or len(bcode) < 10:
        return None
    m = re.search(r"(산)?(\d+)(?:-(\d+))?(?:\s|$)", jibun or "")
    if not m:
        return None
    return f"{bcode}{'2' if m.group(1) else '1'}{m.group(2).zfill(4)}{(m.group(3) or '0').zfill(4)}"


def _resolve(req: MarketReportRequest) -> tuple[str, str | None]:
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _pnu_from_bcode(req.bcode, req.jibun_address)
    lawd_cd = (pnu or "")[:5] if pnu else (req.bcode or "")[:5]
    if not lawd_cd or len(lawd_cd) < 5:
        raise HTTPException(status_code=400, detail="법정동코드 결정 불가 — bcode 또는 pnu 필요")
    return lawd_cd, pnu


@router.post("/report", dependencies=[Depends(enforce_llm_quota)])
async def market_report(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    lawd_cd, pnu = _resolve(req)
    return await MarketReportService().build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options, parcels=req.parcels)


class PopulationDensityRequest(BaseModel):
    address: str | None = None
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None


def _region_name(address: str | None) -> str | None:
    """주소에서 SGIS 시군구 해석용 시/군/구 토큰 추출(예: '의정부시','강남구')."""
    if not address:
        return None
    m = re.findall(r"([가-힣]+(?:시|군|구))", address)
    # 통합시 자치구(예: '수원시 장안구')는 마지막 구 토큰이 더 구체적.
    return m[-1] if m else None


@router.post("/population-density")
async def population_density(
    req: PopulationDensityRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """P4-B 인구밀도 레이어 데이터 — SGIS 행정동 경계(WGS84)+인구 → 밀도 코로플레스.

    LLM 미사용(데이터 조회) → 과금 게이트 없음. 무자료/키없음은 data_source=unavailable.
    """
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _pnu_from_bcode(req.bcode, req.jibun_address)
    bcode = ((pnu or "")[:10] if pnu else (req.bcode or "")) or ""
    return await PopulationDensityService().build(bcode=bcode, region_name=_region_name(req.address))


@router.post("/report/pdf", dependencies=[Depends(enforce_llm_quota)])
async def market_report_pdf(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    pdf = svc.to_pdf(rep)
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="market_report.pdf"'},
    )


@router.post("/report/pptx", dependencies=[Depends(enforce_llm_quota)])
async def market_report_pptx(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    pptx = svc.to_pptx(rep)
    return StreamingResponse(
        iter([pptx]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="market_report.pptx"'},
    )


@router.post("/report/docx", dependencies=[Depends(enforce_llm_quota)])
async def market_report_docx(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    docx = svc.to_docx(rep)
    return StreamingResponse(
        iter([docx]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="market_report.docx"'},
    )
