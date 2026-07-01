"""Add Part F foundation tables.

Revision ID: 006_part_f_foundation
Revises: 005_v44_building_compliance
Create Date: 2026-03-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006_part_f_foundation"
down_revision: str | None = "005_v44_building_compliance"
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
    op.create_table(
        "marketing_contents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("asset_type", sa.String(length=80), nullable=False),
        sa.Column("target_audience", sa.String(length=120), nullable=False),
        sa.Column("tone", sa.String(length=40), nullable=False, server_default="professional"),
        sa.Column("headline", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("call_to_action", sa.String(length=255), nullable=False),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_marketing_contents_tenant_id", "marketing_contents", ["tenant_id"])
    op.create_index("ix_marketing_contents_project_id", "marketing_contents", ["project_id"])

    op.create_table(
        "offering_memorandums",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("marketing_content_id", nullable=True),
        sa.Column("version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("sections_json", postgresql.JSON(), nullable=False),
        sa.Column("risk_factors_json", postgresql.JSON(), nullable=False),
        sa.Column("output_format", sa.String(length=30), nullable=False, server_default="markdown"),
        sa.Column("document_url", sa.String(length=500), nullable=True),
        sa.Column("generated_by", sa.String(length=100), nullable=False, server_default="marketing-service"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["marketing_content_id"], ["marketing_contents.id"]),
    )
    op.create_index("ix_offering_memorandums_tenant_id", "offering_memorandums", ["tenant_id"])
    op.create_index("ix_offering_memorandums_project_id", "offering_memorandums", ["project_id"])
    op.create_index("ix_offering_memorandums_marketing_content_id", "offering_memorandums", ["marketing_content_id"])

    op.create_table(
        "domain_agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("domain", sa.String(length=40), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False, server_default="analysis"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="completed"),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("input_summary_json", postgresql.JSON(), nullable=True),
        sa.Column("output_summary_json", postgresql.JSON(), nullable=True),
        sa.Column("recommendation", sa.String(length=80), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_domain_agent_tasks_tenant_id", "domain_agent_tasks", ["tenant_id"])
    op.create_index("ix_domain_agent_tasks_project_id", "domain_agent_tasks", ["project_id"])

    op.create_table(
        "domain_agent_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("task_id"),
        sa.Column("approver_role", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["domain_agent_tasks.id"]),
    )
    op.create_index("ix_domain_agent_approvals_tenant_id", "domain_agent_approvals", ["tenant_id"])
    op.create_index("ix_domain_agent_approvals_project_id", "domain_agent_approvals", ["project_id"])
    op.create_index("ix_domain_agent_approvals_task_id", "domain_agent_approvals", ["task_id"])

    op.create_table(
        "equipment_sensors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("equipment_name", sa.String(length=120), nullable=False),
        sa.Column("equipment_type", sa.String(length=80), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("latest_reading_json", postgresql.JSON(), nullable=True),
        sa.Column("health_status", sa.String(length=30), nullable=False, server_default="normal"),
        sa.Column("last_reading_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_equipment_sensors_tenant_id", "equipment_sensors", ["tenant_id"])
    op.create_index("ix_equipment_sensors_project_id", "equipment_sensors", ["project_id"])

    op.create_table(
        "predictive_maintenance_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("equipment_sensor_id", nullable=True),
        sa.Column("anomaly_score", sa.Float(), nullable=False),
        sa.Column("remaining_useful_life_days", sa.Integer(), nullable=True),
        sa.Column("hvac_efficiency_score", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("telemetry_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["equipment_sensor_id"], ["equipment_sensors.id"]),
    )
    op.create_index("ix_predictive_maintenance_alerts_tenant_id", "predictive_maintenance_alerts", ["tenant_id"])
    op.create_index("ix_predictive_maintenance_alerts_project_id", "predictive_maintenance_alerts", ["project_id"])
    op.create_index(
        "ix_predictive_maintenance_alerts_equipment_sensor_id",
        "predictive_maintenance_alerts",
        ["equipment_sensor_id"],
    )

    op.create_table(
        "work_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("maintenance_alert_id", nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("assigned_team", sa.String(length=120), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["maintenance_alert_id"], ["predictive_maintenance_alerts.id"]),
    )
    op.create_index("ix_work_orders_tenant_id", "work_orders", ["tenant_id"])
    op.create_index("ix_work_orders_project_id", "work_orders", ["project_id"])
    op.create_index("ix_work_orders_maintenance_alert_id", "work_orders", ["maintenance_alert_id"])

    op.create_table(
        "tenant_tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("unit_label", sa.String(length=80), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="open"),
        sa.Column("feedback_text", sa.Text(), nullable=False),
        sa.Column("requested_action", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_tenant_tickets_tenant_id", "tenant_tickets", ["tenant_id"])
    op.create_index("ix_tenant_tickets_project_id", "tenant_tickets", ["project_id"])

    op.create_table(
        "tenant_sentiment_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("tenant_ticket_id", nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("sentiment_label", sa.String(length=20), nullable=False),
        sa.Column("ai_reply", sa.Text(), nullable=True),
        sa.Column("metrics_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["tenant_ticket_id"], ["tenant_tickets.id"]),
    )
    op.create_index("ix_tenant_sentiment_scores_tenant_id", "tenant_sentiment_scores", ["tenant_id"])
    op.create_index("ix_tenant_sentiment_scores_project_id", "tenant_sentiment_scores", ["project_id"])
    op.create_index("ix_tenant_sentiment_scores_tenant_ticket_id", "tenant_sentiment_scores", ["tenant_ticket_id"])

    op.create_table(
        "tenant_financial_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("occupancy_rate", sa.Float(), nullable=False),
        sa.Column("arrears_ratio", sa.Float(), nullable=False),
        sa.Column("churn_risk_score", sa.Float(), nullable=False),
        sa.Column("health_grade", sa.String(length=20), nullable=False),
        sa.Column("metrics_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_tenant_financial_health_tenant_id", "tenant_financial_health", ["tenant_id"])
    op.create_index("ix_tenant_financial_health_project_id", "tenant_financial_health", ["project_id"])

    op.create_table(
        "asset_intelligence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("composite_score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(length=20), nullable=False),
        sa.Column("adjusted_value_krw", sa.Float(), nullable=False),
        sa.Column("component_scores_json", postgresql.JSON(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_asset_intelligence_snapshots_tenant_id", "asset_intelligence_snapshots", ["tenant_id"])
    op.create_index("ix_asset_intelligence_snapshots_project_id", "asset_intelligence_snapshots", ["project_id"])

    op.create_table(
        "capex_optimization_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("snapshot_id"),
        sa.Column("strategy_name", sa.String(length=120), nullable=False),
        sa.Column("expected_roi", sa.Float(), nullable=False),
        sa.Column("payback_months", sa.Integer(), nullable=False),
        sa.Column("recommendations_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["asset_intelligence_snapshots.id"]),
    )
    op.create_index("ix_capex_optimization_results_tenant_id", "capex_optimization_results", ["tenant_id"])
    op.create_index("ix_capex_optimization_results_project_id", "capex_optimization_results", ["project_id"])
    op.create_index("ix_capex_optimization_results_snapshot_id", "capex_optimization_results", ["snapshot_id"])

    for table in (
        "marketing_contents",
        "offering_memorandums",
        "domain_agent_tasks",
        "domain_agent_approvals",
        "equipment_sensors",
        "predictive_maintenance_alerts",
        "work_orders",
        "tenant_tickets",
        "tenant_sentiment_scores",
        "tenant_financial_health",
        "asset_intelligence_snapshots",
        "capex_optimization_results",
    ):
        _enable_tenant_rls(table)


def downgrade() -> None:
    tables = (
        "capex_optimization_results",
        "asset_intelligence_snapshots",
        "tenant_financial_health",
        "tenant_sentiment_scores",
        "tenant_tickets",
        "work_orders",
        "predictive_maintenance_alerts",
        "equipment_sensors",
        "domain_agent_approvals",
        "domain_agent_tasks",
        "offering_memorandums",
        "marketing_contents",
    )

    for table in tables:
        _disable_tenant_rls(table)

    op.drop_table("capex_optimization_results")
    op.drop_table("asset_intelligence_snapshots")
    op.drop_table("tenant_financial_health")
    op.drop_table("tenant_sentiment_scores")
    op.drop_table("tenant_tickets")
    op.drop_table("work_orders")
    op.drop_table("predictive_maintenance_alerts")
    op.drop_table("equipment_sensors")
    op.drop_table("domain_agent_approvals")
    op.drop_table("domain_agent_tasks")
    op.drop_table("offering_memorandums")
    op.drop_table("marketing_contents")
