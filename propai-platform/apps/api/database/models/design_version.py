"""설계 버전 관리 모델."""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class DesignVersion(Base, TenantMixin, TimestampMixin):
    """설계 버전 관리 테이블.

    프로젝트의 설계 변경 이력을 버전 단위로 추적한다.
    건축/구조/MEP 등 설계 유형별 버전을 관리하며,
    건폐율/용적률/층수 등 주요 설계 지표를 기록한다.
    """

    __tablename__ = "design_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    design_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="architectural",
    )
    floor_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floor_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    building_coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_area_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    design_data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    compliance_log_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
