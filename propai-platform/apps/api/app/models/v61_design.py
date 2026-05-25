"""v61 설계도면 도메인 ORM 모델 — DesignStage, Drawing, DrawingLayer, DrawingEditHistory,
PermitDocumentSet, DesignAlternative."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Date, Float, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from app.core.database import Base


class DesignStage(Base):
    """설계 단계 (1=계획, 2=기본, 3=인허가, 4=실시)."""
    __tablename__ = "design_stages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    stage_no = Column(Integer, nullable=False, comment="1=계획,2=기본,3=인허가,4=실시")
    stage_name = Column(String(50), nullable=False)
    stage_status = Column(String(30), default="pending", comment="pending/active/completed")
    completion_pct = Column(Numeric(5, 2), default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    permit_ref = Column(String(100), nullable=True, comment="인허가 접수번호")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "stage_no", name="uq_design_stage_project_stage"),
    )


class Drawing(Base):
    """도면 — SVG 벡터, DXF 경로, AI 생성 메타."""
    __tablename__ = "drawings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    stage_id = Column(BigInteger, ForeignKey("design_stages.id"), nullable=True)
    drawing_code = Column(String(20), nullable=False, comment="B-01, B-02-STD 등")
    drawing_type = Column(String(50), nullable=False, comment="배치도/평면도/입면도 등")
    drawing_name = Column(String(200), nullable=True)
    floor_level = Column(String(20), nullable=True, comment="B3/B1/1F/기준층/RF")
    direction = Column(String(10), nullable=True, comment="E/W/S/N")
    scale = Column(String(20), default="1:200")
    vector_data = Column(JSON, default={})
    svg_content = Column(Text, nullable=True)
    dxf_path = Column(Text, nullable=True)
    ai_generated = Column(Boolean, default=True)
    ai_model = Column(String(50), default="PropAI-v61")
    generation_params = Column(JSON, default={})
    compliance_ok = Column(Boolean, nullable=True)
    compliance_issues = Column(JSON, default=[])
    version = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DrawingLayer(Base):
    """도면 레이어 (KS A ISO 13567 기반)."""
    __tablename__ = "drawing_layers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    drawing_id = Column(BigInteger, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False)
    layer_name = Column(String(100), nullable=False, comment="A-WALL, A-DOOR 등")
    layer_color = Column(String(20), default="#000000")
    layer_weight = Column(Numeric(4, 1), default=0.25, comment="선 굵기 mm")
    layer_visible = Column(Boolean, default=True)
    layer_locked = Column(Boolean, default=False)
    layer_order = Column(Integer, default=0)
    elements = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)


class DrawingEditHistory(Base):
    """도면 편집 이력."""
    __tablename__ = "drawing_edit_histories"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    drawing_id = Column(BigInteger, ForeignKey("drawings.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    edit_type = Column(String(50), nullable=False, comment="ADD/MODIFY/DELETE/MOVE")
    element_type = Column(String(50), nullable=True, comment="LINE/POLYLINE/TEXT/HATCH")
    layer_name = Column(String(100), nullable=True)
    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)
    edit_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PermitDocumentSet(Base):
    """인허가 도서 현황 (37개 도서)."""
    __tablename__ = "permit_document_sets"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    doc_code = Column(String(20), nullable=False, comment="A-01, B-01-STD 등")
    doc_category = Column(String(10), nullable=False, comment="A/B/C/D/E/F/G")
    doc_name = Column(String(200), nullable=False)
    drawing_id = Column(BigInteger, ForeignKey("drawings.id"), nullable=True)
    is_required = Column(Boolean, default=True)
    is_completed = Column(Boolean, default=False)
    file_path = Column(Text, nullable=True)
    submission_date = Column(Date, nullable=True)
    review_result = Column(String(50), nullable=True)
    review_comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "doc_code", name="uq_permit_doc_project_code"),
    )


class DesignAlternative(Base):
    """설계 대안 비교 (MCDM + 몬테카를로)."""
    __tablename__ = "design_alternatives"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    alt_no = Column(Integer, nullable=False)
    alt_name = Column(String(100), nullable=True)
    floor_area_ratio = Column(Numeric(6, 2), nullable=True, comment="용적률 %")
    building_coverage = Column(Numeric(5, 2), nullable=True, comment="건폐율 %")
    total_floor_area = Column(Numeric(12, 2), nullable=True)
    sellable_area = Column(Numeric(12, 2), nullable=True)
    estimated_revenue = Column(Numeric(18, 2), nullable=True)
    estimated_cost = Column(Numeric(18, 2), nullable=True)
    profit_rate = Column(Numeric(5, 2), nullable=True)
    ai_score = Column(Numeric(4, 1), nullable=True)
    legal_score = Column(Numeric(4, 1), nullable=True)
    profit_score = Column(Numeric(4, 1), nullable=True)
    design_score = Column(Numeric(4, 1), nullable=True)
    esg_score = Column(Numeric(4, 1), nullable=True)
    is_selected = Column(Boolean, default=False)
    selection_reason = Column(Text, nullable=True)
    mc_win_rate = Column(Numeric(5, 1), nullable=True, comment="몬테카를로 승률 %")
    drawings = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("project_id", "alt_no", name="uq_design_alt_project_no"),
    )
