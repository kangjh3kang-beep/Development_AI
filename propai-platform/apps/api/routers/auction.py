"""Auction intelligence router for G95."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.schemas.models import AuctionAnalysisRequest, AuctionListingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.auction_service import AuctionService

router = APIRouter()


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
