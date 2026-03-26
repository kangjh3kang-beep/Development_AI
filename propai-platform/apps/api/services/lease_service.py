"""Lease abstraction and IFRS16 schedule service."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_e_lease import LeaseAbstraction, LeaseIFRS16Schedule


class LeaseService:
    """Create lease abstractions and IFRS16 schedules."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _lease_term_months(start_date: datetime, end_date: datetime) -> int:
        days = max(1, (end_date - start_date).days)
        return max(1, round(days / 30.4375))

    @staticmethod
    def _build_payment_schedule(
        monthly_rent_krw: float,
        lease_term_months: int,
        annual_discount_rate: float,
    ) -> tuple[list[dict], float]:
        monthly_rate = annual_discount_rate / 12
        discounted_payments = [
            monthly_rent_krw / ((1 + monthly_rate) ** month)
            for month in range(1, lease_term_months + 1)
        ]
        opening_liability = round(sum(discounted_payments), 2)
        remaining_liability = opening_liability
        schedule: list[dict] = []

        for period in range(1, lease_term_months + 1):
            interest = round(remaining_liability * monthly_rate, 2)
            principal = round(max(0.0, monthly_rent_krw - interest), 2)
            closing_liability = round(max(0.0, remaining_liability + interest - monthly_rent_krw), 2)
            schedule.append(
                {
                    "period": period,
                    "payment_krw": round(monthly_rent_krw, 2),
                    "interest_krw": interest,
                    "principal_krw": principal,
                    "opening_liability_krw": round(remaining_liability, 2),
                    "closing_liability_krw": closing_liability,
                }
            )
            remaining_liability = closing_liability

        return schedule, opening_liability

    async def analyze(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        source_document_name: str,
        tenant_name: str,
        lease_type: str,
        area_sqm: float,
        deposit_krw: float,
        monthly_rent_krw: float,
        start_date: datetime,
        end_date: datetime,
        discount_rate: float,
        critical_terms: list[dict],
        abstraction_text: str | None,
    ) -> tuple[LeaseAbstraction, LeaseIFRS16Schedule]:
        lease_term_months = self._lease_term_months(start_date, end_date)
        payment_schedule, lease_liability_krw = self._build_payment_schedule(
            monthly_rent_krw=monthly_rent_krw,
            lease_term_months=lease_term_months,
            annual_discount_rate=discount_rate,
        )

        abstraction = LeaseAbstraction(
            tenant_id=tenant_id,
            project_id=project_id,
            source_document_name=source_document_name,
            tenant_name=tenant_name,
            lease_type=lease_type,
            area_sqm=area_sqm,
            deposit_krw=deposit_krw,
            monthly_rent_krw=monthly_rent_krw,
            start_date=start_date,
            end_date=end_date,
            critical_terms_json=critical_terms,
            abstraction_text=abstraction_text
            or f"Lease for {tenant_name}: {lease_type}, {lease_term_months} months, KRW {monthly_rent_krw:,.0f}/month.",
        )
        self.db.add(abstraction)
        await self.db.flush()

        schedule = LeaseIFRS16Schedule(
            tenant_id=tenant_id,
            project_id=project_id,
            lease_abstraction_id=abstraction.id,
            discount_rate=discount_rate,
            lease_term_months=lease_term_months,
            rou_asset_krw=round(lease_liability_krw, 2),
            lease_liability_krw=round(lease_liability_krw, 2),
            payment_schedule_json=payment_schedule,
            notes="IFRS16 present value schedule generated from fixed monthly rent assumptions.",
        )
        self.db.add(schedule)

        await self.db.commit()
        await self.db.refresh(abstraction)
        await self.db.refresh(schedule)
        return abstraction, schedule
