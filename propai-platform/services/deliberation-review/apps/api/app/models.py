"""Phase 0 — 부트스트랩 프로브 모델(공통 믹스인 검증용 AT-3). 비즈니스 테이블은 각 페이즈가 추가."""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class ProbeModel(Base, CommonMixin):
    __tablename__ = "probe"

    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
