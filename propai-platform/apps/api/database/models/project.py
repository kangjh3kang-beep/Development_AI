"""프로젝트 모델.

부동산 개발 프로젝트의 핵심 엔티티.
PostGIS geometry 컬럼으로 위치 정보를 저장한다.
"""

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
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

    # v61 확장 컬럼 (마이그레이션 005)
    pnu_codes: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="필지 PNU 코드 목록")
    zone_type: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="용도지역 유형")
    max_bcr: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True, comment="최대 건폐율 %")
    max_far: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True, comment="최대 용적률 %")
    max_height: Mapped[float | None] = mapped_column(Numeric(6, 1), nullable=True, comment="최대 높이 m")
    building_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="건물 유형")
    floor_above: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="지상 층수")
    floor_below: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="지하 층수")

    # 분석 스냅샷(마이그레이션 024) — 프로젝트별 분석 결과 백엔드 단일출처.
    # 프론트 useProjectContextStore의 ProjectSnapshot(siteAnalysis/designData/
    # costData/feasibilityData/esgData/complianceData/completedStages 등) JSON blob.
    # 기기간 동기화 목적. nullable, default None(기존 흐름 무파괴·additive).
    analysis_snapshot: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="프로젝트별 분석 스냅샷(기기무관 영속)"
    )

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
