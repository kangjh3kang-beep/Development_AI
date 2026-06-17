"""R0 — SQLAlchemy 모델(review 스키마). 계약 스키마의 영속화 대응.

7개 테이블: canonical_variable, quantity_ledger, preflight_context, jurisdiction,
regulation_snapshot, audit_record, resolution_parameter. 전부 공통 믹스인(UUID PK·org/proj·ts).
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Float, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class CanonicalVariableModel(Base, CommonMixin):
    __tablename__ = "canonical_variable"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(32))
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    allowed_sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    required_for_rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class QuantityLedgerModel(Base, CommonMixin):
    __tablename__ = "quantity_ledger"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    variable_name: Mapped[str] = mapped_column(String(128))
    value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(128), nullable=True)
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    conflicts: Mapped[list | None] = mapped_column(JSONB, nullable=True)


class PreflightContextModel(Base, CommonMixin):
    __tablename__ = "preflight_context"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pnu: Mapped[str | None] = mapped_column(String(32), nullable=True)
    jurisdiction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    base_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    scale: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    assumed_fields: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class JurisdictionModel(Base, CommonMixin):
    __tablename__ = "jurisdiction"

    pnu: Mapped[str] = mapped_column(String(32))
    sido_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    sigungu_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    zones: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    stricter_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    assumed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class RegulationSnapshotModel(Base, CommonMixin):
    __tablename__ = "regulation_snapshot"

    snapshot_id: Mapped[str] = mapped_column(String(64), unique=True)
    effective_date: Mapped[date] = mapped_column(Date)
    ruleset_version: Mapped[str] = mapped_column(String(64))
    calc_rule_version: Mapped[str] = mapped_column(String(64))


class AuditRecordModel(Base, CommonMixin):
    __tablename__ = "audit_record"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    layer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ResolutionParameterModel(Base, CommonMixin):
    __tablename__ = "resolution_parameter"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[float] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
