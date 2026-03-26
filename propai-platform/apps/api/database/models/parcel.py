"""필지(토지) 모델.

프로젝트에 속한 토지 정보. 공간 데이터(PostGIS)를 포함한다.
"""

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class Parcel(Base, TenantMixin, TimestampMixin):
    __tablename__ = "parcels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    pnu: Mapped[str | None] = mapped_column(
        String(19), nullable=True, comment="필지고유번호 (19자리)"
    )
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    land_use_zone: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="용도지역"
    )
    boundary = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True,
        comment="필지 경계 폴리곤"
    )
    official_price: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="공시지가 (원/㎡)"
    )
    zoning_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 관계
    project = relationship("Project", back_populates="parcels")
