"""나라장터(G2B) 입찰/낙찰 FastAPI 라우터."""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.g2b_bid import (
    G2BAwardStatsResponse,
    G2BBidAnalyzeRequest,
    G2BBidAnalyzeResponse,
    G2BBidFilter,
    G2BBidListResponse,
    G2BBidResponse,
    G2BDashboardStats,
)
from app.services.g2b_bid_service import G2BBidService

router = APIRouter(prefix="/g2b", tags=["공공입찰(G2B)"])


def _get_service(db: AsyncSession = Depends(get_db)) -> G2BBidService:
    return G2BBidService(db)


# ──────────────────────────────────────────
# 대시보드 통계
# ──────────────────────────────────────────

@router.get("/dashboard", response_model=G2BDashboardStats, summary="공공입찰 대시보드 요약 통계")
async def get_dashboard_stats(service: G2BBidService = Depends(_get_service)):
    """현재 진행 중 공고 수, 마감 임박, 평균 낙찰가율, AI 추천 건수 등 대시보드 요약."""
    return await service.get_dashboard_stats()


# ──────────────────────────────────────────
# 수동 동기화 (나라장터 API 즉시 수집)
# ──────────────────────────────────────────

@router.post("/sync", response_model=dict, summary="나라장터 입찰/낙찰 수동 수집")
async def sync_g2b(
    days: int = Query(7, ge=1, le=90, description="최근 N일 수집"),
    include_awards: bool = Query(True, description="낙찰 결과도 함께 갱신"),
    service: G2BBidService = Depends(_get_service),
):
    """나라장터 API에서 최근 입찰 공고(+낙찰 결과)를 즉시 수집·저장한다.

    arq 스케줄러 없이도 동작하며, 부동산/건설 관련 공고만 필터링하여 저장한다.
    """
    from datetime import datetime, timedelta

    from app.core.config import settings
    from app.integrations.g2b_client import G2BClient

    service_key = settings.G2B_SERVICE_KEY
    if not service_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="G2B 서비스 키가 설정되지 않았습니다.",
        )

    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=days)
    start_s = start_dt.strftime("%Y%m%d%H%M")
    end_s = end_dt.strftime("%Y%m%d%H%M")

    client = G2BClient(service_key=service_key)
    try:
        bid_items = await client.fetch_all_bid_notices(start_date=start_s, end_date=end_s)
        saved = await service.upsert_bid_notices(bid_items)

        result: dict = {"fetched_bids": len(bid_items), "saved_bids": saved}

        if include_awards:
            award_items = await client.fetch_all_award_results(start_date=start_s, end_date=end_s)
            updated = await service.update_award_results(award_items)
            result["fetched_awards"] = len(award_items)
            result["updated_awards"] = updated

        return {"status": "ok", **result}
    finally:
        await client.close()


# ──────────────────────────────────────────
# 입찰 공고
# ──────────────────────────────────────────

@router.get("/bids", response_model=G2BBidListResponse, summary="입찰 공고 목록 조회")
async def list_bids(
    keyword: Optional[str] = Query(None, description="공고명 검색"),
    bid_type: Optional[str] = Query(None, description="업무구분(공사/용역/물품)"),
    region_sido: Optional[str] = Query(None, description="시/도"),
    region_sigungu: Optional[str] = Query(None, description="시/군/구"),
    status_filter: Optional[str] = Query(None, alias="status", description="상태"),
    category_tag: Optional[str] = Query(None, description="AI 분류 태그"),
    min_price: Optional[int] = Query(None, description="최소 추정가격"),
    max_price: Optional[int] = Query(None, description="최대 추정가격"),
    org_type: Optional[str] = Query(None, description="기관유형"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: G2BBidService = Depends(_get_service),
):
    """부동산개발/건설 관련 입찰 공고를 필터링하여 조회한다."""
    f = G2BBidFilter(
        keyword=keyword,
        bid_type=bid_type,
        region_sido=region_sido,
        region_sigungu=region_sigungu,
        status=status_filter,
        category_tag=category_tag,
        min_price=min_price,
        max_price=max_price,
        org_type=org_type,
        page=page,
        page_size=page_size,
    )
    return await service.list_bids(f)


@router.get("/bids/{bid_id}", response_model=G2BBidResponse, summary="입찰 공고 상세 조회")
async def get_bid(bid_id: UUID, service: G2BBidService = Depends(_get_service)):
    """입찰 공고 단건 상세 조회."""
    bid = await service.get_bid(bid_id)
    if not bid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="입찰 공고를 찾을 수 없습니다.")
    return G2BBidResponse.model_validate(bid)


@router.get(
    "/bids/{bid_id}/deeplink",
    summary="나라장터 바로가기 URL",
    response_model=dict,
)
async def get_deeplink(bid_id: UUID, service: G2BBidService = Depends(_get_service)):
    """해당 입찰 공고의 나라장터 상세 페이지 URL을 반환한다."""
    bid = await service.get_bid(bid_id)
    if not bid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="입찰 공고를 찾을 수 없습니다.")
    return {"url": bid.g2b_url, "bid_notice_no": bid.bid_notice_no}


# ──────────────────────────────────────────
# AI 분석
# ──────────────────────────────────────────

@router.post(
    "/bids/{bid_id}/analyze",
    response_model=G2BBidAnalyzeResponse,
    summary="AI 입찰 분석 (수지분석 연동)",
)
async def analyze_bid(
    bid_id: UUID,
    req: G2BBidAnalyzeRequest,
    service: G2BBidService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    """입찰 공고에 대한 AI 분석 (적정 투찰가 예측 + 사업성 진단 + 리스크 스코어링)."""
    bid = await service.get_bid(bid_id)
    if not bid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="입찰 공고를 찾을 수 없습니다.")

    # AI 분석 서비스 호출
    from app.services.ai_services.bid_analyzer import BidAnalyzer

    analyzer = BidAnalyzer(db)
    result = await analyzer.analyze(bid, req)
    return result


@router.post(
    "/bids/{bid_id}/feasibility",
    response_model=G2BBidAnalyzeResponse,
    summary="AI 정밀 분석 (6엔진 연동: QTO·수지·용도지역·법규·ESG·시장)",
)
async def analyze_bid_feasibility(
    bid_id: UUID,
    req: G2BBidAnalyzeRequest,
    service: G2BBidService = Depends(_get_service),
    db: AsyncSession = Depends(get_db),
):
    """입찰 공고를 사통팔땅 6개 엔진에 연결한 정밀 분석.

    추정가격을 평당공사비로 역산해 연면적/구조를 추정(또는 수동 보정)한 뒤
    QTO→원가→수지 Monte Carlo→민감도→용도지역→건축법규 PQ→ESG→시장동향을
    통합해 마진·최적 투찰가·리스크를 산출한다. 각 엔진 실패 시 해당 섹션만 생략.
    """
    bid = await service.get_bid(bid_id)
    if not bid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="입찰 공고를 찾을 수 없습니다.")

    from app.services.ai_services.bid_analyzer import BidAnalyzer

    analyzer = BidAnalyzer(db)
    return await analyzer.analyze_feasibility(bid, req)


# ──────────────────────────────────────────
# 낙찰 통계
# ──────────────────────────────────────────

@router.get("/awards/stats", response_model=G2BAwardStatsResponse, summary="낙찰가율 통계")
async def get_award_stats(
    bid_type: Optional[str] = Query(None, description="업무구분"),
    region_sido: Optional[str] = Query(None, description="시/도"),
    service: G2BBidService = Depends(_get_service),
):
    """지역별/공종별 낙찰가율 통계를 조회한다."""
    return await service.get_award_stats(bid_type=bid_type, region_sido=region_sido)
