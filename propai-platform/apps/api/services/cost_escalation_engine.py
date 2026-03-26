"""PPI-based construction cost escalation engine for v53."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.cost_escalation_snapshot import CostEscalationSnapshot
from apps.api.database.models.project import Project
from apps.api.services.kcci_material_price_service import KCCIMaterialPriceService

_DEFAULT_MATERIAL_CODES = [
    "ready_mix_concrete",
    "rebar_sd400_d13",
    "h_beam_steel",
    "glass_lowe_panel",
]
_PPI_INDEX_BY_YEAR: dict[int, float] = {
    2020: 92.4,
    2021: 96.8,
    2022: 101.9,
    2023: 105.1,
    2024: 109.6,
    2025: 113.8,
    2026: 117.2,
    2027: 120.1,
    2028: 123.4,
    2029: 126.7,
    2030: 130.1,
}


class CostEscalationEngine:
    """Analyze project-level construction cost escalation using simulated PPI data."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()
        self.material_service = KCCIMaterialPriceService(db)

    @staticmethod
    def _ppi_index(year: int) -> float:
        if year in _PPI_INDEX_BY_YEAR:
            return _PPI_INDEX_BY_YEAR[year]

        latest_known_year = max(_PPI_INDEX_BY_YEAR)
        latest_known_index = _PPI_INDEX_BY_YEAR[latest_known_year]
        if year > latest_known_year:
            growth_years = year - latest_known_year
            return round(latest_known_index * ((1.027) ** growth_years), 2)

        earliest_year = min(_PPI_INDEX_BY_YEAR)
        earliest_index = _PPI_INDEX_BY_YEAR[earliest_year]
        decline_years = earliest_year - year
        return round(earliest_index / ((1.022) ** decline_years), 2)

    @staticmethod
    def _normalize_shares(
        *,
        material_share_ratio: float,
        labor_share_ratio: float,
        overhead_share_ratio: float,
    ) -> tuple[float, float, float]:
        total = material_share_ratio + labor_share_ratio + overhead_share_ratio
        if total <= 0:
            raise ValueError("At least one cost share must be greater than zero")
        return (
            round(material_share_ratio / total, 4),
            round(labor_share_ratio / total, 4),
            round(overhead_share_ratio / total, 4),
        )

    @staticmethod
    def _weight_for_material(item: dict) -> float:
        estimated_cost = item.get("estimated_project_cost_krw")
        if isinstance(estimated_cost, (int, float)) and estimated_cost > 0:
            return float(estimated_cost)
        material_code = str(item["material_code"])
        default_weights = {
            "ready_mix_concrete": 0.29,
            "rebar_sd400_d13": 0.24,
            "h_beam_steel": 0.18,
            "glass_lowe_panel": 0.15,
            "gypsum_board": 0.14,
        }
        return default_weights.get(material_code, 0.12)

    @staticmethod
    def _build_alerts(
        *,
        overall_escalation_ratio: float,
        material_impacts: list[dict],
    ) -> list[dict]:
        alerts: list[dict] = []
        if overall_escalation_ratio >= 0.15:
            alerts.append(
                {
                    "severity": "critical",
                    "title": "Escalation exceeds contingency planning band",
                    "detail": f"Projected cost growth reached {overall_escalation_ratio:.1%}.",
                }
            )
        elif overall_escalation_ratio >= 0.08:
            alerts.append(
                {
                    "severity": "elevated",
                    "title": "Escalation pressure is above the baseline budget band",
                    "detail": f"Projected cost growth reached {overall_escalation_ratio:.1%}.",
                }
            )

        for item in material_impacts:
            if item["delta_ratio"] >= 0.18:
                alerts.append(
                    {
                        "severity": "elevated",
                        "title": f"{item['material_name']} requires procurement review",
                        "detail": f"Material delta reached {item['delta_ratio']:.1%}.",
                    }
                )
        return alerts

    async def analyze(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        base_construction_cost_krw: float,
        baseline_year: int,
        target_year: int,
        construction_duration_months: int,
        material_share_ratio: float,
        labor_share_ratio: float,
        overhead_share_ratio: float,
        contingency_ratio: float,
        material_codes: list[str] | None,
        region_code: str = "KR",
    ) -> dict:
        if target_year < baseline_year:
            raise ValueError("target_year must be greater than or equal to baseline_year")

        project = await self.db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        if project is None:
            raise ValueError("Project not found")

        material_share_ratio, labor_share_ratio, overhead_share_ratio = self._normalize_shares(
            material_share_ratio=material_share_ratio,
            labor_share_ratio=labor_share_ratio,
            overhead_share_ratio=overhead_share_ratio,
        )

        material_snapshot = await self.material_service.get_latest_snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            material_codes=material_codes or _DEFAULT_MATERIAL_CODES,
            region_code=region_code,
        )
        material_items = material_snapshot["items"]
        raw_weights = [self._weight_for_material(item) for item in material_items]
        total_weight = sum(raw_weights) or 1.0

        material_impacts: list[dict] = []
        material_delta_ratio = 0.0
        for item, raw_weight in zip(material_items, raw_weights, strict=False):
            weight_ratio = round(raw_weight / total_weight, 4)
            delta_ratio = round((float(item["latest_price_index"]) / 100) - 1, 4)
            cost_impact_krw = round(
                base_construction_cost_krw
                * material_share_ratio
                * weight_ratio
                * max(delta_ratio, 0),
                2,
            )
            material_delta_ratio += weight_ratio * max(delta_ratio, 0)
            material_impacts.append(
                {
                    "material_code": item["material_code"],
                    "material_name": item["material_name"],
                    "weight_ratio": weight_ratio,
                    "baseline_unit_price_krw": round(
                        float(item["current_unit_price_krw"]) / max(1.0, float(item["latest_price_index"]) / 100),
                        2,
                    ),
                    "latest_unit_price_krw": item["current_unit_price_krw"],
                    "delta_ratio": delta_ratio,
                    "cost_impact_krw": cost_impact_krw,
                }
            )

        baseline_ppi = self._ppi_index(baseline_year)
        yearly_projection: list[dict] = []
        duration_adjustment = 1 + max(0, construction_duration_months - 12) / 96
        ppi_weight_multiplier = (
            material_share_ratio
            + labor_share_ratio * 0.72
            + overhead_share_ratio * 0.38
        )

        for year in range(baseline_year, target_year + 1):
            ppi_index = self._ppi_index(year)
            ppi_ratio = max(0.0, round((ppi_index / baseline_ppi) - 1, 4))
            weighted_ratio = round(
                (ppi_ratio * ppi_weight_multiplier + material_delta_ratio * material_share_ratio)
                * duration_adjustment,
                4,
            )
            projected_cost = round(base_construction_cost_krw * (1 + weighted_ratio), 2)
            yearly_projection.append(
                {
                    "year": year,
                    "ppi_index": ppi_index,
                    "escalation_ratio": weighted_ratio,
                    "projected_cost_krw": projected_cost,
                }
            )

        adjusted_core_cost = yearly_projection[-1]["projected_cost_krw"]
        contingency_amount_krw = round(adjusted_core_cost * contingency_ratio, 2)
        adjusted_cost_krw = round(adjusted_core_cost + contingency_amount_krw, 2)
        escalation_amount_krw = round(adjusted_cost_krw - base_construction_cost_krw, 2)
        overall_escalation_ratio = round(
            escalation_amount_krw / base_construction_cost_krw,
            4,
        )
        alerts = self._build_alerts(
            overall_escalation_ratio=overall_escalation_ratio,
            material_impacts=material_impacts,
        )
        ppi_source = "ecos-live-ready" if self.settings.ecos_api_key else "ecos-simulated"
        summary = (
            f"{project.name} cost projection escalates from {base_construction_cost_krw:,.0f} KRW "
            f"to {adjusted_cost_krw:,.0f} KRW by {target_year}, including {contingency_amount_krw:,.0f} KRW contingency."
        )

        snapshot = CostEscalationSnapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            baseline_year=baseline_year,
            target_year=target_year,
            construction_duration_months=construction_duration_months,
            base_construction_cost_krw=round(base_construction_cost_krw, 2),
            adjusted_cost_krw=adjusted_cost_krw,
            escalation_amount_krw=escalation_amount_krw,
            overall_escalation_ratio=overall_escalation_ratio,
            material_share_ratio=material_share_ratio,
            labor_share_ratio=labor_share_ratio,
            overhead_share_ratio=overhead_share_ratio,
            contingency_ratio=contingency_ratio,
            contingency_amount_krw=contingency_amount_krw,
            ppi_source=ppi_source,
            yearly_projection_json=yearly_projection,
            material_impacts_json=material_impacts,
            alerts_json=alerts,
            request_assumptions_json={
                "region_code": region_code,
                "material_codes": [item["material_code"] for item in material_items],
                "project_name": project.name,
            },
            summary=summary,
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return self._to_response(snapshot)

    def _to_response(self, snapshot: CostEscalationSnapshot) -> dict:
        return {
            "id": snapshot.id,
            "project_id": snapshot.project_id,
            "baseline_year": snapshot.baseline_year,
            "target_year": snapshot.target_year,
            "construction_duration_months": snapshot.construction_duration_months,
            "base_construction_cost_krw": snapshot.base_construction_cost_krw,
            "adjusted_cost_krw": snapshot.adjusted_cost_krw,
            "escalation_amount_krw": snapshot.escalation_amount_krw,
            "overall_escalation_ratio": snapshot.overall_escalation_ratio,
            "contingency_ratio": snapshot.contingency_ratio,
            "contingency_amount_krw": snapshot.contingency_amount_krw,
            "ppi_source": snapshot.ppi_source,
            "material_impacts": snapshot.material_impacts_json or [],
            "yearly_projection": snapshot.yearly_projection_json or [],
            "alerts": snapshot.alerts_json or [],
            "summary": snapshot.summary or "",
            "created_at": snapshot.created_at,
        }

    async def get_latest(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        snapshot = await self.db.scalar(
            select(CostEscalationSnapshot)
            .where(
                CostEscalationSnapshot.tenant_id == tenant_id,
                CostEscalationSnapshot.project_id == project_id,
            )
            .order_by(CostEscalationSnapshot.created_at.desc())
            .limit(1)
        )
        if snapshot is None:
            return None
        return self._to_response(snapshot)
