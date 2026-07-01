"""v49 Phase 2: 컴퓨터 비전/WebRTC/디지털 트윈/시설 예약 테이블 추가.

Revision ID: 010_v49_phase2
Revises: 009_v49_devops
Create Date: 2026-03-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "010_v49_phase2"
down_revision: str | None = "009_v49_devops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_column(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _enable_tenant_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation_{table} ON {table} "
        f"USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
    )


def upgrade() -> None:
    # ── safety_violations (G116) ──
    op.create_table(
        "safety_violations",
        _uuid_column("id", nullable=False),
        _uuid_column("tenant_id", nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("camera_id", sa.String(100), nullable=False),
        sa.Column("violation_type", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox_json", postgresql.JSON(), nullable=True),
        sa.Column("frame_url", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_safety_violations_project_id", "safety_violations", ["project_id"])
    op.create_index("ix_safety_violations_violation_type", "safety_violations", ["violation_type"])
    op.create_index("ix_safety_violations_detected_at", "safety_violations", ["detected_at"])
    op.create_index("ix_safety_violations_tenant_id", "safety_violations", ["tenant_id"])
    _enable_tenant_rls("safety_violations")

    # ── parking_records (G119) ──
    op.create_table(
        "parking_records",
        _uuid_column("id", nullable=False),
        _uuid_column("tenant_id", nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("camera_id", sa.String(100), nullable=False),
        sa.Column("plate_number", sa.String(20), nullable=False),
        sa.Column("raw_ocr_text", sa.String(50), nullable=True),
        sa.Column("zone", sa.String(30), nullable=True),
        sa.Column("event_type", sa.String(20), nullable=False, server_default="entry"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_parking_records_project_id", "parking_records", ["project_id"])
    op.create_index("ix_parking_records_plate_number", "parking_records", ["plate_number"])
    op.create_index("ix_parking_records_recorded_at", "parking_records", ["recorded_at"])
    op.create_index("ix_parking_records_tenant_id", "parking_records", ["tenant_id"])
    _enable_tenant_rls("parking_records")

    # ── webrtc_sessions (G113) ──
    op.create_table(
        "webrtc_sessions",
        _uuid_column("id", nullable=False),
        _uuid_column("tenant_id", nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        _uuid_column("initiator_user_id", nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="waiting"),
        sa.Column("ice_candidates_json", postgresql.JSON(), nullable=True),
        sa.Column("ice_retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sdp_offer", sa.String(5000), nullable=True),
        sa.Column("sdp_answer", sa.String(5000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webrtc_sessions_project_id", "webrtc_sessions", ["project_id"])
    op.create_index("ix_webrtc_sessions_tenant_id", "webrtc_sessions", ["tenant_id"])
    _enable_tenant_rls("webrtc_sessions")

    # ── digital_twin_anomalies (G114) ──
    op.create_table(
        "digital_twin_anomalies",
        _uuid_column("id", nullable=False),
        _uuid_column("tenant_id", nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("sensor_type", sa.String(50), nullable=False),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("is_anomaly", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("data_points_used", sa.Integer(), nullable=False),
        sa.Column("feature_values_json", postgresql.JSON(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="info"),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_digital_twin_anomalies_project_id", "digital_twin_anomalies", ["project_id"])
    op.create_index("ix_digital_twin_anomalies_sensor_type", "digital_twin_anomalies", ["sensor_type"])
    op.create_index("ix_digital_twin_anomalies_detected_at", "digital_twin_anomalies", ["detected_at"])
    op.create_index("ix_digital_twin_anomalies_tenant_id", "digital_twin_anomalies", ["tenant_id"])
    _enable_tenant_rls("digital_twin_anomalies")

    # ── facility_reservations (G115) ──
    op.create_table(
        "facility_reservations",
        _uuid_column("id", nullable=False),
        _uuid_column("tenant_id", nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("facility_name", sa.String(200), nullable=False),
        _uuid_column("reserved_by", nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_facility_reservations_project_id", "facility_reservations", ["project_id"])
    op.create_index("ix_facility_reservations_tenant_id", "facility_reservations", ["tenant_id"])
    _enable_tenant_rls("facility_reservations")


def downgrade() -> None:
    for table in (
        "facility_reservations",
        "digital_twin_anomalies",
        "webrtc_sessions",
        "parking_records",
        "safety_violations",
    ):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
