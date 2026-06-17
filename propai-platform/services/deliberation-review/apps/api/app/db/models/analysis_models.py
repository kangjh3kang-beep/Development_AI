"""P2 — 분석 실행 영속화(review 스키마). 전체 AnalysisResult를 JSONB로 저장 + 조회.

analysis_run. 동일 입력+스냅샷 재현(input_hash)과 결속. UUID PK = 조회 키.
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class AnalysisRunModel(Base, CommonMixin):
    __tablename__ = "analysis_run"

    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
