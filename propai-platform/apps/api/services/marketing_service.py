"""Marketing and OM generation service."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_f_marketing import MarketingContent, OfferingMemorandum


class MarketingService:
    """Generate deterministic marketing and offering memorandum outputs."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _headline(project_name: str, asset_type: str, channel: str) -> str:
        return f"{project_name} | {asset_type} {channel} campaign"

    @staticmethod
    def _body(
        *,
        project_name: str,
        asset_type: str,
        target_audience: str,
        tone: str,
        highlights: list[str],
    ) -> str:
        highlights_text = ", ".join(highlights[:4]) if highlights else "prime location and execution readiness"
        return (
            f"{project_name} is positioned as a {tone} {asset_type} opportunity for {target_audience}. "
            f"Core highlights: {highlights_text}. "
            "The message focuses on demand depth, execution discipline, and risk-adjusted upside."
        )

    async def generate_content(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        project_name: str,
        channel: str,
        asset_type: str,
        target_audience: str,
        tone: str,
        highlights: list[str],
    ) -> MarketingContent:
        content = MarketingContent(
            tenant_id=tenant_id,
            project_id=project_id,
            channel=channel,
            project_name=project_name,
            asset_type=asset_type,
            target_audience=target_audience,
            tone=tone,
            headline=self._headline(project_name, asset_type, channel),
            body=self._body(
                project_name=project_name,
                asset_type=asset_type,
                target_audience=target_audience,
                tone=tone,
                highlights=highlights,
            ),
            call_to_action=f"Request the full investment package for {project_name}.",
            metadata_json={"highlights": highlights},
        )
        self.db.add(content)
        await self.db.commit()
        await self.db.refresh(content)
        return content

    async def generate_om_report(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        project_name: str,
        asset_type: str,
        investment_highlights: list[str],
        target_audience: str,
        risk_factors: list[str],
        output_format: str,
    ) -> OfferingMemorandum:
        sections = [
            {
                "section": "investment-thesis",
                "content": (
                    f"{project_name} targets {target_audience} capital "
                    f"with a focus on {asset_type} positioning."
                ),
            },
            {
                "section": "market-positioning",
                "content": "Demand depth, competitive differentiation, and execution sequencing are emphasized.",
            },
            {
                "section": "capital-structure",
                "content": "Recommended capital mix should preserve downside resilience and sponsor flexibility.",
            },
        ]
        memorandum = OfferingMemorandum(
            tenant_id=tenant_id,
            project_id=project_id,
            version="v1",
            title=f"{project_name} Offering Memorandum",
            executive_summary=(
                f"{project_name} presents a {asset_type} investment thesis for {target_audience}. "
                f"Key highlights: {', '.join(investment_highlights[:4]) or 'institutional-grade positioning'}."
            ),
            sections_json=sections,
            risk_factors_json=risk_factors or ["execution risk", "leasing risk", "capital markets timing"],
            output_format=output_format,
            generated_by="marketing-service",
        )
        self.db.add(memorandum)
        await self.db.commit()
        await self.db.refresh(memorandum)
        return memorandum
