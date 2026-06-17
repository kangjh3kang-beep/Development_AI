"""L3-B — ORM 모델(review 스키마). 시뮬 지표 + 시뮬 파라미터.

sim_metric, sim_param. snapshot 결속, method_trace JSONB.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Float, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class SimMetricModel(Base, CommonMixin):
    __tablename__ = "sim_metric"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metric_id: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    method_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    required_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)


class SimParamModel(Base, CommonMixin):
    __tablename__ = "sim_param"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[float] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
