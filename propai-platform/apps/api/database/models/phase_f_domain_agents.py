"""Part F domain agent orchestration models."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class DomainAgentTask(Base, TenantMixin, TimestampMixin):
    __tablename__ = "domain_agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    task_type: Mapped[str] = mapped_column(String(40), nullable=False, default="analysis")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed")
    confidence_score: Mapped[float] = mapped_column(nullable=False)
    requires_approval: Mapped[bool] = mapped_column(nullable=False, default=False)
    input_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendation: Mapped[str] = mapped_column(String(80), nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)


class DomainAgentApproval(Base, TenantMixin, TimestampMixin):
    __tablename__ = "domain_agent_approvals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("domain_agent_tasks.id"), nullable=False, index=True
    )
    approver_role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(nullable=True)
