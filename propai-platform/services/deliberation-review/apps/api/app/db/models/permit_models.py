"""인·허가/심의 프로세스 영속 모델(review 스키마). blob(권위 조회본) + project/org(프로젝트 DB 결속)."""
from __future__ import annotations

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class PermitProcessRunModel(Base, CommonMixin):
    __tablename__ = "permit_process_run"
    # 0016 마이그레이션과 동일 리터럴 명칭의 명시적 인덱스 — 모델=SSOT, autogenerate 드리프트(DROP) 0.
    # (index=True만 쓰면 _NAMING으로 'ix_review_..._project_id'가 돼 마이그레이션 명칭과 어긋남)
    __table_args__ = (Index("ix_permit_process_run_project", "project_id"),)

    spec_id: Mapped[str] = mapped_column(String(64))
    spec_version: Mapped[str] = mapped_column(String(64))
    analysis_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_conformance: Mapped[str | None] = mapped_column(String(16), nullable=True)
    overall_verification: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result: Mapped[dict] = mapped_column(JSONB)   # PermitProcessResult 전체(재현)
