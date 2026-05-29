"""v61 설계도면 도메인 ORM 모델.

DesignStage, Drawing, DrawingLayer, DrawingEditHistory,
PermitDocumentSet, DesignAlternative.

database/models/base.py 의 Base + TenantMixin 을 사용하여
tenant_id 를 자동 포함한다.
Drawing 만 TimestampMixin 적용 (updated_at 존재), 나머지는 created_at 직접 정의.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


# ---------------------------------------------------------------------------
# DesignStage
# ---------------------------------------------------------------------------
class DesignStage(Base, TenantMixin):
    """설계 단계 (1=계획, 2=기본, 3=인허가, 4=실시)."""

    __tablename__ = "design_stages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False,
    )
    stage_no: Mapped[int] = mapped_column(Integer, nullable=False, comment="1=계획,2=기본,3=인허가,4=실시")
    stage_name: Mapped[str] = mapped_column(String(50), nullable=False)
    stage_status: Mapped[str] = mapped_column(String(30), default="pending", comment="pending/active/completed")
    completion_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    permit_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="인허가 접수번호")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("project_id", "stage_no", name="uq_design_stage_project_stage"),
    )


# ---------------------------------------------------------------------------
# Drawing  (updated_at 존재 -> TimestampMixin 사용)
# ---------------------------------------------------------------------------
class Drawing(Base, TenantMixin, TimestampMixin):
    """도면 -- SVG 벡터, DXF 경로, AI 생성 메타."""

    __tablename__ = "drawings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False,
    )
    stage_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("design_stages.id"), nullable=True)
    drawing_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="B-01, B-02-STD 등")
    drawing_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="배치도/평면도/입면도 등")
    drawing_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    floor_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="B3/B1/1F/기준층/RF")
    direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment="E/W/S/N")
    scale: Mapped[str] = mapped_column(String(20), default="1:200")
    vector_data: Mapped[Any] = mapped_column(JSON, default={})
    svg_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dxf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_model: Mapped[str] = mapped_column(String(50), default="PropAI-v61")
    generation_params: Mapped[Any] = mapped_column(JSON, default={})
    compliance_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    compliance_issues: Mapped[Any] = mapped_column(JSON, default=[])
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# DrawingLayer
# ---------------------------------------------------------------------------
class DrawingLayer(Base, TenantMixin):
    """도면 레이어 (KS A ISO 13567 기반)."""

    __tablename__ = "drawing_layers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False,
    )
    layer_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="A-WALL, A-DOOR 등")
    layer_color: Mapped[str] = mapped_column(String(20), default="#000000")
    layer_weight: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=0.25, comment="선 굵기 mm")
    layer_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    layer_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    layer_order: Mapped[int] = mapped_column(Integer, default=0)
    elements: Mapped[Any] = mapped_column(JSON, default=[])
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# DrawingEditHistory
# ---------------------------------------------------------------------------
class DrawingEditHistory(Base, TenantMixin):
    """도면 편집 이력."""

    __tablename__ = "drawing_edit_histories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    drawing_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("drawings.id"), nullable=False)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    edit_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="ADD/MODIFY/DELETE/MOVE")
    element_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="LINE/POLYLINE/TEXT/HATCH")
    layer_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    before_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    after_data: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    edit_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# PermitDocumentSet
# ---------------------------------------------------------------------------
class PermitDocumentSet(Base, TenantMixin):
    """인허가 도서 현황 (37개 도서)."""

    __tablename__ = "permit_document_sets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False,
    )
    doc_code: Mapped[str] = mapped_column(String(20), nullable=False, comment="A-01, B-01-STD 등")
    doc_category: Mapped[str] = mapped_column(String(10), nullable=False, comment="A/B/C/D/E/F/G")
    doc_name: Mapped[str] = mapped_column(String(200), nullable=False)
    drawing_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("drawings.id"), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submission_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    review_result: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("project_id", "doc_code", name="uq_permit_doc_project_code"),
    )


# ---------------------------------------------------------------------------
# DesignAlternative
# ---------------------------------------------------------------------------
class DesignAlternative(Base, TenantMixin):
    """설계 대안 비교 (MCDM + 몬테카를로)."""

    __tablename__ = "design_alternatives"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False,
    )
    alt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    alt_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    floor_area_ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True, comment="용적률 %")
    building_coverage: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True, comment="건폐율 %")
    total_floor_area: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    sellable_area: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    estimated_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    profit_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    ai_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    legal_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    profit_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    design_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    esg_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 1), nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    selection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mc_win_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 1), nullable=True, comment="몬테카를로 승률 %")
    drawings: Mapped[Any] = mapped_column(JSON, default=[])
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("project_id", "alt_no", name="uq_design_alt_project_no"),
    )
