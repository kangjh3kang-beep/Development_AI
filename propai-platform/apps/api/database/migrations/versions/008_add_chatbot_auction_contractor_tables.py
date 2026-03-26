"""Add chatbot, auction, and contractor tables.

Revision ID: 008_chatbot_auction_contractor
Revises: 007_part_g_foundation
Create Date: 2026-03-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_chatbot_auction_contractor"
down_revision: str | None = "007_part_g_foundation"
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
        "chatbot_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _uuid_column("tenant_id"),
        _uuid_column("project_id", nullable=True),
        _uuid_column("user_id"),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column(
            "title",
            sa.String(200),
            nullable=False,
            server_default=sa.text("'General advisory'"),
        ),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("context_json", postgresql.JSONB(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "model_name",
            sa.String(60),
            nullable=False,
            server_default=sa.text("'claude-sonnet-4-5'"),
        ),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_chatbot_sessions_tenant_id", "chatbot_sessions", ["tenant_id"])
    op.create_index("ix_chatbot_sessions_project_id", "chatbot_sessions", ["project_id"])
    op.create_index("ix_chatbot_sessions_user_id", "chatbot_sessions", ["user_id"])
    op.create_index("ix_chatbot_sessions_domain", "chatbot_sessions", ["domain"])

    op.create_table(
        "chatbot_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _uuid_column("session_id"),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls_json", postgresql.JSONB(), nullable=True),
        sa.Column("feedback_score", sa.Float(), nullable=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chatbot_sessions.id"]),
    )
    op.create_index("ix_chatbot_messages_session_id", "chatbot_messages", ["session_id"])

    op.create_table(
        "auction_listings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _uuid_column("tenant_id"),
        _uuid_column("project_id", nullable=True),
        sa.Column("auction_type", sa.String(30), nullable=False),
        sa.Column("case_number", sa.String(100), nullable=False),
        sa.Column("court_name", sa.String(100), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("property_type", sa.String(40), nullable=False),
        sa.Column("appraised_value_krw", sa.Float(), nullable=False),
        sa.Column("minimum_bid_krw", sa.Float(), nullable=False),
        sa.Column("bid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auction_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'scheduled'"),
        ),
        sa.Column("analysis_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_auction_listings_tenant_id", "auction_listings", ["tenant_id"])
    op.create_index("ix_auction_listings_project_id", "auction_listings", ["project_id"])
    op.create_index("ix_auction_listings_auction_type", "auction_listings", ["auction_type"])

    op.create_table(
        "contractors",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _uuid_column("tenant_id"),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("business_number", sa.String(20), nullable=False),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("specialties_json", postgresql.JSONB(), nullable=True),
        sa.Column("contact_name", sa.String(100), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("contact_email", sa.String(200), nullable=True),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_contractors_tenant_id", "contractors", ["tenant_id"])
    op.create_index("ix_contractors_business_number", "contractors", ["business_number"])
    op.create_index("ix_contractors_category", "contractors", ["category"])

    for table in ("chatbot_sessions", "auction_listings", "contractors"):
        _enable_tenant_rls(table)


def downgrade() -> None:
    for table in ("contractors", "auction_listings", "chatbot_sessions"):
        _disable_tenant_rls(table)

    op.drop_table("contractors")
    op.drop_table("auction_listings")
    op.drop_table("chatbot_messages")
    op.drop_table("chatbot_sessions")
