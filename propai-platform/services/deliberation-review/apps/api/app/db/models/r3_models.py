"""R3 — ORM 모델(review 스키마). 룰/의존엣지/판정/매핑.

rule, rule_edge, finding, mapping_assignment. snapshot 결속, 근거조문 링크.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class RuleModel(Base, CommonMixin):
    __tablename__ = "rule"

    rule_id: Mapped[str] = mapped_column(String(64), unique=True)
    target_variable: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comparator: Mapped[str | None] = mapped_column(String(8), nullable=True)
    relaxations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class RuleEdgeModel(Base, CommonMixin):
    __tablename__ = "rule_edge"

    rule_id: Mapped[str] = mapped_column(String(64))
    depends_on_rule_id: Mapped[str] = mapped_column(String(64))


class FindingModel(Base, CommonMixin):
    __tablename__ = "finding"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(64))
    verdict: Mapped[str] = mapped_column(String(16))
    conditional_relaxations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    requires_committee: Mapped[bool] = mapped_column(Boolean, server_default="false")
    composite_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    gated_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    conflicts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    measured_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    limit_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)


class MappingAssignmentModel(Base, CommonMixin):
    __tablename__ = "mapping_assignment"

    source_criterion: Mapped[str | None] = mapped_column(String(256), nullable=True)
    standard_item: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    silent_pass: Mapped[bool] = mapped_column(Boolean, server_default="false")
