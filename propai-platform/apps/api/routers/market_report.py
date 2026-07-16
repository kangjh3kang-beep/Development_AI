"""시장조사보고서 라우터 — 구조화 JSON / PDF / PPTX 생성."""

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.billing_deps import enforce_llm_quota
from app.services.land_intelligence.parcel_normalize import ParcelsIn
from app.services.market.market_report_service import MarketReportService
from app.services.market.migration_region_service import MigrationRegionService
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
    #   ★공용 정규화(ParcelsIn): str[]/dict[] 양 shape → canonical dict[](무음 no-op 제거).
    parcels: ParcelsIn | None = None


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
    result = await MarketReportService().build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options, parcels=req.parcels)
    # ★성장루프 조인키: 시장보고서 요약을 원장에 best-effort 적재(멱등) 후 최상위 `ledger_hash`
    #   노출 — 시장 인사이트 화면의 피드백(👍/👎)이 원장과 조인된다. 실패해도 보고서 무손상.
    try:
        from app.services.ledger.analysis_ledger_service import attach_ledger_hash
        from app.services.ledger.ledger_adapters import record_user_analysis
        if isinstance(result, dict):
            wb = await record_user_analysis(
                analysis_type="market_report",
                summary={
                    "address": req.address, "lawd_cd": lawd_cd, "pnu": pnu,
                    "use_llm": req.use_llm,
                    "parcel_count": len(req.parcels or []) or 1,
                    "trade_count": (result.get("stats") or {}).get("count")
                    if isinstance(result.get("stats"), dict) else None,
                },
                tenant_id=str(getattr(current_user, "tenant_id", "") or "") or None,
                pnu=pnu or None, address=req.address, source="market_report",
            )
            result = attach_ledger_hash(result, wb)
    except Exception:  # noqa: BLE001 — 원장 적재 실패해도 보고서 무손상
        pass
    return result


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


class MigrationRegionRequest(BaseModel):
    address: str | None = None
    pnu: str | None = None
    bcode: str | None = None
    jibun_address: str | None = None
    year: str | None = None


@router.post("/migration-region")
async def migration_region(
    req: MigrationRegionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """권역 인구이동망 레이어 — 대상 시군구가 속한 시도의 시군구별 순이동 발산 코로플레스.

    SGIS 시군구 경계(WGS84) + KOSIS「시군구별 이동자수」 순이동을 조인해 권역(시도) 지도를
    색으로 시각화한다(전출초과=적·전입초과=청·0=중립). LLM 미사용(데이터 조회) → 과금 게이트 없음.
    KOSIS/SGIS 무키·무자료는 data_source=unavailable(가짜 순이동 금지).
    """
    pnu = req.pnu
    if not pnu and req.bcode and req.jibun_address:
        pnu = _pnu_from_bcode(req.bcode, req.jibun_address)
    bcode = ((pnu or "")[:10] if pnu else (req.bcode or "")) or ""
    return await MigrationRegionService().build_migration_region(
        bcode=bcode, region_name=_region_name(req.address), year=req.year)


@router.post("/report/pdf", dependencies=[Depends(enforce_llm_quota)])
async def market_report_pdf(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """시장조사보고서 PDF — 통합 보고서 생성엔진 경유(build_report_model_from_market + render_report).

    엔드포인트 경로·요청 계약·응답 헤더(파일명 등)는 프론트 무수정 목표로 이전과 동일 유지."""
    from app.services.report.render import build_report_model_from_market, render_report

    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    model = build_report_model_from_market(rep)
    pdf, _media_type, _ext = render_report(model, "pdf")
    return StreamingResponse(
        iter([pdf]), media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="market_report.pdf"'},
    )


@router.post("/report/pptx", dependencies=[Depends(enforce_llm_quota)])
async def market_report_pptx(
    req: MarketReportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """시장조사보고서 PPTX — 통합 보고서 생성엔진 경유(PDF 라우트와 동일 어댑터·모델 재사용)."""
    from app.services.report.render import build_report_model_from_market, render_report

    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    model = build_report_model_from_market(rep)
    pptx, _media_type, _ext = render_report(model, "pptx")
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
    """시장조사보고서 DOCX — 통합 보고서 생성엔진 경유(PDF 라우트와 동일 어댑터·모델 재사용)."""
    from app.services.report.render import build_report_model_from_market, render_report

    lawd_cd, pnu = _resolve(req)
    svc = MarketReportService()
    rep = await svc.build_report(
        req.address, lawd_cd, pnu, use_llm=req.use_llm, options=req.options or {}, parcels=req.parcels)
    model = build_report_model_from_market(rep)
    docx, _media_type, _ext = render_report(model, "docx")
    return StreamingResponse(
        iter([docx]),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="market_report.docx"'},
    )
