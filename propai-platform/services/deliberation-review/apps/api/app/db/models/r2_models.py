"""R2 — ORM 모델(review 스키마). 공급/소비 분리 영속화.

source_document, rule_candidate, mirror_snapshot, hitl_task, harvest_job, citation_check.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class SourceDocumentModel(Base, CommonMixin):
    __tablename__ = "source_document"

    doc_id: Mapped[str] = mapped_column(String(128), unique=True)
    tier: Mapped[str] = mapped_column(String(16))
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)


class RuleCandidateModel(Base, CommonMixin):
    __tablename__ = "rule_candidate"

    candidate_id: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default="DRAFT")
    target_variable: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source_doc_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MirrorSnapshotModel(Base, CommonMixin):
    __tablename__ = "mirror_snapshot"
    # INC-13: 멱등·동시writer 안전 — (jurisdiction, snapshot_id) 원자적 upsert(on_conflict) 근거.
    __table_args__ = (UniqueConstraint("jurisdiction", "snapshot_id",
                                       name="uq_mirror_snapshot_jur_sid"),)

    snapshot_id: Mapped[str] = mapped_column(String(64))
    jurisdiction: Mapped[str] = mapped_column(String(64))
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rules: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    active_candidate_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # INC-14: 라이브 본문 해시 provenance(reconcile diff 기준, 0015). nullable=legacy/미설정 허용.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class HITLTaskModel(Base, CommonMixin):
    __tablename__ = "hitl_task"

    task_id: Mapped[str] = mapped_column(String(128), unique=True)
    candidate_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    usage_freq: Mapped[float | None] = mapped_column(Float, nullable=True)
    imminent: Mapped[bool] = mapped_column(Boolean, server_default="false")
    sla_due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class HarvestJobModel(Base, CommonMixin):
    __tablename__ = "harvest_job"

    jurisdiction: Mapped[str] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class CitationCheckModel(Base, CommonMixin):
    __tablename__ = "citation_check"

    citation_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    matched: Mapped[bool] = mapped_column(Boolean, server_default="false")
    method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checked_date: Mapped[date | None] = mapped_column(nullable=True)
