"""v62 분양관리(sales)/모델하우스(mh) 공통 믹스인 + PostgreSQL ltree 타입.

기존 플랫폼 Base(apps.api.database.models.base.Base)를 그대로 사용하며,
sales/mh 도메인 전용 믹스인(현장 격리 site_id, 소프트삭제, 생성자)을 제공한다.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType


class Ltree(UserDefinedType):
    """PostgreSQL ltree 컬럼 타입(조직 계층 경로). 마이그레이션에서 ltree 확장 생성."""

    cache_ok = True

    def get_col_spec(self, **kw):
        return "LTREE"

    def bind_processor(self, dialect):
        def process(value):
            return str(value) if value is not None else None
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            return value
        return process


class PKMixin:
    """UUID 기본키(서버측 gen_random_uuid)."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    """생성/수정 시각."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"), nullable=False
    )


class SoftDeleteMixin:
    """소프트 삭제(deleted_at). 부분 유니크 인덱스 WHERE deleted_at IS NULL 와 연동."""

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SiteMixin:
    """현장(분양 사이트) 격리 키. RLS app.site_id 정책과 연동."""

    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales_sites.id"), nullable=False, index=True
    )


class CreatedByMixin:
    """생성자(users.id 참조하지 않는 약한 참조 — 운영 유연성)."""

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
