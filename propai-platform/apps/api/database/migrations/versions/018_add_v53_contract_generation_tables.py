"""Add v53 contract generation draft table.

Revision ID: 018_v53_contract_generation
Revises: 017_v53_phase2_operations
Create Date: 2026-03-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "018_v53_contract_generation"
down_revision: str | None = "017_v53_phase2_operations"
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
        "generated_contract_drafts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("esign_request_id", nullable=True),
        sa.Column("contract_type", sa.String(length=50), nullable=False),
        sa.Column("target_language", sa.String(length=10), nullable=False, server_default="ko"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("counterparty_name", sa.String(length=120), nullable=False),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contract_amount_krw", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_terms_json", postgresql.JSON(), nullable=True),
        sa.Column("clauses_json", postgresql.JSON(), nullable=True),
        sa.Column("rendered_markdown", sa.Text(), nullable=False),
        sa.Column("document_url", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column(
            "sign_status",
            sa.String(length=30),
            nullable=False,
            server_default="not_requested",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["esign_request_id"], ["esign_requests.id"]),
    )
    op.create_index(
        "ix_generated_contract_drafts_tenant_id",
        "generated_contract_drafts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_generated_contract_drafts_project_id",
        "generated_contract_drafts",
        ["project_id"],
    )
    op.create_index(
        "ix_generated_contract_drafts_esign_request_id",
        "generated_contract_drafts",
        ["esign_request_id"],
    )

    _enable_tenant_rls("generated_contract_drafts")


def downgrade() -> None:
    _disable_tenant_rls("generated_contract_drafts")
    op.drop_table("generated_contract_drafts")
