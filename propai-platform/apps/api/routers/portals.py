"""Portal integration router for G92."""

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    PortalBatchPostRequest,
    PortalBatchPostResponse,
    PortalMarketDataResponse,
    PortalPostRequest,
    PortalPostResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.portals_service import PortalsService

router = APIRouter()


def _serialize_listing(listing, performance) -> PortalPostResponse:
    return PortalPostResponse(
        listing_id=listing.id,
        project_id=listing.project_id,
        portal_name=listing.portal_name,
        listing_external_id=listing.listing_external_id,
        listing_url=listing.listing_url,
        status=listing.status,
        view_count=performance.view_count,
        inquiry_count=performance.inquiry_count,
        created_at=listing.created_at,
    )


@router.post("/{portal_id}/post", response_model=PortalPostResponse)
async def post_listing_to_portal(
    portal_id: str,
    body: PortalPostRequest,
    current_user: CurrentUser = Depends(RequirePermission("portals", "write")),
    db: AsyncSession = Depends(get_db),
) -> PortalPostResponse:
    """Post a listing to a specific portal."""
    service = PortalsService(db)
    listing, performance = await service.post_listing(
        tenant_id=current_user.tenant_id,
        portal_name=portal_id,
        project_id=body.project_id,
        project_name=body.project_name,
        region_code=body.region_code,
        property_type=body.property_type,
        price_krw=body.price_krw,
        area_sqm=body.area_sqm,
        title=body.title,
        description=body.description,
        images=body.images,
    )
    return _serialize_listing(listing, performance)


@router.post("/post-all", response_model=PortalBatchPostResponse)
async def post_listing_to_all_portals(
    body: PortalBatchPostRequest,
    current_user: CurrentUser = Depends(RequirePermission("portals", "write")),
    db: AsyncSession = Depends(get_db),
) -> PortalBatchPostResponse:
    """Post a listing to multiple portals."""
    service = PortalsService(db)
    items: list[PortalPostResponse] = []
    portals = body.portals or ["naver", "zigbang", "dabang"]
    for portal_name in portals:
        listing, performance = await service.post_listing(
            tenant_id=current_user.tenant_id,
            portal_name=portal_name,
            project_id=body.project_id,
            project_name=body.project_name,
            region_code=body.region_code,
            property_type=body.property_type,
            price_krw=body.price_krw,
            area_sqm=body.area_sqm,
            title=body.title,
            description=body.description,
            images=body.images,
        )
        items.append(_serialize_listing(listing, performance))

    return PortalBatchPostResponse(items=items, success_count=len(items))


@router.get("/market-data/{region_code}", response_model=PortalMarketDataResponse)
async def get_portal_market_data(
    region_code: str,
    current_user: CurrentUser = Depends(RequirePermission("portals", "read")),
    db: AsyncSession = Depends(get_db),
) -> PortalMarketDataResponse:
    """Return aggregated portal market data for a region."""
    service = PortalsService(db)
    data = await service.market_data(tenant_id=current_user.tenant_id, region_code=region_code)
    return PortalMarketDataResponse(**data)
