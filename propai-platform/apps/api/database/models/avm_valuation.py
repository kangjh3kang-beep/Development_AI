"""AVM (자동 시세 추정) 모델.

XGBoost 기반 시세 추정 결과를 저장한다.
MAPE ≤ 5% 기준 (CoVe O1).
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class AVMValuation(Base, TenantMixin, TimestampMixin):
    __tablename__ = "avm_valuations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    estimated_price: Mapped[float] = mapped_column(
        Float, nullable=False, comment="추정 가격 (원)"
    )
    price_per_sqm: Mapped[float] = mapped_column(
        Float, nullable=False, comment="㎡당 단가"
    )
    confidence_score: Mapped[float] = mapped_column(
        Float, nullable=False, comment="신뢰도 (0~1)"
    )
    comparable_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="비교 사례 수"
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    feature_importance: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="특성 중요도"
    )
    comparables: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="비교 사례 상세"
    )

    # 관계
    project = relationship("Project", back_populates="avm_valuations")
