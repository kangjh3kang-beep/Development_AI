"""공사 일지 모델.

시공 현장의 작업 기록, 인력, 장비, 기상 조건 등을 관리한다.
"""

import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class ConstructionLog(Base, TenantMixin, TimestampMixin):
    __tablename__ = "construction_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    weather: Mapped[str | None] = mapped_column(String(50), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    worker_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    work_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_used: Mapped[list | None] = mapped_column(JSON, nullable=True)
    issues: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="현장 이슈 목록"
    )
    progress_pct: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="공정률 (0~100)"
    )

    # 관계
    project = relationship("Project", back_populates="construction_logs")
