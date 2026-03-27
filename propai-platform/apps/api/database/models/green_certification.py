"""친환경 인증 모델."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class GreenCertification(Base, TenantMixin, TimestampMixin):
    """친환경 인증 평가 테이블.

    G-SEED, ZEB, LEED 등 친환경 인증 평가 결과를 기록한다.
    카테고리별 점수, 등급, 적합 여부를 관리하며,
    탄소 저감 전략 수립의 기초 데이터로 활용된다.
    """

    __tablename__ = "green_certifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    cert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[str] = mapped_column(String(10), nullable=False)
    category_scores_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
