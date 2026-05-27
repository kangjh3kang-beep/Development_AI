"""수지분석 VCS 데이터베이스 모델.

Git 방식의 SHA1 기반 커밋 체인을 PostgreSQL에 영구 저장.
"""

import uuid
from sqlalchemy import String, Boolean, Text, Index, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin, TimestampMixin


class FeasibilityCommit(Base, TenantMixin, TimestampMixin):
    """수지분석 커밋 — 불변 스냅샷."""
    __tablename__ = "feasibility_commits"
    __table_args__ = (
        Index("ix_feas_commit_project_sha", "project_id", "sha"),
        Index("ix_feas_commit_project_branch", "project_id", "branch_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
    parent_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    author: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    branch_name: Mapped[str] = mapped_column(String(100), default="main", nullable=False)


class FeasibilityBranch(Base, TenantMixin):
    """수지분석 브랜치."""
    __tablename__ = "feasibility_branches"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_feas_branch_project_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FeasibilityTag(Base, TenantMixin):
    """수지분석 태그."""
    __tablename__ = "feasibility_tags"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_feas_tag_project_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sha: Mapped[str] = mapped_column(String(40), nullable=False)
