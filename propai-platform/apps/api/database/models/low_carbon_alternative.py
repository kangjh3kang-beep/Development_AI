"""저탄소 대체자재 모델."""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class LowCarbonAlternative(Base, TenantMixin, TimestampMixin):
    """저탄소 대체자재 테이블.

    기존 건축 자재 대비 GWP(지구온난화지수)가 낮은 대체자재를 기록한다.
    탄소 저감률, 비용 변동률, 가용성 정보를 관리하며,
    친환경 설계 의사결정을 지원한다.
    """

    __tablename__ = "low_carbon_alternatives"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    original_material: Mapped[str] = mapped_column(String(200), nullable=False)
    alternative_material: Mapped[str] = mapped_column(String(200), nullable=False)
    original_gwp: Mapped[float] = mapped_column(Float, nullable=False)
    alternative_gwp: Mapped[float] = mapped_column(Float, nullable=False)
    reduction_pct: Mapped[float] = mapped_column(Float, nullable=False)
    cost_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    availability: Mapped[str] = mapped_column(
        String(50), nullable=False, default="available",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
