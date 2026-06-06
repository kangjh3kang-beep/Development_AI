"""Auction intelligence router for G95.

추가: 경·공매 1단계 — 온비드(공매) 전국연동 3탭(내토지 연동분 / 전국 조건검색 /
전국 최저입찰가 순위) + 저장조건 CRUD + 낙찰가능가 추정 + 관리/cron 동기화.
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from packages.schemas.models import AuctionAnalysisRequest, AuctionListingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.auction_service import AuctionService

router = APIRouter()


def _step1_service(db: AsyncSession = Depends(get_db)):
    from app.services.auction.auction_service import AuctionStep1Service

    return AuctionStep1Service(db)


def _onbid_service_key() -> Optional[str]:
    """온비드 서비스 키 해석: ONBID_SERVICE_KEY → settings 폴백(없으면 None=mock)."""
    import os

    key = os.getenv("ONBID_SERVICE_KEY")
    if key:
        return key
    try:
        from app.core.config import settings

        return getattr(settings, "ONBID_SERVICE_KEY", "") or None
    except Exception:  # noqa: BLE001
        return None


def _serialize_listing(listing) -> AuctionListingResponse:
    analysis = listing.analysis_json or {}
    return AuctionListingResponse(
        listing_id=listing.id,
        project_id=listing.project_id,
        auction_type=listing.auction_type,
        case_number=listing.case_number,
        court_name=listing.court_name,
        address=listing.address,
        property_type=listing.property_type,
        appraised_value_krw=listing.appraised_value_krw,
        minimum_bid_krw=listing.minimum_bid_krw,
        bid_count=listing.bid_count,
        auction_date=listing.auction_date,
        status=listing.status,
        discount_ratio=float(analysis.get("discount_ratio", 0.0)),
        market_gap_ratio=float(analysis.get("market_gap_ratio", 0.0)),
        investment_score=float(analysis.get("investment_score", 0.0)),
        recommended_max_bid_krw=float(
            analysis.get("recommended_max_bid_krw", listing.minimum_bid_krw)
        ),
        expected_margin_krw=float(analysis.get("expected_margin_krw", 0.0)),
        diligence_flags=list(analysis.get("diligence_flags", [])),
        created_at=listing.created_at,
    )


@router.post("/analyze", response_model=AuctionListingResponse)
async def analyze_auction_listing(
    body: AuctionAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    db: AsyncSession = Depends(get_db),
) -> AuctionListingResponse:
    service = AuctionService(db)
    listing = await service.analyze_and_store(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        auction_type=body.auction_type,
        case_number=body.case_number,
        court_name=body.court_name,
        address=body.address,
        property_type=body.property_type,
        appraised_value_krw=body.appraised_value_krw,
        minimum_bid_krw=body.minimum_bid_krw,
        bid_count=body.bid_count,
        auction_date=body.auction_date,
        occupancy_status=body.occupancy_status,
        senior_lien_exists=body.senior_lien_exists,
        expected_repair_cost_krw=body.expected_repair_cost_krw,
        nearby_market_price_krw=body.nearby_market_price_krw,
    )
    return _serialize_listing(listing)


@router.get("/listings/{listing_id}", response_model=AuctionListingResponse)
async def get_auction_listing(
    listing_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    db: AsyncSession = Depends(get_db),
) -> AuctionListingResponse:
    service = AuctionService(db)
    listing = await service.get_listing(
        tenant_id=current_user.tenant_id,
        listing_id=listing_id,
    )
    if listing is None:
        raise HTTPException(status_code=404, detail="Auction listing not found")
    return _serialize_listing(listing)


@router.get("/opportunities", response_model=list[AuctionListingResponse])
async def list_auction_opportunities(
    project_id: UUID | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[AuctionListingResponse]:
    service = AuctionService(db)
    listings = await service.list_opportunities(
        tenant_id=current_user.tenant_id,
        limit=limit,
        project_id=project_id,
    )
    return [_serialize_listing(listing) for listing in listings]


# ══════════════════════════════════════════════════════════════════════
# 경·공매 1단계 — 온비드(공매) 전국연동 3탭 + 저장조건 + 낙찰가능가 + 동기화
# ══════════════════════════════════════════════════════════════════════


@router.get("/search", summary="② 전국 조건검색(지역·종류·유찰·가격·낙찰가능가)")
async def auction_search(
    region: Optional[str] = Query(None, description="시/도(예: 서울)"),
    kind: Optional[str] = Query(None, description="종류(land/building/apt/officetel/factory/etc)"),
    min_fail: Optional[int] = Query(None, ge=0, description="최소 유찰회수"),
    max_price: Optional[int] = Query(None, ge=0, description="최대 최저입찰가(원)"),
    est_win_max: Optional[int] = Query(None, ge=0, description="예상 낙찰가(중앙) 상한(원)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """전국 공매 물건을 조건검색한다. 캐시 우선, 비면 온비드 동기화 후 재조회.

    각 물건에 est_win(예상 낙찰가 범위·신뢰도·가정)을 포함하며, data_source로
    실연동/mock 여부를 정직 표기한다.
    """
    return await service.search(
        region=region, kind=kind, min_fail=min_fail, max_price=max_price,
        est_win_max=est_win_max, page=page, page_size=page_size,
        service_key=_onbid_service_key(),
    )


@router.get("/ranking", summary="③ 전국 최저입찰가/할인율 순위")
async def auction_ranking(
    region: Optional[str] = Query(None, description="시/도"),
    kind: Optional[str] = Query(None, description="종류"),
    by: str = Query("min_bid", pattern="^(min_bid|discount_rate)$"),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """전국 최저입찰가(by=min_bid) 또는 할인율(by=discount_rate) 순위."""
    return await service.ranking(region=region, kind=kind, by=by, limit=limit)


@router.get("/my", summary="① 내 관리토지 중 경공매 연동분(프로젝트별+통합)")
async def auction_my(
    group_by: str = Query("project", pattern="^(project|none)$"),
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """내 프로젝트/토지조서 PNU와 일치하는 공매 물건을 자동매칭해 반환한다."""
    return await service.my_listings(
        user_id=str(current_user.user_id),
        tenant_id=str(current_user.tenant_id),
        group_by=group_by,
    )


@router.get("/filters", summary="저장조건 목록")
async def auction_list_filters(
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    items = await service.list_filters(user_id=str(current_user.user_id))
    return {"items": items, "total": len(items)}


@router.post("/filters", summary="저장조건 생성")
async def auction_create_filter(
    name: str = Body(..., embed=True),
    conditions: dict[str, Any] = Body(default_factory=dict, embed=True),
    notify: bool = Body(False, embed=True),
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    return await service.create_filter(
        user_id=str(current_user.user_id), name=name,
        conditions=conditions, notify=notify,
    )


@router.delete("/filters/{filter_id}", summary="저장조건 삭제")
async def auction_delete_filter(
    filter_id: int,
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    ok = await service.delete_filter(user_id=str(current_user.user_id), filter_id=filter_id)
    if not ok:
        raise HTTPException(status_code=404, detail="저장조건을 찾을 수 없습니다.")
    return {"status": "deleted", "id": filter_id}


@router.post("/sync", summary="온비드 공매 동기화(관리/cron)")
async def auction_sync(
    region: Optional[str] = Query(None, description="시/도(미지정=전국 배치)"),
    kind: Optional[str] = Query(None, description="종류"),
    rows: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(RequirePermission("auction", "write")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    """온비드 공매 목록을 수집해 auction_items에 멱등 upsert한다(키 없으면 mock)."""
    return await service.sync_region(
        service_key=_onbid_service_key(), region=region, kind=kind, rows=rows,
    )


@router.get("/items/{item_id}", summary="공매 물건 상세(+권리/감정 raw +낙찰가능가)")
async def auction_item_detail(
    item_id: int,
    current_user: CurrentUser = Depends(RequirePermission("auction", "read")),
    service=Depends(_step1_service),
) -> dict[str, Any]:
    item = await service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="물건을 찾을 수 없습니다.")
    return item
