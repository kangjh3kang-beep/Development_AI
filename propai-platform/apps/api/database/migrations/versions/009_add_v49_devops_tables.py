"""v49 Phase 1: DevOps 모니터링/백업/Rate Limit/알림 테이블 추가.

Revision ID: 009_v49_devops
Revises: 008_chatbot_auction_contractor
Create Date: 2026-03-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "009_v49_devops"
down_revision: str | None = "008_chatbot_auction_contractor"
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
    # ── monitoring_metrics ──
    op.create_table(
        "monitoring_metrics",
        _uuid_column("id", nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False, server_default="percent"),
        sa.Column("threshold_warning", sa.Float(), nullable=True),
        sa.Column("threshold_critical", sa.Float(), nullable=True),
        sa.Column("labels", sa.String(500), nullable=True),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_metrics_host", "monitoring_metrics", ["host"])
    op.create_index("ix_monitoring_metrics_metric_name", "monitoring_metrics", ["metric_name"])
    op.create_index("ix_monitoring_metrics_recorded_at", "monitoring_metrics", ["recorded_at"])

    # ── backup_logs ──
    op.create_table(
        "backup_logs",
        _uuid_column("id", nullable=False),
        sa.Column("backup_type", sa.String(30), nullable=False),
        sa.Column("target", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backup_logs_status", "backup_logs", ["status"])

    # ── rate_limit_violations ──
    op.create_table(
        "rate_limit_violations",
        _uuid_column("id", nullable=False),
        _uuid_column("tenant_id", nullable=False),
        _uuid_column("user_id", nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("http_method", sa.String(10), nullable=False),
        sa.Column("limit_name", sa.String(100), nullable=False),
        sa.Column("limit_max", sa.Integer(), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("current_count", sa.Integer(), nullable=False),
        sa.Column("violated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_violations_tenant_id", "rate_limit_violations", ["tenant_id"])
    op.create_index("ix_rate_limit_violations_user_id", "rate_limit_violations", ["user_id"])
    op.create_index("ix_rate_limit_violations_endpoint", "rate_limit_violations", ["endpoint"])
    op.create_index("ix_rate_limit_violations_violated_at", "rate_limit_violations", ["violated_at"])
    _enable_tenant_rls("rate_limit_violations")

    # ── alert_rules ──
    op.create_table(
        "alert_rules",
        _uuid_column("id", nullable=False),
        _uuid_column("tenant_id", nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("condition", sa.String(20), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("evaluation_window_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notification_channels", postgresql.JSON(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_rules_tenant_id", "alert_rules", ["tenant_id"])
    op.create_index("ix_alert_rules_metric_name", "alert_rules", ["metric_name"])
    _enable_tenant_rls("alert_rules")


def downgrade() -> None:
    # RLS 정책 제거 후 테이블 삭제
    for table in ("alert_rules", "rate_limit_violations"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_table("alert_rules")
    op.drop_table("rate_limit_violations")
    op.drop_table("backup_logs")
    op.drop_table("monitoring_metrics")
