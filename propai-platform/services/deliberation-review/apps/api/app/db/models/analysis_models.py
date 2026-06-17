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
    # INC-14: 원시 입력(AnalysisInput) 보존 — reconcile 불일치 시 동일입력 재실행(결정론)을 위해 필요.
    # None=legacy(0015 이전) 또는 미보존 → reconcile는 재실행 불가로 카운트 표면화(무음0).
    input_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
