"""설계 모델.

평면도, BIM/IFC, 3D 모델 등 설계 산출물을 관리한다.
파일은 MinIO(S3 호환)에 저장하고 URL을 기록한다.
"""

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class Design(Base, TenantMixin, TimestampMixin):
    __tablename__ = "designs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    design_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="floor_plan | bim_ifc | three_d | site_plan"
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # BIM/IFC 관련 메타데이터
    total_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_volume_m3: Mapped[float | None] = mapped_column(Float, nullable=True)
    element_count: Mapped[int | None] = mapped_column(nullable=True)
    room_count: Mapped[int | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 관계
    project = relationship("Project", back_populates="designs")
