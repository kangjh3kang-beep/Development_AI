"""L5 — ORM 모델(review 스키마). 검증결과/주장-근거 링크/정합 로그.

verification_result, claim_evidence_link, reconcile_log. snapshot 결속.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class VerificationResultModel(Base, CommonMixin):
    __tablename__ = "verification_result"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    citation_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    checks: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClaimEvidenceLinkModel(Base, CommonMixin):
    __tablename__ = "claim_evidence_link"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    claim: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    supported: Mapped[bool] = mapped_column(Boolean, server_default="false")


class ReconcileLogModel(Base, CommonMixin):
    __tablename__ = "reconcile_log"

    citation_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    live_reconciled: Mapped[bool] = mapped_column(Boolean, server_default="false")
    mismatch: Mapped[bool] = mapped_column(Boolean, server_default="false")
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
