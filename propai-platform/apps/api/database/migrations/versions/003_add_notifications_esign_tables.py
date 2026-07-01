"""Add notifications and e-sign tables.

Revision ID: 003_notifications_esign
Revises: 002_auth_webhook
Create Date: 2026-03-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003_notifications_esign"
down_revision: str | None = "002_auth_webhook"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True, index=True),
        sa.Column("channel", sa.String(50), nullable=False, server_default="alimtalk"),
        sa.Column("recipient_phone", sa.String(30), nullable=False),
        sa.Column("template_code", sa.String(100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", postgresql.JSON(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="sent"),
        sa.Column("external_ref", sa.String(100), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "esign_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True, index=True),
        sa.Column("document_name", sa.String(255), nullable=False),
        sa.Column("document_url", sa.String(500), nullable=False),
        sa.Column("signer_name", sa.String(100), nullable=False),
        sa.Column("signer_email", sa.String(255), nullable=False),
        sa.Column("signer_phone", sa.String(30), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False, server_default="mock"),
        sa.Column("status", sa.String(50), nullable=False, server_default="requested"),
        sa.Column("external_request_id", sa.String(100), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    for table in ("notification_messages", "esign_requests"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id = current_setting('app.current_tenant', true)::uuid)"
        )


def downgrade() -> None:
    for table in ("esign_requests", "notification_messages"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_table("esign_requests")
    op.drop_table("notification_messages")
