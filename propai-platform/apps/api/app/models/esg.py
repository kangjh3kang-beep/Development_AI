import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Numeric
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class LCAAssessment(Base):
    __tablename__ = "lca_assessments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    standard = Column(String(50), default="ISO 14040:2006")
    phase = Column(String(50), nullable=False)
    gwp_total_kgco2e = Column(Numeric(16, 4), nullable=True)
    gwp_materials = Column(Numeric(16, 4), nullable=True)
    gwp_construction = Column(Numeric(16, 4), nullable=True)
    gwp_operation = Column(Numeric(16, 4), nullable=True)
    gwp_eol = Column(Numeric(16, 4), nullable=True)
    ipcc_version = Column(String(20), default="AR6 2021")
    calculation_details = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class LCCAnalysis(Base):
    __tablename__ = "lcc_analyses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    standard = Column(String(50), default="ISO 15686-5:2017")
    lifecycle_years = Column(Integer, nullable=False)
    discount_rate = Column(Numeric(5, 4), nullable=True)
    construction_cost_krw = Column(Numeric(20, 0), nullable=True)
    maintenance_pv_krw = Column(Numeric(20, 0), nullable=True)
    energy_pv_krw = Column(Numeric(20, 0), nullable=True)
    replacement_pv_krw = Column(Numeric(20, 0), nullable=True)
    total_lcc_krw = Column(Numeric(20, 0), nullable=True)
    cash_flow_yearly = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class ZEBCertification(Base):
    __tablename__ = "zeb_certifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    legal_basis = Column(String(100), default="녹색건축물 조성 지원법 제17조")
    energy_independence_ratio = Column(Numeric(6, 2), nullable=True)
    total_energy_kwh = Column(Numeric(16, 2), nullable=True)
    renewable_energy_kwh = Column(Numeric(16, 2), nullable=True)
    zeb_grade = Column(String(20), nullable=True)
    energyplus_idf_path = Column(String(500), nullable=True)
    simulation_result = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class EPDMaterialCarbon(Base):
    __tablename__ = "epd_material_carbon"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    material_name = Column(String(200), nullable=False)
    material_category = Column(String(100), nullable=False)
    quantity_kg = Column(Numeric(16, 2), nullable=False)
    epd_coefficient_kgco2e_per_kg = Column(Numeric(10, 6), nullable=True)
    carbon_footprint_kgco2e = Column(Numeric(16, 4), nullable=True)
    low_carbon_alternative = Column(String(200), nullable=True)
    reduction_potential_pct = Column(Numeric(5, 2), nullable=True)
    standard = Column(String(50), default="ISO 21930:2017")
    created_at = Column(DateTime, default=datetime.utcnow)

class LifecycleOptimization(Base):
    __tablename__ = "lifecycle_optimization"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    optimization_type = Column(String(50), nullable=False)
    standard = Column(String(50), default="ISO 15686-1")
    lifecycle_years = Column(Integer, nullable=False)
    discount_rate = Column(Numeric(5, 4), nullable=True)
    optimal_lcc_krw = Column(Numeric(20, 0), nullable=True)
    component_replacement_schedule = Column(JSON, default={})
    energy_optimization_scenario = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
