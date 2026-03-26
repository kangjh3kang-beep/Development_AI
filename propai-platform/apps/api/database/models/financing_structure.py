"""자금조달 구조 모델."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class FinancingStructure(Base, TenantMixin, TimestampMixin):
    """자금조달 구조 테이블.

    프로젝트의 자기자본/타인자본/메자닌 비율 및
    대출 조건(금리, 기간)을 관리한다.
    """

    __tablename__ = "financing_structures"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    structure_name: Mapped[str] = mapped_column(String(100), nullable=False)
    equity_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, comment="자기자본 비율",
    )
    debt_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, comment="타인자본 비율",
    )
    mezzanine_ratio: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="메자닌 비율",
    )
    equity_amount_krw: Mapped[float] = mapped_column(Float, nullable=False)
    debt_amount_krw: Mapped[float] = mapped_column(Float, nullable=False)
    mezzanine_amount_krw: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    interest_rate: Mapped[float] = mapped_column(
        Float, nullable=False, comment="대출 금리",
    )
    loan_term_months: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="대출 기간 (월)",
    )
    lender_info_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
