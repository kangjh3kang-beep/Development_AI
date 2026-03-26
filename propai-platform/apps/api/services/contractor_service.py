"""Contractor network service for G95."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_g_operations import Contractor


class ContractorService:
    """Persist contractor records and produce deterministic recommendations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _score_candidate(
        *,
        category: str,
        required_specialties: list[str],
        region_hint: str | None,
        contractor: Contractor,
    ) -> tuple[float, list[str]]:
        score = 45.0
        reasons: list[str] = []

        contractor_specialties = [
            str(item).lower() for item in (contractor.specialties_json or []) if item
        ]
        required = [item.lower() for item in required_specialties if item]
        overlap = sorted(set(contractor_specialties) & set(required))

        if contractor.category == category:
            score += 20
            reasons.append("category aligned")
        elif contractor.category == "general_contractor":
            score += 8
            reasons.append("general contractor fallback")

        if overlap:
            score += min(len(overlap) * 10, 25)
            reasons.append(f"specialty overlap: {', '.join(overlap)}")

        if region_hint and contractor.address and region_hint.lower() in contractor.address.lower():
            score += 10
            reasons.append("regional coverage matched")

        if contractor.rating is not None:
            score += contractor.rating * 4
            if contractor.rating >= 4.0:
                reasons.append("strong rating")

        return round(max(0.0, min(score, 100.0)), 2), reasons

    async def upsert_contractor(
        self,
        *,
        tenant_id: UUID,
        company_name: str,
        business_number: str,
        category: str,
        specialties: list[str],
        contact_name: str | None,
        contact_phone: str | None,
        contact_email: str | None,
        address: str | None,
        rating: float | None,
        notes: str | None,
    ) -> Contractor:
        contractor = await self.db.scalar(
            select(Contractor).where(
                Contractor.tenant_id == tenant_id,
                Contractor.business_number == business_number,
            )
        )
        if contractor is None:
            contractor = Contractor(
                tenant_id=tenant_id,
                company_name=company_name,
                business_number=business_number,
                category=category,
                specialties_json=specialties,
                contact_name=contact_name,
                contact_phone=contact_phone,
                contact_email=contact_email,
                address=address,
                rating=rating,
                notes=notes,
            )
            self.db.add(contractor)
        else:
            contractor.company_name = company_name
            contractor.category = category
            contractor.specialties_json = specialties
            contractor.contact_name = contact_name
            contractor.contact_phone = contact_phone
            contractor.contact_email = contact_email
            contractor.address = address
            contractor.rating = rating
            contractor.notes = notes
            contractor.is_active = True

        await self.db.commit()
        await self.db.refresh(contractor)
        return contractor

    async def list_active(
        self,
        *,
        tenant_id: UUID,
        category: str | None,
        limit: int,
    ) -> list[Contractor]:
        stmt = select(Contractor).where(
            Contractor.tenant_id == tenant_id,
            Contractor.is_active.is_(True),
        )
        if category:
            stmt = stmt.where(Contractor.category == category)
        result = await self.db.execute(stmt.order_by(Contractor.created_at.desc()))
        contractors = list(result.scalars().all())
        contractors.sort(key=lambda item: float(item.rating or 0.0), reverse=True)
        return contractors[:limit]

    async def recommend(
        self,
        *,
        tenant_id: UUID,
        category: str,
        required_specialties: list[str],
        region_hint: str | None,
        max_results: int,
    ) -> list[dict]:
        contractors = await self.list_active(
            tenant_id=tenant_id,
            category=None,
            limit=max(max_results * 4, 20),
        )
        scored: list[dict] = []
        for contractor in contractors:
            score, reasons = self._score_candidate(
                category=category,
                required_specialties=required_specialties,
                region_hint=region_hint,
                contractor=contractor,
            )
            if score <= 0:
                continue
            scored.append(
                {
                    "contractor": contractor,
                    "match_score": score,
                    "reasons": reasons or ["baseline fit"],
                }
            )

        scored.sort(key=lambda item: item["match_score"], reverse=True)
        return scored[:max_results]
