"""전세 리스크 분석 결과 모델.

전세가율, 위험등급, HUG 보증보험 가입 가능 여부, 사기 패턴 탐지 결과를 저장한다.
"""

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class JeonseAnalysis(Base, TenantMixin, TimestampMixin):
    __tablename__ = "jeonse_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    jeonse_price: Mapped[float] = mapped_column(Float, nullable=False, comment="전세가 (원)")
    sale_price: Mapped[float] = mapped_column(Float, nullable=False, comment="매매가 (원)")
    jeonse_ratio: Mapped[float] = mapped_column(Float, nullable=False, comment="전세가율")
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="위험 등급 (SAFE/LOW/MEDIUM/HIGH/CRITICAL)"
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, comment="위험 점수 (0~1)")
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True, comment="종합 분석")
    factors: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="위험 요인")
    hug_eligible: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="HUG 보증보험 가입 가능"
    )
    hug_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    market_data: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="시장 데이터")

    # 관계
    project = relationship("Project", backref="jeonse_analyses")
