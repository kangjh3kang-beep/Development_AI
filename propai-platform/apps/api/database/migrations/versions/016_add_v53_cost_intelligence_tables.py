"""Add v53 cost intelligence tables.

Revision ID: 016_v53_cost_intelligence
Revises: 015_patch_s06_backup_logs
Create Date: 2026-03-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "016_v53_cost_intelligence"
down_revision: str | None = "015_patch_s06_backup_logs"
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
        "material_price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        sa.Column("material_code", sa.String(length=100), nullable=False),
        sa.Column("material_name", sa.String(length=500), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("region_code", sa.String(length=20), nullable=False, server_default="KR"),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("source_name", sa.String(length=60), nullable=False, server_default="kcci-simulated"),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("unit_price_krw", sa.Float(), nullable=False),
        sa.Column("price_index", sa.Float(), nullable=False),
        sa.Column("mom_change_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("yoy_change_ratio", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_material_price_history_tenant_id", "material_price_history", ["tenant_id"])
    op.create_index("ix_material_price_history_material_code", "material_price_history", ["material_code"])
    op.create_index("ix_material_price_history_category", "material_price_history", ["category"])
    op.create_index("ix_material_price_history_snapshot_at", "material_price_history", ["snapshot_at"])

    op.create_table(
        "cost_escalation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("baseline_year", sa.Integer(), nullable=False),
        sa.Column("target_year", sa.Integer(), nullable=False),
        sa.Column("construction_duration_months", sa.Integer(), nullable=False),
        sa.Column("base_construction_cost_krw", sa.Float(), nullable=False),
        sa.Column("adjusted_cost_krw", sa.Float(), nullable=False),
        sa.Column("escalation_amount_krw", sa.Float(), nullable=False),
        sa.Column("overall_escalation_ratio", sa.Float(), nullable=False),
        sa.Column("material_share_ratio", sa.Float(), nullable=False),
        sa.Column("labor_share_ratio", sa.Float(), nullable=False),
        sa.Column("overhead_share_ratio", sa.Float(), nullable=False),
        sa.Column("contingency_ratio", sa.Float(), nullable=False),
        sa.Column("contingency_amount_krw", sa.Float(), nullable=False),
        sa.Column("ppi_source", sa.String(length=60), nullable=False, server_default="ecos-simulated"),
        sa.Column("yearly_projection_json", postgresql.JSON(), nullable=True),
        sa.Column("material_impacts_json", postgresql.JSON(), nullable=True),
        sa.Column("alerts_json", postgresql.JSON(), nullable=True),
        sa.Column("request_assumptions_json", postgresql.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_cost_escalation_snapshots_tenant_id", "cost_escalation_snapshots", ["tenant_id"])
    op.create_index("ix_cost_escalation_snapshots_project_id", "cost_escalation_snapshots", ["project_id"])

    _enable_tenant_rls("material_price_history")
    _enable_tenant_rls("cost_escalation_snapshots")


def downgrade() -> None:
    _disable_tenant_rls("cost_escalation_snapshots")
    _disable_tenant_rls("material_price_history")
    op.drop_table("cost_escalation_snapshots")
    op.drop_table("material_price_history")
