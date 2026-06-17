"""Phase 0 — Declarative Base + 공통 믹스인(UUID PK, org/proj FK 컬럼, ts).

전 모델이 상속한다. metadata는 review 스키마로 결속(다른 프로젝트와 테이블·alembic 격리).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.settings import settings

SCHEMA = settings.DB_SCHEMA

# 명명규약 + 스키마 결속(마이그레이션 안정 + 격리)
_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}
metadata_obj = MetaData(schema=SCHEMA, naming_convention=_NAMING)


class Base(DeclarativeBase):
    metadata = metadata_obj


class CommonMixin:
    """UUID PK + organization_id/project_id + created_at/updated_at 표준 컬럼."""

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
