"""RE100 이행률 추적 및 K-ETS 배출권 비용 산출 모델.

RE100 이행 경로, 배출량, K-ETS 비용, 조달 수단 비교, 로드맵 등을 저장한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class Re100Tracking(Base, TenantMixin, TimestampMixin):
    """RE100 이행률 추적 레코드."""

    __tablename__ = "re100_trackings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    tracking_year: Mapped[int] = mapped_column(Integer, nullable=False)
    total_electricity_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    renewable_electricity_mwh: Mapped[float] = mapped_column(Float, nullable=False)
    re100_rate: Mapped[float] = mapped_column(Float, nullable=False)
    grid_emission_factor: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.4629
    )
    total_emissions_tco2eq: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_emissions_tco2eq: Mapped[float] = mapped_column(Float, nullable=False)
    excess_emissions_tco2eq: Mapped[float] = mapped_column(Float, nullable=False)
    kts_unit_price_krw: Mapped[int] = mapped_column(
        Integer, nullable=False, default=18000
    )
    kts_total_cost_krw: Mapped[float] = mapped_column(Float, nullable=False)
    procurement_breakdown_json: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )
    roadmap_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
