"""v44.0 법규 위반 이력 (G98) -- 법규 검증 결과 기록."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class ComplianceViolationRecord(Base, TenantMixin, TimestampMixin):
    """법규 위반 이력: 설계 검증 시 발생한 위반 사항 기록."""

    __tablename__ = "compliance_violations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, comment="프로젝트 FK"
    )
    violation_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="building_coverage | floor_area_ratio | height | setback | sunlight | structure"
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="error", comment="error | warning"
    )
    message: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="위반 설명 메시지"
    )
    current_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="현재 수치"
    )
    limit_value: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="법규 한도 수치"
    )
    design_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=True, comment="위반 시점 설계 스냅샷"
    )
    resolved: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="해결 여부"
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
