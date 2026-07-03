import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from apps.api.database.models.base import Base


class SmartCityData(Base):
    __tablename__ = "smart_city_data"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True)
    data_type = Column(String(100), nullable=False)
    location_point = Column(Geometry("POINT", srid=4326), nullable=True)
    value = Column(Numeric(16, 4), nullable=True)
    unit = Column(String(50), nullable=True)
    source = Column(String(200), nullable=True)
    development_score = Column(Numeric(5, 2), nullable=True)
    recorded_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DigitalTwinRealtime(Base):
    __tablename__ = "digital_twin_realtime"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    twin_type = Column(String(100), nullable=False)
    sensor_data = Column(JSON, default={})
    energy_consumption_kwh = Column(Numeric(12, 4), nullable=True)
    occupancy_rate = Column(Numeric(5, 2), nullable=True)
    optimal_operation_scenario = Column(JSON, default={})
    ifc_version = Column(String(20), default="IFC 4.3")
    recorded_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class RegulationChangeLog(Base):
    __tablename__ = "regulation_change_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    law_name = Column(String(200), nullable=False)
    article_number = Column(String(100), nullable=True)
    change_type = Column(String(50), nullable=False)
    change_summary = Column(Text, nullable=True)
    impact_analysis = Column(JSON, default={})
    affected_projects = Column(JSON, default=[])
    notification_sent = Column(Boolean, default=False)
    effective_date = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow)

class PortfolioOptimization(Base):
    __tablename__ = "portfolio_optimization"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    optimization_type = Column(String(100), nullable=False)
    asset_count = Column(Integer, nullable=False)
    total_value_krw = Column(Numeric(20, 0), nullable=True)
    optimized_allocation = Column(JSON, default={})
    rebalancing_recommendation = Column(JSON, default={})
    legal_basis = Column(String(200), default="부동산 투자회사법")
    created_at = Column(DateTime, default=datetime.utcnow)

class NaturalDisasterRisk(Base):
    __tablename__ = "natural_disaster_risk"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    location_point = Column(Geometry("POINT", srid=4326), nullable=True)
    flood_risk_score = Column(Numeric(5, 2), nullable=True)
    landslide_risk_score = Column(Numeric(5, 2), nullable=True)
    earthquake_risk_score = Column(Numeric(5, 2), nullable=True)
    total_risk_score = Column(Numeric(5, 2), nullable=True)
    risk_level = Column(String(20), nullable=True)
    evacuation_routes = Column(JSON, default=[])
    legal_basis = Column(String(200), default="자연재해대책법")
    created_at = Column(DateTime, default=datetime.utcnow)

class ProcurementOptimization(Base):
    __tablename__ = "procurement_optimization"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    material_name = Column(String(200), nullable=False)
    current_price_krw = Column(Numeric(16, 0), nullable=True)
    ppi_index = Column(Numeric(8, 2), nullable=True)
    optimal_order_quantity = Column(Numeric(12, 2), nullable=True)
    optimal_order_timing = Column(DateTime, nullable=True)
    supplier_scores = Column(JSON, default={})
    eoq_calculation = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class DesignReviewResult(Base):
    __tablename__ = "design_review_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    drawing_type = Column(String(100), nullable=False)
    review_status = Column(String(50), nullable=False)
    error_count = Column(Integer, default=0)
    errors_detected = Column(JSON, default=[])
    correction_items = Column(JSON, default=[])
    legal_violations = Column(JSON, default=[])
    ai_feedback = Column(Text, nullable=True)
    legal_basis = Column(String(200), default="건축법 제25조")
    created_at = Column(DateTime, default=datetime.utcnow)

class PublicInsightReport(Base):
    __tablename__ = "public_insight_reports"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    report_type = Column(String(100), nullable=False)
    data_source = Column(String(200), nullable=True)
    insights = Column(JSON, default={})
    market_trend = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)
