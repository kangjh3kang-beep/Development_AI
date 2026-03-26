"""Auction intelligence service for G95."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_g_operations import AuctionListing


class AuctionService:
    """Persist and score auction opportunities deterministically."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _analysis_snapshot(
        *,
        appraised_value_krw: float,
        minimum_bid_krw: float,
        bid_count: int,
        occupancy_status: str,
        senior_lien_exists: bool,
        expected_repair_cost_krw: float,
        nearby_market_price_krw: float | None,
    ) -> dict:
        market_value = nearby_market_price_krw or appraised_value_krw
        discount_ratio = round(max(0.0, 1 - (minimum_bid_krw / appraised_value_krw)), 4)
        market_gap_ratio = round(max(0.0, 1 - (minimum_bid_krw / market_value)), 4)
        repair_ratio = expected_repair_cost_krw / appraised_value_krw if appraised_value_krw else 0.0

        score = 58.0
        score += discount_ratio * 32
        score += market_gap_ratio * 18
        score -= min(bid_count, 6) * 2.5
        score -= min(repair_ratio * 100, 15)
        if senior_lien_exists:
            score -= 15
        if occupancy_status == "vacant":
            score += 5
        elif occupancy_status in {"occupied", "tenant"}:
            score -= 10
        elif occupancy_status == "unknown":
            score -= 3
        investment_score = round(max(0.0, min(score, 100.0)), 2)

        recommended_max_bid_krw = max(
            minimum_bid_krw,
            round(min(appraised_value_krw * 0.93, market_value * 0.9) - expected_repair_cost_krw, 2),
        )
        expected_margin_krw = round(
            max(0.0, market_value - recommended_max_bid_krw - expected_repair_cost_krw),
            2,
        )

        diligence_flags: list[str] = []
        if senior_lien_exists:
            diligence_flags.append("review senior lien exposure")
        if occupancy_status in {"occupied", "tenant", "unknown"}:
            diligence_flags.append("confirm vacancy and handover timing")
        if expected_repair_cost_krw > appraised_value_krw * 0.05:
            diligence_flags.append("validate repair capex before bid")
        if bid_count >= 3:
            diligence_flags.append("competition is elevated")
        if not diligence_flags:
            diligence_flags.append("standard legal and title diligence")

        return {
            "discount_ratio": discount_ratio,
            "market_gap_ratio": market_gap_ratio,
            "investment_score": investment_score,
            "recommended_max_bid_krw": recommended_max_bid_krw,
            "expected_margin_krw": expected_margin_krw,
            "diligence_flags": diligence_flags,
            "occupancy_status": occupancy_status,
            "senior_lien_exists": senior_lien_exists,
            "expected_repair_cost_krw": expected_repair_cost_krw,
            "nearby_market_price_krw": market_value,
        }

    async def analyze_and_store(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID | None,
        auction_type: str,
        case_number: str,
        court_name: str,
        address: str,
        property_type: str,
        appraised_value_krw: float,
        minimum_bid_krw: float,
        bid_count: int,
        auction_date,
        occupancy_status: str,
        senior_lien_exists: bool,
        expected_repair_cost_krw: float,
        nearby_market_price_krw: float | None,
    ) -> AuctionListing:
        analysis_json = self._analysis_snapshot(
            appraised_value_krw=appraised_value_krw,
            minimum_bid_krw=minimum_bid_krw,
            bid_count=bid_count,
            occupancy_status=occupancy_status,
            senior_lien_exists=senior_lien_exists,
            expected_repair_cost_krw=expected_repair_cost_krw,
            nearby_market_price_krw=nearby_market_price_krw,
        )

        listing = await self.db.scalar(
            select(AuctionListing).where(
                AuctionListing.tenant_id == tenant_id,
                AuctionListing.case_number == case_number,
            )
        )
        if listing is None:
            listing = AuctionListing(
                tenant_id=tenant_id,
                project_id=project_id,
                auction_type=auction_type,
                case_number=case_number,
                court_name=court_name,
                address=address,
                property_type=property_type,
                appraised_value_krw=appraised_value_krw,
                minimum_bid_krw=minimum_bid_krw,
                bid_count=bid_count,
                auction_date=auction_date,
                status="scheduled",
                analysis_json=analysis_json,
            )
            self.db.add(listing)
        else:
            listing.project_id = project_id
            listing.auction_type = auction_type
            listing.court_name = court_name
            listing.address = address
            listing.property_type = property_type
            listing.appraised_value_krw = appraised_value_krw
            listing.minimum_bid_krw = minimum_bid_krw
            listing.bid_count = bid_count
            listing.auction_date = auction_date
            listing.analysis_json = analysis_json

        await self.db.commit()
        await self.db.refresh(listing)
        return listing

    async def get_listing(self, *, tenant_id: UUID, listing_id: UUID) -> AuctionListing | None:
        return await self.db.scalar(
            select(AuctionListing).where(
                AuctionListing.id == listing_id,
                AuctionListing.tenant_id == tenant_id,
            )
        )

    async def list_opportunities(
        self,
        *,
        tenant_id: UUID,
        limit: int,
        project_id: UUID | None,
    ) -> list[AuctionListing]:
        stmt = select(AuctionListing).where(AuctionListing.tenant_id == tenant_id)
        if project_id is not None:
            stmt = stmt.where(AuctionListing.project_id == project_id)
        result = await self.db.execute(stmt.order_by(AuctionListing.created_at.desc()))
        listings = [
            listing
            for listing in result.scalars().all()
            if listing.status not in {"cancelled", "sold"}
        ]
        listings.sort(
            key=lambda item: float((item.analysis_json or {}).get("investment_score", 0.0)),
            reverse=True,
        )
        return listings[:limit]
