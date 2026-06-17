"""L3-C — ORM 모델(review 스키마). 정성 평가/루브릭 인용/정성 캐시.

qual_assessment, rubric_citation, qual_cache. snapshot/모델버전 결속(재현성).
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class QualAssessmentModel(Base, CommonMixin):
    __tablename__ = "qual_assessment"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    item: Mapped[str | None] = mapped_column(String(128), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_grade: Mapped[bool] = mapped_column(Boolean, server_default="true")
    asserts_legal_verdict: Mapped[bool] = mapped_column(Boolean, server_default="false")


class RubricCitationModel(Base, CommonMixin):
    __tablename__ = "rubric_citation"

    qual_assessment_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    rubric_item: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective: Mapped[bool] = mapped_column(Boolean, server_default="true")


class QualCacheModel(Base, CommonMixin):
    __tablename__ = "qual_cache"

    cache_key: Mapped[str] = mapped_column(String(64), unique=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
