"""L4 — ORM 모델(review 스키마). 유사사례/매치/통계.

precedent_case, precedent_match, precedent_stat. 출처/snapshot 결속.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class PrecedentCaseModel(Base, CommonMixin):
    __tablename__ = "precedent_case"

    case_id: Mapped[str] = mapped_column(String(128), unique=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issue_labels: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    conditions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    decided_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class PrecedentMatchModel(Base, CommonMixin):
    __tablename__ = "precedent_match"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    case_id: Mapped[str] = mapped_column(String(128))
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_candidate: Mapped[bool] = mapped_column(Boolean, server_default="true")
    source: Mapped[str | None] = mapped_column(Text, nullable=True)


class PrecedentStatModel(Base, CommonMixin):
    __tablename__ = "precedent_stat"

    issue: Mapped[str] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distribution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    common_conditions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
