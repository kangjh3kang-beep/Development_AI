"""프로젝트 모델.

부동산 개발 프로젝트의 핵심 엔티티.
PostGIS geometry 컬럼으로 위치 정보를 저장한다.
"""

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.api.database.models.base import Base, SoftDeleteMixin, TenantMixin, TimestampMixin


class Project(Base, TenantMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # PostGIS 공간 정보
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    total_area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 관계
    tenant = relationship("Tenant", back_populates="projects")
    parcels = relationship("Parcel", back_populates="project", lazy="selectin")
    designs = relationship("Design", back_populates="project", lazy="selectin")
    avm_valuations = relationship("AVMValuation", back_populates="project", lazy="selectin")
    financial_analyses = relationship("FinancialAnalysis", back_populates="project", lazy="selectin")
    drone_inspections = relationship("DroneInspection", back_populates="project", lazy="selectin")
    tax_calculations = relationship("TaxCalculation", back_populates="project", lazy="selectin")
    escrow_transactions = relationship("EscrowTransaction", back_populates="project", lazy="selectin")
    construction_logs = relationship("ConstructionLog", back_populates="project", lazy="selectin")
