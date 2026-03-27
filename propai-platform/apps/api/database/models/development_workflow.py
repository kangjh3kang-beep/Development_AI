"""개발 워크플로 모델."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class DevelopmentWorkflow(Base, TenantMixin, TimestampMixin):
    """개발 워크플로 테이블.

    부동산 개발 프로젝트의 진행 단계를 추적한다.
    토지매입→설계→인허가→시공→분양→준공→입주 등의 단계를 관리하며,
    현재 단계, 담당자, 상태 정보를 기록한다.
    """

    __tablename__ = "development_workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    workflow_name: Mapped[str] = mapped_column(String(200), nullable=False)
    current_stage: Mapped[str] = mapped_column(
        String(100), nullable=False, default="init",
    )
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stages_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
