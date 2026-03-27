"""평면도 및 CAD 요소 모델."""

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class FloorPlan(Base, TenantMixin, TimestampMixin):
    """평면도 테이블.

    건물의 각 층별 평면 정보를 관리한다.
    층 번호, 면적, 층고, CAD 요소 JSON 등을 기록하며,
    설계 버전과 연계하여 변경 이력을 추적한다.
    """

    __tablename__ = "floor_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True,
    )
    design_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("design_versions.id"), nullable=True, index=True,
    )
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_height_m: Mapped[float] = mapped_column(Float, nullable=False, default=3.3)
    elements_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_ground_floor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CadElement(Base, TenantMixin, TimestampMixin):
    """CAD 요소 테이블.

    평면도 내 개별 건축 요소(벽, 기둥, 슬래브, 창문, 문, 계단 등)를 관리한다.
    위치, 크기, 회전, 재질 등 속성을 기록하며,
    AI 기반 설계 자동화에 활용된다.
    """

    __tablename__ = "cad_elements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True,
    )
    floor_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("floor_plans.id"), nullable=False, index=True,
    )
    element_type: Mapped[str] = mapped_column(String(50), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    y: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    width: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    height: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    rotation_deg: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    properties_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
