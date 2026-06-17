"""INC-11 — 외부 1차출처 응답 캐시(review 스키마).

external_source_cache: 어댑터(law.go.kr/MOLIT/VWORLD 등)의 외부 호출 응답을 영속. 분석마다 재호출
(쿼터/지연/비용) 제거 + 적중 시 동일 입력→동일 출력(결정론 영향 0). payload에 ref/etag/fetched_at 보존
(1차출처·설명가능성), snapshot_id 결속(재현성). cache_key=adapter+endpoint+정규화params 해시(secret 제외).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CommonMixin


class ExternalSourceCacheModel(Base, CommonMixin):
    __tablename__ = "external_source_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_external_source_cache_cache_key"),)

    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    adapter: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    params_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 캐시된 응답(dict 또는 list)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(256), nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
