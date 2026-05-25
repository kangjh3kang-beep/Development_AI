"""수지분석 버전관리(VCS) 모델 — Git 방식 commit/branch/diff/tag/share."""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class FeasibilityCommit(Base):
    """수지분석 커밋 — 불변 스냅샷 + SHA1 해시."""
    __tablename__ = "feasibility_commits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feasibility_project_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_projects.id"), nullable=False, index=True
    )
    branch_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_branches.id"), nullable=True)
    parent_commit_id = Column(UUID(as_uuid=True), nullable=True, comment="이전 커밋")
    sha_hash = Column(String(40), nullable=False, unique=True, comment="SHA1 해시")
    message = Column(Text, nullable=False)
    snapshot_data = Column(JSON, nullable=False, comment="입력+결과 전체 스냅샷")
    author_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FeasibilityBranch(Base):
    """수지분석 브랜치 — 시나리오 분기."""
    __tablename__ = "feasibility_branches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feasibility_project_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_projects.id"), nullable=False, index=True
    )
    name = Column(String(100), nullable=False, comment="main/scenario-a/optimistic 등")
    head_commit_id = Column(UUID(as_uuid=True), nullable=True, comment="최신 커밋")
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FeasibilityDiff(Base):
    """수지분석 Diff — 두 커밋 간 차이."""
    __tablename__ = "feasibility_diffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commit_a_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_commits.id"), nullable=False)
    commit_b_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_commits.id"), nullable=False)
    diff_data = Column(JSON, nullable=False, comment="항목별 {old, new, delta}")
    created_at = Column(DateTime, default=datetime.utcnow)


class FeasibilityTag(Base):
    """수지분석 태그 — 특정 커밋 고정 레이블."""
    __tablename__ = "feasibility_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commit_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_commits.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FeasibilityShare(Base):
    """수지분석 공유 — 버전/커밋 외부 공유 링크."""
    __tablename__ = "feasibility_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feasibility_project_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_projects.id"), nullable=False
    )
    commit_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_commits.id"), nullable=True)
    share_token = Column(String(64), nullable=False, unique=True)
    permissions = Column(String(20), default="read", comment="read/comment/edit")
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class FeasibilityRollback(Base):
    """수지분석 롤백 로그 — 감사 추적."""
    __tablename__ = "feasibility_rollbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feasibility_project_id = Column(
        UUID(as_uuid=True), ForeignKey("feasibility_projects.id"), nullable=False
    )
    from_commit_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_commits.id"), nullable=False)
    to_commit_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_commits.id"), nullable=False)
    reason = Column(Text, nullable=True)
    performed_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
