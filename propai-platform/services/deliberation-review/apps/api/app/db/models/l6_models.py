"""L6 — ORM 모델(review 스키마). 보고서/항목/권고.

review_report, report_item, recommendation. snapshot/audit 결속.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class ReviewReportModel(Base, CommonMixin):
    __tablename__ = "review_report"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class ReportItemModel(Base, CommonMixin):
    __tablename__ = "report_item"

    report_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    item_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence_grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RecommendationModel(Base, CommonMixin):
    __tablename__ = "recommendation"

    report_item_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    target_variable: Mapped[str | None] = mapped_column(String(128), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    grounded: Mapped[bool] = mapped_column(Boolean, server_default="false")
