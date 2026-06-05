"""KCCI material price service for v53 cost intelligence."""

from datetime import datetime, timezone
UTC = timezone.utc
from math import sin
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.material_price_history import MaterialPriceHistory
from apps.api.database.models.project import Project
from apps.api.database.models.quantity_takeoff import QuantityTakeoff

# ★시장단가 SSOT(D4 market_unit_price 출처): KCCI 변동모델(성장률·변동성·위상)의 기준값.
#   품셈 표준단가(standard_quantity_estimator.UNIT_PRICES_2026 / material_unit_prices DB)와는
#   별개 도메인(시장 변동 시세). 단가 3중비교에서 market 축으로 사용된다.
_MATERIAL_LIBRARY: dict[str, dict[str, float | str | list[str]]] = {
    "ready_mix_concrete": {
        "name": "Ready-mix concrete 25-240-15",
        "category": "concrete",
        "unit": "m3",
        "base_price_krw": 94500.0,
        "annual_growth_ratio": 0.058,
        "volatility": 0.016,
        "phase": 0.3,
        "default_quantity_per_sqm": 0.42,
        "default_weight_ratio": 0.29,
        "aliases": ["concrete", "ready", "레미콘", "콘크리트"],
    },
    "rebar_sd400_d13": {
        "name": "Rebar SD400 D13",
        "category": "steel",
        "unit": "ton",
        "base_price_krw": 848000.0,
        "annual_growth_ratio": 0.064,
        "volatility": 0.024,
        "phase": 1.1,
        "default_quantity_per_sqm": 0.052,
        "default_weight_ratio": 0.24,
        "aliases": ["rebar", "steel", "철근"],
    },
    "h_beam_steel": {
        "name": "Structural H-beam steel",
        "category": "structural_steel",
        "unit": "ton",
        "base_price_krw": 1395000.0,
        "annual_growth_ratio": 0.071,
        "volatility": 0.028,
        "phase": 2.0,
        "default_quantity_per_sqm": 0.034,
        "default_weight_ratio": 0.18,
        "aliases": ["beam", "h-beam", "구조용강재", "steel frame"],
    },
    "glass_lowe_panel": {
        "name": "Low-E glass panel",
        "category": "facade",
        "unit": "sqm",
        "base_price_krw": 182000.0,
        "annual_growth_ratio": 0.049,
        "volatility": 0.015,
        "phase": 2.8,
        "default_quantity_per_sqm": 0.31,
        "default_weight_ratio": 0.15,
        "aliases": ["glass", "façade", "facade", "유리", "창호"],
    },
    "gypsum_board": {
        "name": "Gypsum board 12.5T",
        "category": "interior",
        "unit": "sheet",
        "base_price_krw": 12300.0,
        "annual_growth_ratio": 0.041,
        "volatility": 0.012,
        "phase": 3.4,
        "default_quantity_per_sqm": 1.4,
        "default_weight_ratio": 0.14,
        "aliases": ["gypsum", "board", "석고보드", "interior"],
    },
}


class KCCIMaterialPriceService:
    """Simulated KCCI-backed material price ingestion and read service."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    @staticmethod
    def _month_anchor(year: int, month: int) -> datetime:
        return datetime(year, month, 1, tzinfo=UTC)

    @staticmethod
    def _resolve_material_codes(material_codes: list[str] | None) -> list[str]:
        if not material_codes:
            return list(_MATERIAL_LIBRARY.keys())

        resolved = [code for code in material_codes if code in _MATERIAL_LIBRARY]
        return resolved or list(_MATERIAL_LIBRARY.keys())

    @staticmethod
    def _months_between(start: datetime, end: datetime) -> int:
        return (end.year - start.year) * 12 + end.month - start.month

    @staticmethod
    def _source_name(kcci_api_key: str) -> str:
        return "kcci-live-ready" if kcci_api_key else "kcci-simulated"

    @staticmethod
    def _calc_material_price(
        base_price: float,
        annual_growth_ratio: float,
        volatility: float,
        phase: float,
        snapshot_at: datetime,
    ) -> float:
        base_anchor = datetime(2024, 1, 1, tzinfo=UTC)
        month_offset = KCCIMaterialPriceService._months_between(base_anchor, snapshot_at)
        growth_multiplier = (1 + annual_growth_ratio) ** (month_offset / 12)
        cyclical_multiplier = 1 + volatility * sin((month_offset + phase) * 0.85)
        return round(base_price * growth_multiplier * cyclical_multiplier, 2)

    @classmethod
    def _calc_unit_price(cls, material_code: str, snapshot_at: datetime) -> dict[str, float]:
        material = _MATERIAL_LIBRARY[material_code]
        base_price = float(material["base_price_krw"])
        annual_growth_ratio = float(material["annual_growth_ratio"])
        volatility = float(material["volatility"])
        phase = float(material["phase"])

        unit_price = cls._calc_material_price(
            base_price=base_price,
            annual_growth_ratio=annual_growth_ratio,
            volatility=volatility,
            phase=phase,
            snapshot_at=snapshot_at,
        )
        price_index = round((unit_price / base_price) * 100, 2)

        previous_month = (
            datetime(snapshot_at.year - 1, 12, 1, tzinfo=UTC)
            if snapshot_at.month == 1
            else datetime(snapshot_at.year, snapshot_at.month - 1, 1, tzinfo=UTC)
        )
        previous_year = datetime(snapshot_at.year - 1, snapshot_at.month, 1, tzinfo=UTC)

        previous_month_price = cls._calc_material_price(
            base_price=base_price,
            annual_growth_ratio=annual_growth_ratio,
            volatility=volatility,
            phase=phase,
            snapshot_at=previous_month,
        )
        previous_year_price = cls._calc_material_price(
            base_price=base_price,
            annual_growth_ratio=annual_growth_ratio,
            volatility=volatility,
            phase=phase,
            snapshot_at=previous_year,
        )

        mom_change_ratio = (
            round((unit_price - previous_month_price) / previous_month_price, 4)
            if previous_month_price > 0
            else 0.0
        )
        yoy_change_ratio = (
            round((unit_price - previous_year_price) / previous_year_price, 4)
            if previous_year_price > 0
            else 0.0
        )

        return {
            "unit_price_krw": unit_price,
            "price_index": price_index,
            "mom_change_ratio": mom_change_ratio,
            "yoy_change_ratio": yoy_change_ratio,
        }

    async def _ensure_history(
        self,
        *,
        tenant_id: UUID,
        material_codes: list[str],
        region_code: str,
        history_months: int = 6,
    ) -> None:
        now = datetime.now(UTC)
        current_anchor = self._month_anchor(now.year, now.month)
        target_anchors: list[datetime] = []
        year = current_anchor.year
        month = current_anchor.month
        for _ in range(history_months):
            target_anchors.append(self._month_anchor(year, month))
            if month == 1:
                year -= 1
                month = 12
            else:
                month -= 1

        earliest_anchor = target_anchors[-1]
        existing_rows = (
            (
                await self.db.execute(
                    select(MaterialPriceHistory).where(
                        MaterialPriceHistory.tenant_id == tenant_id,
                        MaterialPriceHistory.region_code == region_code,
                        MaterialPriceHistory.material_code.in_(material_codes),
                        MaterialPriceHistory.snapshot_at >= earliest_anchor,
                    )
                )
            )
            .scalars()
            .all()
        )
        existing_keys = {
            (row.material_code, row.snapshot_at.year, row.snapshot_at.month)
            for row in existing_rows
        }
        source_name = self._source_name(self.settings.kcci_api_key)

        created = False
        for material_code in material_codes:
            material = _MATERIAL_LIBRARY[material_code]
            for anchor in target_anchors:
                key = (material_code, anchor.year, anchor.month)
                if key in existing_keys:
                    continue

                price = self._calc_unit_price(material_code, anchor)
                self.db.add(
                    MaterialPriceHistory(
                        tenant_id=tenant_id,
                        material_code=material_code,
                        material_name=str(material["name"]),
                        category=str(material["category"]),
                        region_code=region_code,
                        unit=str(material["unit"]),
                        source_name=source_name,
                        snapshot_at=anchor,
                        unit_price_krw=float(price["unit_price_krw"]),
                        price_index=float(price["price_index"]),
                        mom_change_ratio=float(price["mom_change_ratio"]),
                        yoy_change_ratio=float(price["yoy_change_ratio"]),
                        metadata_json={
                            "default_weight_ratio": material["default_weight_ratio"],
                            "default_quantity_per_sqm": material["default_quantity_per_sqm"],
                        },
                    )
                )
                created = True

        if created:
            await self.db.commit()

    @staticmethod
    def _match_material_code(row: QuantityTakeoff) -> str | None:
        haystack = " ".join(
            part.lower()
            for part in [
                row.item_code,
                row.item_name,
                row.category,
                row.material_spec or "",
            ]
            if part
        )
        for material_code, config in _MATERIAL_LIBRARY.items():
            aliases = [str(alias).lower() for alias in config["aliases"]] + [material_code.lower()]
            if any(alias in haystack for alias in aliases):
                return material_code
        return None

    async def _estimate_project_costs(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID | None,
        latest_rows: dict[str, MaterialPriceHistory],
    ) -> dict[str, float | None]:
        estimates: dict[str, float | None] = {
            material_code: None for material_code in latest_rows
        }
        if project_id is None:
            return estimates

        quantity_rows = (
            (
                await self.db.execute(
                    select(QuantityTakeoff).where(
                        QuantityTakeoff.tenant_id == tenant_id,
                        QuantityTakeoff.project_id == project_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if quantity_rows:
            totals: dict[str, float] = {material_code: 0.0 for material_code in latest_rows}
            for row in quantity_rows:
                material_code = self._match_material_code(row)
                if material_code is None or material_code not in latest_rows:
                    continue
                totals[material_code] += round(row.quantity * latest_rows[material_code].unit_price_krw, 2)
            for material_code, amount in totals.items():
                if amount > 0:
                    estimates[material_code] = round(amount, 2)
            return estimates

        project = await self.db.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        if project is None or not project.total_area_sqm:
            return estimates

        area = float(project.total_area_sqm)
        for material_code, row in latest_rows.items():
            config = _MATERIAL_LIBRARY[material_code]
            quantity_per_sqm = float(config["default_quantity_per_sqm"])
            estimates[material_code] = round(area * quantity_per_sqm * row.unit_price_krw, 2)
        return estimates

    async def _build_snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID | None,
        region_code: str,
        material_codes: list[str],
    ) -> dict:
        rows = (
            (
                await self.db.execute(
                    select(MaterialPriceHistory)
                    .where(
                        MaterialPriceHistory.tenant_id == tenant_id,
                        MaterialPriceHistory.region_code == region_code,
                        MaterialPriceHistory.material_code.in_(material_codes),
                    )
                    .order_by(
                        MaterialPriceHistory.material_code.asc(),
                        MaterialPriceHistory.snapshot_at.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )

        grouped: dict[str, list[MaterialPriceHistory]] = {}
        for row in rows:
            grouped.setdefault(row.material_code, []).append(row)

        latest_rows = {material_code: history[0] for material_code, history in grouped.items() if history}
        project_costs = await self._estimate_project_costs(
            tenant_id=tenant_id,
            project_id=project_id,
            latest_rows=latest_rows,
        )

        items: list[dict] = []
        alerts: list[dict] = []
        snapshot_at = None

        for material_code in material_codes:
            history = grouped.get(material_code, [])
            if not history:
                continue
            latest = history[0]
            snapshot_at = latest.snapshot_at if snapshot_at is None else max(snapshot_at, latest.snapshot_at)
            history_points = [
                {
                    "snapshot_at": row.snapshot_at,
                    "unit_price_krw": row.unit_price_krw,
                    "price_index": row.price_index,
                    "mom_change_ratio": row.mom_change_ratio,
                    "source_name": row.source_name,
                }
                for row in reversed(history[:6])
            ]
            severity = "normal"
            if latest.mom_change_ratio >= 0.035 or latest.yoy_change_ratio >= 0.12:
                severity = "elevated"
            if latest.mom_change_ratio >= 0.055 or latest.yoy_change_ratio >= 0.18:
                severity = "critical"

            items.append(
                {
                    "material_code": material_code,
                    "material_name": latest.material_name,
                    "category": latest.category,
                    "unit": latest.unit,
                    "current_unit_price_krw": latest.unit_price_krw,
                    "latest_price_index": latest.price_index,
                    "mom_change_ratio": latest.mom_change_ratio,
                    "yoy_change_ratio": latest.yoy_change_ratio,
                    "estimated_project_cost_krw": project_costs.get(material_code),
                    "alert_level": severity,
                    "history": history_points,
                }
            )

            if severity != "normal":
                alerts.append(
                    {
                        "material_code": material_code,
                        "severity": severity,
                        "title": f"{latest.material_name} price acceleration",
                        "detail": (
                            f"Monthly change {latest.mom_change_ratio:.1%}, "
                            f"year-over-year change {latest.yoy_change_ratio:.1%}."
                        ),
                    }
                )

        return {
            "as_of": snapshot_at or datetime.now(UTC),
            "project_id": project_id,
            "region_code": region_code,
            "items": items,
            "alerts": alerts,
        }

    async def refresh_snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID | None,
        material_codes: list[str] | None,
        region_code: str = "KR",
    ) -> dict:
        resolved_codes = self._resolve_material_codes(material_codes)
        await self._ensure_history(
            tenant_id=tenant_id,
            material_codes=resolved_codes,
            region_code=region_code,
        )
        return await self._build_snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            region_code=region_code,
            material_codes=resolved_codes,
        )

    async def get_latest_snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID | None,
        material_codes: list[str] | None,
        region_code: str = "KR",
    ) -> dict:
        resolved_codes = self._resolve_material_codes(material_codes)
        await self._ensure_history(
            tenant_id=tenant_id,
            material_codes=resolved_codes,
            region_code=region_code,
        )
        return await self._build_snapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            region_code=region_code,
            material_codes=resolved_codes,
        )
