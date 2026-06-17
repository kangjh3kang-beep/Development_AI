"""R1.5 — ORM 모델(review 스키마). 법정 산정값 + 산정규칙/규칙셋/파라미터.

legal_quantity, calc_rule, calc_rule_set, calc_param. snapshot_id 결속, calc_trace JSONB.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, Float, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class LegalQuantityModel(Base, CommonMixin):
    __tablename__ = "legal_quantity"

    analysis_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    variable_id: Mapped[str] = mapped_column(String(128))
    value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    calc_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    calc_rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CalcRuleModel(Base, CommonMixin):
    __tablename__ = "calc_rule"

    rule_id: Mapped[str] = mapped_column(String(64), unique=True)
    target_variable: Mapped[str] = mapped_column(String(128))
    exclusion_logic_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class CalcRuleSetModel(Base, CommonMixin):
    __tablename__ = "calc_rule_set"

    set_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[str] = mapped_column(String(64))
    effective_date: Mapped[date] = mapped_column(Date)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ruleset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CalcParamModel(Base, CommonMixin):
    __tablename__ = "calc_param"

    name: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[float] = mapped_column(Numeric)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    basis_article: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
