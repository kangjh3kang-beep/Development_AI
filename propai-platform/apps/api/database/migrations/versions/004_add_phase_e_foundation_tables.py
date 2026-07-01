"""Add Phase E foundation tables.

Revision ID: 004_phase_e_foundation
Revises: 003_notifications_esign
Create Date: 2026-03-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004_phase_e_foundation"
down_revision: str | None = "003_notifications_esign"
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
        "investment_underwritings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("total_cost_krw", sa.Float(), nullable=False),
        sa.Column("projected_revenue_krw", sa.Float(), nullable=False),
        sa.Column("acquisition_price_krw", sa.Float(), nullable=False),
        sa.Column("equity_krw", sa.Float(), nullable=False),
        sa.Column("debt_krw", sa.Float(), nullable=False),
        sa.Column("projected_profit_krw", sa.Float(), nullable=False),
        sa.Column("profit_margin_ratio", sa.Float(), nullable=False),
        sa.Column("debt_ratio", sa.Float(), nullable=False),
        sa.Column("equity_multiple", sa.Float(), nullable=False),
        sa.Column("jeonse_ratio", sa.Float(), nullable=True),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("recommendation", sa.String(length=30), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("key_risks", postgresql.JSON(), nullable=True),
        sa.Column("assumptions_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_investment_underwritings_tenant_id", "investment_underwritings", ["tenant_id"])
    op.create_index("ix_investment_underwritings_project_id", "investment_underwritings", ["project_id"])

    op.create_table(
        "lp_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("underwriting_id"),
        sa.Column("report_title", sa.String(length=255), nullable=False),
        sa.Column("report_version", sa.String(length=40), nullable=False, server_default="v1"),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("metrics_json", postgresql.JSON(), nullable=False),
        sa.Column("distribution_waterfall_json", postgresql.JSON(), nullable=True),
        sa.Column("generated_by", sa.String(length=100), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["underwriting_id"], ["investment_underwritings.id"]),
    )
    op.create_index("ix_lp_reports_tenant_id", "lp_reports", ["tenant_id"])
    op.create_index("ix_lp_reports_project_id", "lp_reports", ["project_id"])
    op.create_index("ix_lp_reports_underwriting_id", "lp_reports", ["underwriting_id"])

    op.create_table(
        "data_room_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("underwriting_id"),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=60), nullable=False),
        sa.Column("storage_url", sa.String(length=500), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tags_json", postgresql.JSON(), nullable=True),
        sa.Column("parsed_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["underwriting_id"], ["investment_underwritings.id"]),
    )
    op.create_index("ix_data_room_documents_tenant_id", "data_room_documents", ["tenant_id"])
    op.create_index("ix_data_room_documents_project_id", "data_room_documents", ["project_id"])
    op.create_index("ix_data_room_documents_underwriting_id", "data_room_documents", ["underwriting_id"])

    op.create_table(
        "compliance_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("check_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("findings_json", postgresql.JSON(), nullable=True),
        sa.Column("remediation_plan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_compliance_checks_tenant_id", "compliance_checks", ["tenant_id"])
    op.create_index("ix_compliance_checks_project_id", "compliance_checks", ["project_id"])

    op.create_table(
        "kyc_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("subject_name", sa.String(length=200), nullable=False),
        sa.Column("document_kind", sa.String(length=60), nullable=False),
        sa.Column("identifier_masked", sa.String(length=120), nullable=True),
        sa.Column("storage_url", sa.String(length=500), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_kyc_documents_tenant_id", "kyc_documents", ["tenant_id"])
    op.create_index("ix_kyc_documents_project_id", "kyc_documents", ["project_id"])

    op.create_table(
        "aml_screenings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("subject_name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False, server_default="internal"),
        sa.Column("match_status", sa.String(length=30), nullable=False, server_default="clear"),
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("matched_lists_json", postgresql.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_aml_screenings_tenant_id", "aml_screenings", ["tenant_id"])
    op.create_index("ix_aml_screenings_project_id", "aml_screenings", ["project_id"])

    op.create_table(
        "lease_abstractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("source_document_name", sa.String(length=255), nullable=False),
        sa.Column("tenant_name", sa.String(length=200), nullable=False),
        sa.Column("lease_type", sa.String(length=60), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=False),
        sa.Column("deposit_krw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("monthly_rent_krw", sa.Float(), nullable=False, server_default="0"),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("critical_terms_json", postgresql.JSON(), nullable=True),
        sa.Column("abstraction_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_lease_abstractions_tenant_id", "lease_abstractions", ["tenant_id"])
    op.create_index("ix_lease_abstractions_project_id", "lease_abstractions", ["project_id"])

    op.create_table(
        "lease_ifrs16_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("lease_abstraction_id"),
        sa.Column("discount_rate", sa.Float(), nullable=False),
        sa.Column("lease_term_months", sa.Integer(), nullable=False),
        sa.Column("rou_asset_krw", sa.Float(), nullable=False),
        sa.Column("lease_liability_krw", sa.Float(), nullable=False),
        sa.Column("payment_schedule_json", postgresql.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["lease_abstraction_id"], ["lease_abstractions.id"]),
    )
    op.create_index("ix_lease_ifrs16_schedules_tenant_id", "lease_ifrs16_schedules", ["tenant_id"])
    op.create_index("ix_lease_ifrs16_schedules_project_id", "lease_ifrs16_schedules", ["project_id"])
    op.create_index(
        "ix_lease_ifrs16_schedules_lease_abstraction_id",
        "lease_ifrs16_schedules",
        ["lease_abstraction_id"],
    )

    op.create_table(
        "esg_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("reporting_period", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="draft"),
        sa.Column("environmental_score", sa.Float(), nullable=True),
        sa.Column("social_score", sa.Float(), nullable=True),
        sa.Column("governance_score", sa.Float(), nullable=True),
        sa.Column("disclosures_json", postgresql.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_esg_reports_tenant_id", "esg_reports", ["tenant_id"])
    op.create_index("ix_esg_reports_project_id", "esg_reports", ["project_id"])

    op.create_table(
        "carbon_footprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("scope1_tco2e", sa.Float(), nullable=False, server_default="0"),
        sa.Column("scope2_tco2e", sa.Float(), nullable=False, server_default="0"),
        sa.Column("scope3_tco2e", sa.Float(), nullable=False, server_default="0"),
        sa.Column("intensity_kgco2e_per_sqm", sa.Float(), nullable=True),
        sa.Column("baseline_year", sa.Integer(), nullable=True),
        sa.Column("breakdown_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_carbon_footprints_tenant_id", "carbon_footprints", ["tenant_id"])
    op.create_index("ix_carbon_footprints_project_id", "carbon_footprints", ["project_id"])

    op.create_table(
        "gresb_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("assessment_year", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rating", sa.String(length=10), nullable=True),
        sa.Column("gaps_json", postgresql.JSON(), nullable=True),
        sa.Column("action_plan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_gresb_assessments_tenant_id", "gresb_assessments", ["tenant_id"])
    op.create_index("ix_gresb_assessments_project_id", "gresb_assessments", ["project_id"])

    op.create_table(
        "climate_risk_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("construction_period_months", sa.Integer(), nullable=False),
        sa.Column("flood_risk_score", sa.Float(), nullable=False),
        sa.Column("heat_risk_score", sa.Float(), nullable=False),
        sa.Column("overall_risk_level", sa.String(length=20), nullable=False),
        sa.Column("annual_expected_loss_krw", sa.Float(), nullable=False),
        sa.Column("risk_factors", postgresql.JSON(), nullable=True),
        sa.Column("mitigation_tips", postgresql.JSON(), nullable=True),
        sa.Column("scenario_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_climate_risk_assessments_tenant_id", "climate_risk_assessments", ["tenant_id"])
    op.create_index("ix_climate_risk_assessments_project_id", "climate_risk_assessments", ["project_id"])

    op.create_table(
        "insurance_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("climate_risk_assessment_id"),
        sa.Column("coverage_type", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("annual_premium_estimate_krw", sa.Float(), nullable=False),
        sa.Column("coverage_limit_krw", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("broker_notes_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["climate_risk_assessment_id"], ["climate_risk_assessments.id"]),
    )
    op.create_index("ix_insurance_recommendations_tenant_id", "insurance_recommendations", ["tenant_id"])
    op.create_index("ix_insurance_recommendations_project_id", "insurance_recommendations", ["project_id"])
    op.create_index(
        "ix_insurance_recommendations_climate_risk_assessment_id",
        "insurance_recommendations",
        ["climate_risk_assessment_id"],
    )

    for table in (
        "investment_underwritings",
        "lp_reports",
        "data_room_documents",
        "compliance_checks",
        "kyc_documents",
        "aml_screenings",
        "lease_abstractions",
        "lease_ifrs16_schedules",
        "esg_reports",
        "carbon_footprints",
        "gresb_assessments",
        "climate_risk_assessments",
        "insurance_recommendations",
    ):
        _enable_tenant_rls(table)


def downgrade() -> None:
    tables = (
        "insurance_recommendations",
        "climate_risk_assessments",
        "gresb_assessments",
        "carbon_footprints",
        "esg_reports",
        "lease_ifrs16_schedules",
        "lease_abstractions",
        "aml_screenings",
        "kyc_documents",
        "compliance_checks",
        "data_room_documents",
        "lp_reports",
        "investment_underwritings",
    )

    for table in tables:
        _disable_tenant_rls(table)

    op.drop_table("insurance_recommendations")
    op.drop_table("climate_risk_assessments")
    op.drop_table("gresb_assessments")
    op.drop_table("carbon_footprints")
    op.drop_table("esg_reports")
    op.drop_table("lease_ifrs16_schedules")
    op.drop_table("lease_abstractions")
    op.drop_table("aml_screenings")
    op.drop_table("kyc_documents")
    op.drop_table("compliance_checks")
    op.drop_table("data_room_documents")
    op.drop_table("lp_reports")
    op.drop_table("investment_underwritings")
