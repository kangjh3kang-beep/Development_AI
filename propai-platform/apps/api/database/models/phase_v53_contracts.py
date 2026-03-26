"""v53 contract automation persistence models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class GeneratedContractDraft(Base, TenantMixin, TimestampMixin):
    __tablename__ = "generated_contract_drafts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    esign_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("esign_requests.id"),
        nullable=True,
        index=True,
    )
    contract_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_language: Mapped[str] = mapped_column(String(10), nullable=False, default="ko")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(120), nullable=False)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    contract_amount_krw: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    key_terms_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    clauses_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rendered_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    document_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    sign_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="not_requested"
    )
