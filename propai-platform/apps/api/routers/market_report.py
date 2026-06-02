"""시장조사보고서 라우터 — 구조화 JSON / PDF / PPTX 생성."""

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.market.market_report_service import MarketReportService

router = APIRouter(prefix="/api/v1/market", tags=["시장조사보고서"])


class MarketReportRequest(BaseModel):
    address: str
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    use_llm: bool = True  # AI 내러티브 분석 포함 여부(사용자 선택)


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


@router.post("/report")
async def market_report(req: MarketReportRequest):
    lawd_cd, pnu = _resolve(req)
    return await MarketReportService().build_report(req.address, lawd_cd, pnu, use_llm=req.use_llm)


@router.post("/report/pdf")
async def market_report_pdf(req: MarketReportRequest):
    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(req.address, lawd_cd, pnu, use_llm=req.use_llm)
    pdf = svc.to_pdf(rep)
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="market_report.pdf"'},
    )


@router.post("/report/pptx")
async def market_report_pptx(req: MarketReportRequest):
    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(req.address, lawd_cd, pnu, use_llm=req.use_llm)
    pptx = svc.to_pptx(rep)
    return StreamingResponse(
        iter([pptx]),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": 'attachment; filename="market_report.pptx"'},
    )
