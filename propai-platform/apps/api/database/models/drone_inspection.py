"""드론 점검 모델.

YOLOv8 기반 하자 탐지 결과를 저장한다.
F1 ≥ 0.80 기준 (CoVe O6).
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class DroneInspection(Base, TenantMixin, TimestampMixin):
    __tablename__ = "drone_inspections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    flight_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="비행 ID"
    )
    images_processed: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    defects_found: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    defects: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="탐지된 하자 목록 [{type, severity, location, confidence}]"
    )
    severity_summary: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="심각도별 건수 {EMERGENCY: n, HIGH: n, ...}"
    )
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detection_f1: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="탐지 F1 스코어"
    )
    report_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="점검 보고서 URL"
    )

    # 관계
    project = relationship("Project", back_populates="drone_inspections")
