"""Add Part G foundation tables.

Revision ID: 007_part_g_foundation
Revises: 006_part_f_foundation
Create Date: 2026-03-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "007_part_g_foundation"
down_revision: str | None = "006_part_f_foundation"
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
        "ai_cost_budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("monthly_budget_usd", sa.Float(), nullable=False),
        sa.Column("alert_threshold_ratio", sa.Float(), nullable=False, server_default="0.8"),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_ai_cost_budgets_tenant_id", "ai_cost_budgets", ["tenant_id"])
    op.create_index("ix_ai_cost_budgets_endpoint", "ai_cost_budgets", ["endpoint"])
    op.create_index("ix_ai_cost_budgets_month", "ai_cost_budgets", ["month"])

    op.create_table(
        "portal_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("portal_name", sa.String(length=60), nullable=False),
        sa.Column("region_code", sa.String(length=20), nullable=False),
        sa.Column("listing_title", sa.String(length=255), nullable=False),
        sa.Column("listing_external_id", sa.String(length=200), nullable=False),
        sa.Column("listing_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("property_type", sa.String(length=40), nullable=False),
        sa.Column("price_krw", sa.Float(), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("images_json", postgresql.JSON(), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_portal_listings_tenant_id", "portal_listings", ["tenant_id"])
    op.create_index("ix_portal_listings_project_id", "portal_listings", ["project_id"])
    op.create_index("ix_portal_listings_portal_name", "portal_listings", ["portal_name"])
    op.create_index("ix_portal_listings_region_code", "portal_listings", ["region_code"])

    op.create_table(
        "portal_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("listing_id"),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inquiry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("click_through_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bookmark_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ranking_position", sa.Integer(), nullable=True),
        sa.Column("metrics_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["portal_listings.id"]),
    )
    op.create_index("ix_portal_performance_tenant_id", "portal_performance", ["tenant_id"])
    op.create_index("ix_portal_performance_project_id", "portal_performance", ["project_id"])
    op.create_index("ix_portal_performance_listing_id", "portal_performance", ["listing_id"])

    op.create_table(
        "multilingual_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("report_type", sa.String(length=60), nullable=False),
        sa.Column("source_language", sa.String(length=10), nullable=False, server_default="ko"),
        sa.Column("target_language", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("translated_text", sa.Text(), nullable=False),
        sa.Column("translation_engine", sa.String(length=60), nullable=False, server_default="deterministic-template"),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_multilingual_reports_tenant_id", "multilingual_reports", ["tenant_id"])
    op.create_index("ix_multilingual_reports_project_id", "multilingual_reports", ["project_id"])
    op.create_index("ix_multilingual_reports_target_language", "multilingual_reports", ["target_language"])

    op.create_table(
        "translation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("report_id", nullable=True),
        sa.Column("source_language", sa.String(length=10), nullable=False, server_default="ko"),
        sa.Column("target_language", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["multilingual_reports.id"]),
    )
    op.create_index("ix_translation_jobs_tenant_id", "translation_jobs", ["tenant_id"])
    op.create_index("ix_translation_jobs_project_id", "translation_jobs", ["project_id"])
    op.create_index("ix_translation_jobs_report_id", "translation_jobs", ["report_id"])

    op.create_table(
        "kepco_rate_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        sa.Column("contract_type", sa.String(length=40), nullable=False),
        sa.Column("energy_rate_krw_per_kwh", sa.Float(), nullable=False),
        sa.Column("base_charge_krw_per_kw", sa.Float(), nullable=False),
        sa.Column("fuel_adjustment_krw_per_kwh", sa.Float(), nullable=False, server_default="5"),
        sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_kepco_rate_cache_tenant_id", "kepco_rate_cache", ["tenant_id"])
    op.create_index("ix_kepco_rate_cache_contract_type", "kepco_rate_cache", ["contract_type"])

    op.create_table(
        "energy_certifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("energy_grade", sa.String(length=20), nullable=False),
        sa.Column("zeb_grade", sa.String(length=20), nullable=False),
        sa.Column("annual_energy_demand_kwh", sa.Float(), nullable=False),
        sa.Column("annual_renewable_generation_kwh", sa.Float(), nullable=False),
        sa.Column("energy_independence_rate", sa.Float(), nullable=False),
        sa.Column("bems_saving_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bems_saving_kwh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recommendations_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_energy_certifications_tenant_id", "energy_certifications", ["tenant_id"])
    op.create_index("ix_energy_certifications_project_id", "energy_certifications", ["project_id"])

    op.create_table(
        "energy_cert_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("certification_id"),
        sa.Column("score_name", sa.String(length=60), nullable=False),
        sa.Column("score_value", sa.Float(), nullable=False),
        sa.Column("details_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["certification_id"], ["energy_certifications.id"]),
    )
    op.create_index("ix_energy_cert_scores_tenant_id", "energy_cert_scores", ["tenant_id"])
    op.create_index("ix_energy_cert_scores_project_id", "energy_cert_scores", ["project_id"])
    op.create_index("ix_energy_cert_scores_certification_id", "energy_cert_scores", ["certification_id"])

    for table in (
        "ai_cost_budgets",
        "portal_listings",
        "portal_performance",
        "multilingual_reports",
        "translation_jobs",
        "kepco_rate_cache",
        "energy_certifications",
        "energy_cert_scores",
    ):
        _enable_tenant_rls(table)


def downgrade() -> None:
    tables = (
        "energy_cert_scores",
        "energy_certifications",
        "kepco_rate_cache",
        "translation_jobs",
        "multilingual_reports",
        "portal_performance",
        "portal_listings",
        "ai_cost_budgets",
    )
    for table in tables:
        _disable_tenant_rls(table)

    op.drop_table("energy_cert_scores")
    op.drop_table("energy_certifications")
    op.drop_table("kepco_rate_cache")
    op.drop_table("translation_jobs")
    op.drop_table("multilingual_reports")
    op.drop_table("portal_performance")
    op.drop_table("portal_listings")
    op.drop_table("ai_cost_budgets")
