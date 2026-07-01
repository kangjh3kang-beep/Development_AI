"""Add v53 digital twin status, risk, and permit tables.

Revision ID: 017_v53_phase2_operations
Revises: 016_v53_cost_intelligence
Create Date: 2026-03-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "017_v53_phase2_operations"
down_revision: str | None = "016_v53_cost_intelligence"
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


def _disable_tenant_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "digital_twin_status_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("building_type", sa.String(length=40), nullable=False),
        sa.Column("gross_floor_area_sqm", sa.Float(), nullable=False),
        sa.Column("annual_energy_kwh", sa.Float(), nullable=False),
        sa.Column("occupancy_rate", sa.Float(), nullable=False),
        sa.Column("sensor_count", sa.Integer(), nullable=False),
        sa.Column("online_sensor_count", sa.Integer(), nullable=False),
        sa.Column("latest_anomaly_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_alarm_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eui", sa.Float(), nullable=False),
        sa.Column("eui_grade", sa.String(length=10), nullable=False),
        sa.Column("operational_readiness_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("predicted_next_day_energy_kwh", sa.Float(), nullable=True),
        sa.Column("status_summary_json", postgresql.JSON(), nullable=True),
        sa.Column("recommendations_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_digital_twin_status_snapshots_tenant_id", "digital_twin_status_snapshots", ["tenant_id"])
    op.create_index("ix_digital_twin_status_snapshots_project_id", "digital_twin_status_snapshots", ["project_id"])

    op.create_table(
        "unified_risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("composite_risk_score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(length=10), nullable=False),
        sa.Column("var_95_ratio", sa.Float(), nullable=False),
        sa.Column("p90_adjusted_cost_krw", sa.Float(), nullable=False),
        sa.Column("expected_downside_krw", sa.Float(), nullable=False),
        sa.Column("dimension_scores_json", postgresql.JSON(), nullable=True),
        sa.Column("assumptions_json", postgresql.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_unified_risk_assessments_tenant_id", "unified_risk_assessments", ["tenant_id"])
    op.create_index("ix_unified_risk_assessments_project_id", "unified_risk_assessments", ["project_id"])

    op.create_table(
        "permit_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("permit_type", sa.String(length=50), nullable=False),
        sa.Column("region", sa.String(length=50), nullable=False),
        sa.Column("applicant_name", sa.String(length=120), nullable=True),
        sa.Column("submission_reference", sa.String(length=80), nullable=False, unique=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("current_stage", sa.String(length=40), nullable=False, server_default="document-prep"),
        sa.Column("building_area_sqm", sa.Float(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_agricultural", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("submit_to_seumter", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("readiness_score", sa.Float(), nullable=False),
        sa.Column("checklist_json", postgresql.JSON(), nullable=True),
        sa.Column("validation_summary_json", postgresql.JSON(), nullable=True),
        sa.Column("duration_summary_json", postgresql.JSON(), nullable=True),
        sa.Column("submitted_documents_json", postgresql.JSON(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_permit_submissions_tenant_id", "permit_submissions", ["tenant_id"])
    op.create_index("ix_permit_submissions_project_id", "permit_submissions", ["project_id"])
    op.create_index("ix_permit_submissions_submission_reference", "permit_submissions", ["submission_reference"])

    for table in (
        "digital_twin_status_snapshots",
        "unified_risk_assessments",
        "permit_submissions",
    ):
        _enable_tenant_rls(table)


def downgrade() -> None:
    for table in (
        "permit_submissions",
        "unified_risk_assessments",
        "digital_twin_status_snapshots",
    ):
        _disable_tenant_rls(table)

    op.drop_table("permit_submissions")
    op.drop_table("unified_risk_assessments")
    op.drop_table("digital_twin_status_snapshots")
