"""Portal posting and market-data service."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_g_portal import PortalListing, PortalPerformance

_PORTAL_FACTORS = {
    "naver": {"views": 220, "inquiries": 12, "ctr": 0.19, "bookmark": 8, "rank": 4},
    "zigbang": {"views": 180, "inquiries": 9, "ctr": 0.16, "bookmark": 6, "rank": 6},
    "dabang": {"views": 165, "inquiries": 8, "ctr": 0.15, "bookmark": 5, "rank": 8},
    "peterpan": {"views": 120, "inquiries": 5, "ctr": 0.11, "bookmark": 3, "rank": 11},
}


class PortalsService:
    """Manage portal listing posts and aggregate market data."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _portal_defaults(portal_name: str) -> dict[str, float | int]:
        return _PORTAL_FACTORS.get(portal_name, {"views": 140, "inquiries": 6, "ctr": 0.12, "bookmark": 4, "rank": 10})

    async def post_listing(
        self,
        *,
        tenant_id: UUID,
        portal_name: str,
        project_id: UUID,
        project_name: str,
        region_code: str,
        property_type: str,
        price_krw: float,
        area_sqm: float,
        title: str,
        description: str,
        images: list[str],
    ) -> tuple[PortalListing, PortalPerformance]:
        normalized_portal = portal_name.lower()
        external_id = f"{normalized_portal}-{str(project_id)[:8]}-{region_code}"
        listing = PortalListing(
            tenant_id=tenant_id,
            project_id=project_id,
            portal_name=normalized_portal,
            region_code=region_code,
            listing_title=title,
            listing_external_id=external_id,
            listing_url=f"https://{normalized_portal}.example.com/listings/{external_id}",
            status="active",
            property_type=property_type,
            price_krw=price_krw,
            area_sqm=area_sqm,
            description=description,
            images_json=images,
            metadata_json={"project_name": project_name},
        )
        self.db.add(listing)
        await self.db.flush()

        defaults = self._portal_defaults(normalized_portal)
        performance = PortalPerformance(
            tenant_id=tenant_id,
            project_id=project_id,
            listing_id=listing.id,
            view_count=int(defaults["views"]),
            inquiry_count=int(defaults["inquiries"]),
            click_through_rate=float(defaults["ctr"]),
            bookmark_count=int(defaults["bookmark"]),
            ranking_position=int(defaults["rank"]),
            metrics_json={"region_code": region_code},
        )
        self.db.add(performance)
        await self.db.commit()
        await self.db.refresh(listing)
        await self.db.refresh(performance)
        return listing, performance

    async def market_data(self, *, tenant_id: UUID, region_code: str) -> dict:
        summary = (
            await self.db.execute(
                select(
                    func.count(PortalListing.id),
                    func.coalesce(func.avg(PortalListing.price_krw), 0.0),
                    func.coalesce(func.avg(PortalListing.area_sqm), 0.0),
                    func.coalesce(func.avg(PortalPerformance.inquiry_count), 0.0),
                )
                .join(PortalPerformance, PortalPerformance.listing_id == PortalListing.id)
                .where(
                    PortalListing.tenant_id == tenant_id,
                    PortalListing.region_code == region_code,
                    PortalListing.status == "active",
                )
            )
        ).one()

        portal_rows = (
            await self.db.execute(
                select(
                    PortalListing.portal_name,
                    func.count(PortalListing.id),
                    func.coalesce(func.avg(PortalPerformance.inquiry_count), 0.0),
                )
                .join(PortalPerformance, PortalPerformance.listing_id == PortalListing.id)
                .where(
                    PortalListing.tenant_id == tenant_id,
                    PortalListing.region_code == region_code,
                )
                .group_by(PortalListing.portal_name)
                .order_by(func.count(PortalListing.id).desc())
            )
        ).all()

        return {
            "region_code": region_code,
            "active_listing_count": int(summary[0] or 0),
            "average_price_krw": round(float(summary[1] or 0.0), 2),
            "average_area_sqm": round(float(summary[2] or 0.0), 2),
            "average_inquiry_count": round(float(summary[3] or 0.0), 2),
            "top_portals": [
                {
                    "portal_name": portal_name,
                    "listing_count": int(listing_count or 0),
                    "average_inquiry_count": round(float(avg_inquiry or 0.0), 2),
                }
                for portal_name, listing_count, avg_inquiry in portal_rows
            ],
        }
