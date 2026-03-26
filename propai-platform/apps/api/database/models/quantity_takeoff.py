"""물량산출 모델."""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class QuantityTakeoff(Base, TenantMixin, TimestampMixin):
    """물량산출 테이블.

    BIM/IFC 기반 또는 수동 입력 물량산출 결과를 관리한다.
    자재별 수량, 단가, 합계 금액 및 BIM 요소 참조 정보를 기록한다.
    """

    __tablename__ = "quantity_takeoffs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    item_code: Mapped[str] = mapped_column(String(50), nullable=False)
    item_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(
        String(100), nullable=False, default="general",
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    unit_price_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_price_krw: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    bim_element_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    material_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
