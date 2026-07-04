import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    project_type = Column(String(50), nullable=False)
    status = Column(String(50), default="planning")
    location_address = Column(Text, nullable=True)
    location_point = Column(Geometry("POINT", srid=4326), nullable=True)
    total_area_sqm = Column(Numeric(12, 2), nullable=True)
    total_budget_krw = Column(Numeric(20, 0), nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata_ = Column("metadata", JSON, default={})

class LandParcel(Base):
    __tablename__ = "land_parcels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    pnu_code = Column(String(19), unique=True, nullable=False)
    jibun_address = Column(Text, nullable=False)
    road_address = Column(Text, nullable=True)
    area_sqm = Column(Numeric(12, 2), nullable=True)
    geometry = Column(Geometry("POLYGON", srid=4326), nullable=True)
    land_use_zone = Column(String(100), nullable=True)
    land_category = Column(String(50), nullable=True)
    official_land_price_krw = Column(Numeric(20, 0), nullable=True)
    owner_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ParcelGroup(Base):
    __tablename__ = "parcel_groups"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name = Column(String(200), nullable=False)
    merged_geometry = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)
    total_area_sqm = Column(Numeric(12, 2), nullable=True)
    pnu_codes = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)

class LandUseZone(Base):
    __tablename__ = "land_use_zones"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_code = Column(String(50), unique=True, nullable=False)
    zone_name = Column(String(100), nullable=False)
    max_floor_area_ratio = Column(Numeric(6, 2), nullable=True)
    max_building_coverage_ratio = Column(Numeric(6, 2), nullable=True)
    max_height_m = Column(Numeric(8, 2), nullable=True)
    allowed_uses = Column(JSON, default=[])
    legal_basis = Column(String(200), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SiteAnalysisReport(Base):
    __tablename__ = "site_analysis_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    analysis_type = Column(String(100), nullable=False)
    far_applicable = Column(Numeric(6, 2), nullable=True)
    bcr_applicable = Column(Numeric(6, 2), nullable=True)
    max_height_applicable = Column(Numeric(8, 2), nullable=True)
    zoning_upgrade_possible = Column(Boolean, default=False)
    development_directions = Column(JSON, default=[])
    ai_recommendation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class LandCompensationEstimate(Base):
    __tablename__ = "land_compensation_estimates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    parcel_id = Column(UUID(as_uuid=True), ForeignKey("land_parcels.id"), nullable=False)
    standard_land_price_krw = Column(Numeric(20, 0), nullable=True)
    compensation_multiplier = Column(Numeric(6, 4), nullable=True)
    estimated_compensation_krw = Column(Numeric(20, 0), nullable=True)
    objection_auto_generated = Column(Boolean, default=False)
    legal_basis = Column(String(200), default="공익사업을 위한 토지 등의 취득 및 보상에 관한 법률")
    created_at = Column(DateTime, default=datetime.utcnow)
