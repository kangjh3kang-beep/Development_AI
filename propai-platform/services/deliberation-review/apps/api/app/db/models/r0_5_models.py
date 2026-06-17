"""R0.5 — ORM 모델(review 스키마). 시트역할 배정 + 의미요소.

sheet_role_assignment, semantic_element. snapshot_id 결속, audit_record 연계(분석 단위).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class SheetRoleAssignmentModel(Base, CommonMixin):
    __tablename__ = "sheet_role_assignment"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sheet_id: Mapped[str] = mapped_column(String(128))
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    isolated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    method: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class SemanticElementModel(Base, CommonMixin):
    __tablename__ = "semantic_element"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    element_id: Mapped[str] = mapped_column(String(128))
    semantic_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    identity_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_sheets: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
