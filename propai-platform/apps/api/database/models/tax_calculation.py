"""세금 계산 모델.

취득세, 재산세, 양도세 등 부동산 관련 세금 계산 결과를 저장한다.
절세 시나리오도 함께 기록한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class TaxCalculation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "tax_calculations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    tax_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="acquisition | property | transfer | comprehensive_real_estate | registration | inheritance | gift"
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False, comment="세액 (원)")
    taxable_value: Mapped[float] = mapped_column(Float, nullable=False, comment="과세표준")
    tax_rate: Mapped[float] = mapped_column(Float, nullable=False, comment="세율")
    deductions: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="공제 항목 목록"
    )
    optimization_tips: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="절세 팁 목록"
    )
    scenario_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    calculation_basis: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="계산 근거"
    )

    # 관계
    project = relationship("Project", back_populates="tax_calculations")
