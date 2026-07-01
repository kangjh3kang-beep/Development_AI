"""Add v44 building compliance tables (G96-G99).

Revision ID: 005_v44_building_compliance
Revises: 004_phase_e_foundation
Create Date: 2026-03-22

건축 법규 검증 / 자동 보정 엔진용 4개 테이블:
- building_regulations: 용도지역별 법규 한도 (G96)
- cad_edit_history: CAD 편집 이력 (G97)
- compliance_violations: 법규 위반 기록 (G98)
- auto_correction_history: 자동 보정 대안 (G99)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005_v44_building_compliance"
down_revision: str | None = "004_phase_e_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_column(name: str, nullable: bool = False) -> sa.Column:
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
    # ── G96: 용도지역별 건축 법규 한도 ──
    op.create_table(
        "building_regulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        sa.Column("zone_code", sa.String(length=20), nullable=False),
        sa.Column("zone_name", sa.String(length=100), nullable=False),
        sa.Column("building_coverage_ratio", sa.Float(), nullable=False),
        sa.Column("floor_area_ratio", sa.Float(), nullable=False),
        sa.Column("max_height_m", sa.Float(), nullable=False),
        sa.Column("min_setback_m", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("sunlight_hours_min", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_building_regulations_tenant_id", "building_regulations", ["tenant_id"])
    op.create_index("ix_building_regulations_zone_code", "building_regulations", ["zone_code"])

    # ── G97: CAD 편집 이력 ──
    op.create_table(
        "cad_edit_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("user_id"),
        sa.Column("edit_type", sa.String(length=30), nullable=False),
        sa.Column("element_id", sa.String(length=100), nullable=False),
        sa.Column("before_state", postgresql.JSONB(), nullable=True),
        sa.Column("after_state", postgresql.JSONB(), nullable=True),
        sa.Column("design_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_cad_edit_history_tenant_id", "cad_edit_history", ["tenant_id"])
    op.create_index("ix_cad_edit_history_project_id", "cad_edit_history", ["project_id"])
    op.create_index("ix_cad_edit_history_user_id", "cad_edit_history", ["user_id"])

    # ── G98: 법규 위반 기록 ──
    op.create_table(
        "compliance_violations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("violation_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="error"),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("limit_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("design_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_compliance_violations_tenant_id", "compliance_violations", ["tenant_id"])
    op.create_index("ix_compliance_violations_project_id", "compliance_violations", ["project_id"])
    op.create_index("ix_compliance_violations_violation_type", "compliance_violations", ["violation_type"])

    # ── G99: 자동 보정 대안 이력 ──
    op.create_table(
        "auto_correction_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("violation_id"),
        sa.Column("violation_type", sa.String(length=50), nullable=False),
        sa.Column("alternative_id", sa.String(length=10), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("corrected_design", postgresql.JSONB(), nullable=False),
        sa.Column("estimated_cost_change_krw", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("far_after", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("bcr_after", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["violation_id"], ["compliance_violations.id"]),
    )
    op.create_index("ix_auto_correction_history_tenant_id", "auto_correction_history", ["tenant_id"])
    op.create_index("ix_auto_correction_history_project_id", "auto_correction_history", ["project_id"])
    op.create_index("ix_auto_correction_history_violation_id", "auto_correction_history", ["violation_id"])

    # ── 모든 테이블에 RLS 적용 ──
    for table in (
        "building_regulations",
        "cad_edit_history",
        "compliance_violations",
        "auto_correction_history",
    ):
        _enable_tenant_rls(table)


def downgrade() -> None:
    tables = (
        "auto_correction_history",
        "compliance_violations",
        "cad_edit_history",
        "building_regulations",
    )

    for table in tables:
        _disable_tenant_rls(table)

    op.drop_table("auto_correction_history")
    op.drop_table("compliance_violations")
    op.drop_table("cad_edit_history")
    op.drop_table("building_regulations")
