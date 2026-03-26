"""Energy persistence service for KEPCO and certifications."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_g_energy import (
    EnergyCertificationRecord,
    EnergyCertScore,
    KepcoRateCache,
)
from apps.api.services.construction_ai_service import ConstructionAIService

_DEFAULT_ENERGY_RATES_KRW: dict[str, float] = {
    "general": 132.4,
    "industrial": 119.2,
    "education": 108.1,
}

_DEFAULT_BASE_CHARGE_PER_KW: dict[str, float] = {
    "general": 8320.0,
    "industrial": 7210.0,
    "education": 6570.0,
}


class EnergyService:
    """Persist KEPCO tariff cache and certification records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.construction_service = ConstructionAIService(db)

    @staticmethod
    def energy_grade(demand_per_sqm: float) -> str:
        if demand_per_sqm <= 60:
            return "A+"
        if demand_per_sqm <= 90:
            return "A"
        if demand_per_sqm <= 130:
            return "B"
        if demand_per_sqm <= 170:
            return "C"
        return "D"

    async def _get_or_create_rate(
        self,
        *,
        tenant_id: UUID,
        contract_type: str,
    ) -> KepcoRateCache:
        normalized = contract_type if contract_type in _DEFAULT_ENERGY_RATES_KRW else "general"
        existing = await self.db.scalar(
            select(KepcoRateCache).where(
                KepcoRateCache.tenant_id == tenant_id,
                KepcoRateCache.contract_type == normalized,
            )
        )
        if existing is not None:
            return existing

        existing = KepcoRateCache(
            tenant_id=tenant_id,
            contract_type=normalized,
            energy_rate_krw_per_kwh=_DEFAULT_ENERGY_RATES_KRW[normalized],
            base_charge_krw_per_kw=_DEFAULT_BASE_CHARGE_PER_KW[normalized],
            fuel_adjustment_krw_per_kwh=5.0,
            metadata_json={"source": "seeded-default"},
        )
        self.db.add(existing)
        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    async def calculate_kepco_bill(
        self,
        *,
        tenant_id: UUID,
        usage_kwh: float,
        contract_type: str,
        demand_kw: float,
    ) -> dict[str, float | str]:
        rate = await self._get_or_create_rate(tenant_id=tenant_id, contract_type=contract_type)

        base_charge_krw = demand_kw * rate.base_charge_krw_per_kw
        energy_charge_krw = usage_kwh * rate.energy_rate_krw_per_kwh
        fuel_adjustment_krw = usage_kwh * rate.fuel_adjustment_krw_per_kwh
        climate_fund_krw = energy_charge_krw * 0.037
        subtotal = base_charge_krw + energy_charge_krw + fuel_adjustment_krw + climate_fund_krw
        vat_krw = subtotal * 0.1
        total_bill_krw = subtotal + vat_krw

        return {
            "contract_type": rate.contract_type,
            "usage_kwh": usage_kwh,
            "demand_kw": demand_kw,
            "base_charge_krw": round(base_charge_krw, 2),
            "energy_charge_krw": round(energy_charge_krw, 2),
            "climate_fund_krw": round(climate_fund_krw, 2),
            "fuel_adjustment_krw": round(fuel_adjustment_krw, 2),
            "vat_krw": round(vat_krw, 2),
            "total_bill_krw": round(total_bill_krw, 2),
        }

    async def certify_energy(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        total_area_sqm: float,
        floors: int,
        window_wall_ratio: float,
        insulation_grade: str,
        bems_saving_rate: float,
    ) -> EnergyCertificationRecord:
        zeb_result = self.construction_service.estimate_zeb_energy(
            total_area_sqm=total_area_sqm,
            floors=floors,
            window_wall_ratio=window_wall_ratio,
            insulation_grade=insulation_grade,
        )

        raw_demand = float(zeb_result["annual_energy_demand_kwh"])
        bems_saving_kwh = raw_demand * bems_saving_rate
        adjusted_demand = raw_demand - bems_saving_kwh
        recommendations = list(zeb_result["recommendations"])
        if bems_saving_rate < 0.05:
            recommendations.append("Add a BEMS control strategy to improve runtime savings.")

        record = EnergyCertificationRecord(
            tenant_id=tenant_id,
            project_id=project_id,
            energy_grade=self.energy_grade(adjusted_demand / total_area_sqm),
            zeb_grade=str(zeb_result["zeb_grade"]),
            annual_energy_demand_kwh=round(adjusted_demand, 1),
            annual_renewable_generation_kwh=float(zeb_result["annual_renewable_generation_kwh"]),
            energy_independence_rate=float(zeb_result["energy_independence_rate"]),
            bems_saving_rate=bems_saving_rate,
            bems_saving_kwh=round(bems_saving_kwh, 1),
            recommendations_json=recommendations,
        )
        self.db.add(record)
        await self.db.flush()

        scores = [
            ("energy-grade-score", {"A+": 100, "A": 90, "B": 80, "C": 70, "D": 55}[record.energy_grade]),
            ("zeb-independence", record.energy_independence_rate),
            ("bems-saving", record.bems_saving_rate * 100),
        ]
        for score_name, score_value in scores:
            self.db.add(
                EnergyCertScore(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    certification_id=record.id,
                    score_name=score_name,
                    score_value=round(float(score_value), 2),
                    details_json=None,
                )
            )

        await self.db.commit()
        await self.db.refresh(record)
        return record
