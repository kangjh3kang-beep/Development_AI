"""v44.0 자동 보정 이력 (G99) -- 법규 위반 자동 보정 대안 기록."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class AutoCorrectionHistory(Base, TenantMixin, TimestampMixin):
    """자동 보정 이력: AI가 제안한 보정 대안과 적용 결과."""

    __tablename__ = "auto_correction_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="프로젝트 FK"
    )
    violation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="위반 기록 FK"
    )
    violation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="위반 유형"
    )
    alternative_id: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="대안 식별자 (A, B, C ...)"
    )
    description: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="보정 대안 설명"
    )
    corrected_design: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="보정 후 설계 데이터"
    )
    estimated_cost_change_krw: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="예상 공사비 변동 (원)"
    )
    far_after: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="보정 후 용적률"
    )
    bcr_after: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="보정 후 건폐율"
    )
    applied: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="사용자 적용 여부"
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
