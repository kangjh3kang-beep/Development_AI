"""v53 operations, risk, and permit persistence models."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from apps.api.database.models.base import Base, TenantMixin, TimestampMixin


class DigitalTwinStatusSnapshot(Base, TenantMixin, TimestampMixin):
    __tablename__ = "digital_twin_status_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    building_type: Mapped[str] = mapped_column(String(40), nullable=False)
    gross_floor_area_sqm: Mapped[float] = mapped_column(nullable=False)
    annual_energy_kwh: Mapped[float] = mapped_column(nullable=False)
    occupancy_rate: Mapped[float] = mapped_column(nullable=False)
    sensor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    online_sensor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latest_anomaly_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_alarm_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eui: Mapped[float] = mapped_column(nullable=False)
    eui_grade: Mapped[str] = mapped_column(String(10), nullable=False)
    operational_readiness_score: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    predicted_next_day_energy_kwh: Mapped[float | None] = mapped_column(nullable=True)
    status_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommendations_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class UnifiedRiskAssessment(Base, TenantMixin, TimestampMixin):
    __tablename__ = "unified_risk_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    composite_risk_score: Mapped[float] = mapped_column(nullable=False)
    grade: Mapped[str] = mapped_column(String(10), nullable=False)
    var_95_ratio: Mapped[float] = mapped_column(nullable=False)
    p90_adjusted_cost_krw: Mapped[float] = mapped_column(nullable=False)
    expected_downside_krw: Mapped[float] = mapped_column(nullable=False)
    dimension_scores_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    assumptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class PermitSubmission(Base, TenantMixin, TimestampMixin):
    __tablename__ = "permit_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    permit_type: Mapped[str] = mapped_column(String(50), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    applicant_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    submission_reference: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    current_stage: Mapped[str] = mapped_column(String(40), nullable=False, default="document-prep")
    building_area_sqm: Mapped[float] = mapped_column(nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_agricultural: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    submit_to_seumter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    readiness_score: Mapped[float] = mapped_column(nullable=False)
    checklist_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    validation_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    submitted_documents_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
