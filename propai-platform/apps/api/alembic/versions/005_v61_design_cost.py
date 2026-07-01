"""v61 설계도면 + BIM 공사비 테이블 13개 + Project 확장 컬럼 8개

Revision ID: 005
Revises: 004
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 설계 도메인 ──

    op.create_table(
        "design_stages",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("stage_no", sa.Integer, nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("stage_status", sa.String(30), server_default="pending"),
        sa.Column("completion_pct", sa.Numeric(5, 2), server_default="0"),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("permit_ref", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "stage_no", name="uq_design_stage_project_stage"),
    )

    op.create_table(
        "drawings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("stage_id", sa.BigInteger, sa.ForeignKey("design_stages.id"), nullable=True),
        sa.Column("drawing_code", sa.String(20), nullable=False),
        sa.Column("drawing_type", sa.String(50), nullable=False),
        sa.Column("drawing_name", sa.String(200), nullable=True),
        sa.Column("floor_level", sa.String(20), nullable=True),
        sa.Column("direction", sa.String(10), nullable=True),
        sa.Column("scale", sa.String(20), server_default="1:200"),
        sa.Column("vector_data", JSON, server_default="{}"),
        sa.Column("svg_content", sa.Text, nullable=True),
        sa.Column("dxf_path", sa.Text, nullable=True),
        sa.Column("ai_generated", sa.Boolean, server_default="true"),
        sa.Column("ai_model", sa.String(50), server_default="PropAI-v61"),
        sa.Column("generation_params", JSON, server_default="{}"),
        sa.Column("compliance_ok", sa.Boolean, nullable=True),
        sa.Column("compliance_issues", JSON, server_default="[]"),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("is_latest", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "drawing_layers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("drawing_id", sa.BigInteger, sa.ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("layer_name", sa.String(100), nullable=False),
        sa.Column("layer_color", sa.String(20), server_default="#000000"),
        sa.Column("layer_weight", sa.Numeric(4, 1), server_default="0.25"),
        sa.Column("layer_visible", sa.Boolean, server_default="true"),
        sa.Column("layer_locked", sa.Boolean, server_default="false"),
        sa.Column("layer_order", sa.Integer, server_default="0"),
        sa.Column("elements", JSON, server_default="[]"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "drawing_edit_histories",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("drawing_id", sa.BigInteger, sa.ForeignKey("drawings.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("edit_type", sa.String(50), nullable=False),
        sa.Column("element_type", sa.String(50), nullable=True),
        sa.Column("layer_name", sa.String(100), nullable=True),
        sa.Column("before_data", JSON, nullable=True),
        sa.Column("after_data", JSON, nullable=True),
        sa.Column("edit_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "permit_document_sets",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("doc_code", sa.String(20), nullable=False),
        sa.Column("doc_category", sa.String(10), nullable=False),
        sa.Column("doc_name", sa.String(200), nullable=False),
        sa.Column("drawing_id", sa.BigInteger, sa.ForeignKey("drawings.id"), nullable=True),
        sa.Column("is_required", sa.Boolean, server_default="true"),
        sa.Column("is_completed", sa.Boolean, server_default="false"),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("submission_date", sa.Date, nullable=True),
        sa.Column("review_result", sa.String(50), nullable=True),
        sa.Column("review_comment", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "doc_code", name="uq_permit_doc_project_code"),
    )

    op.create_table(
        "design_alternatives",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("alt_no", sa.Integer, nullable=False),
        sa.Column("alt_name", sa.String(100), nullable=True),
        sa.Column("floor_area_ratio", sa.Numeric(6, 2), nullable=True),
        sa.Column("building_coverage", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_floor_area", sa.Numeric(12, 2), nullable=True),
        sa.Column("sellable_area", sa.Numeric(12, 2), nullable=True),
        sa.Column("estimated_revenue", sa.Numeric(18, 2), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(18, 2), nullable=True),
        sa.Column("profit_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("ai_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("legal_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("profit_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("design_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("esg_score", sa.Numeric(4, 1), nullable=True),
        sa.Column("is_selected", sa.Boolean, server_default="false"),
        sa.Column("selection_reason", sa.Text, nullable=True),
        sa.Column("mc_win_rate", sa.Numeric(5, 1), nullable=True),
        sa.Column("drawings", JSON, server_default="[]"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "alt_no", name="uq_design_alt_project_no"),
    )

    # ── 공사비 도메인 ──

    op.create_table(
        "cost_work_types",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("work_code", sa.String(20), nullable=False),
        sa.Column("work_name", sa.String(200), nullable=False),
        sa.Column("parent_code", sa.String(20), nullable=True),
        sa.Column("work_level", sa.Integer, server_default="1"),
        sa.Column("work_category", sa.String(50), nullable=False),
        sa.Column("work_division", sa.String(50), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("is_subtotal", sa.Boolean, server_default="false"),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "material_unit_prices",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("material_code", sa.String(50), nullable=False, index=True),
        sa.Column("material_name", sa.String(300), nullable=False),
        sa.Column("spec", sa.String(300), nullable=True),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("material_price", sa.Numeric(18, 2), server_default="0"),
        sa.Column("labor_price", sa.Numeric(18, 2), server_default="0"),
        sa.Column("expense_price", sa.Numeric(18, 2), server_default="0"),
        sa.Column("price_basis_year", sa.Integer, server_default="2026"),
        sa.Column("price_source", sa.String(100), server_default="표준품셈2025"),
        sa.Column("region", sa.String(50), server_default="경기도"),
        sa.Column("valid_from", sa.Date, nullable=True),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("is_current", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "bim_quantities",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True),
        sa.Column("ifc_global_id", sa.String(100), nullable=True, index=True),
        sa.Column("ifc_object_type", sa.String(100), nullable=True),
        sa.Column("ifc_object_name", sa.String(300), nullable=True),
        sa.Column("work_code", sa.String(20), nullable=True),
        sa.Column("floor_level", sa.String(50), nullable=True),
        sa.Column("zone", sa.String(100), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), server_default="0"),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("quantity_formula", sa.Text, nullable=True),
        sa.Column("extraction_method", sa.String(50), server_default="AI_AUTO"),
        sa.Column("verified", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "cost_calculation_sheets",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("work_category", sa.String(50), nullable=False),
        sa.Column("direct_material_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("indirect_material_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("direct_labor_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("indirect_labor_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("direct_expense", sa.Numeric(18, 2), server_default="0"),
        sa.Column("industrial_acc_ins", sa.Numeric(18, 2), server_default="0"),
        sa.Column("employment_ins", sa.Numeric(18, 2), server_default="0"),
        sa.Column("health_ins", sa.Numeric(18, 2), server_default="0"),
        sa.Column("pension_ins", sa.Numeric(18, 2), server_default="0"),
        sa.Column("lcare_ins", sa.Numeric(18, 2), server_default="0"),
        sa.Column("retirement_fund", sa.Numeric(18, 2), server_default="0"),
        sa.Column("safety_health_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("env_preserve_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("general_mgmt_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("profit_amount", sa.Numeric(18, 2), server_default="0"),
        sa.Column("vat_amount", sa.Numeric(18, 2), server_default="0"),
        sa.Column("total_project_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("applied_rates_snapshot", JSON, server_default="{}"),
        sa.Column("rates_applied_date", sa.Date, nullable=True),
        sa.Column("calc_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "progress_billings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("billing_no", sa.Integer, nullable=False),
        sa.Column("period_from", sa.Date, nullable=True),
        sa.Column("period_to", sa.Date, nullable=True),
        sa.Column("work_entries", JSON, server_default="[]"),
        sa.Column("planned_value", sa.Numeric(18, 2), server_default="0"),
        sa.Column("earned_value", sa.Numeric(18, 2), server_default="0"),
        sa.Column("actual_cost", sa.Numeric(18, 2), server_default="0"),
        sa.Column("evm_spi", sa.Float, nullable=True),
        sa.Column("evm_cpi", sa.Float, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "legal_rate_histories",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("rate_category", sa.String(50), nullable=False, index=True),
        sa.Column("rate_value", sa.Numeric(8, 6), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("gov_notice_no", sa.String(100), nullable=True),
        sa.Column("gov_notice_url", sa.Text, nullable=True),
        sa.Column("source_api", sa.String(200), nullable=True),
        sa.Column("applied_to", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "standard_price_updates",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("price_period", sa.String(20), nullable=False),
        sa.Column("update_type", sa.String(30), nullable=False),
        sa.Column("gov_notice_no", sa.String(100), nullable=True),
        sa.Column("effective_from", sa.Date, nullable=True),
        sa.Column("price_count", sa.Integer, server_default="0"),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("processed", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── Project 확장 컬럼 ──

    op.add_column("projects", sa.Column("pnu_codes", JSON, nullable=True))
    op.add_column("projects", sa.Column("zone_type", sa.String(100), nullable=True))
    op.add_column("projects", sa.Column("max_bcr", sa.Numeric(5, 2), nullable=True))
    op.add_column("projects", sa.Column("max_far", sa.Numeric(6, 2), nullable=True))
    op.add_column("projects", sa.Column("max_height", sa.Numeric(6, 1), nullable=True))
    op.add_column("projects", sa.Column("building_type", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("floor_above", sa.Integer, nullable=True))
    op.add_column("projects", sa.Column("floor_below", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "floor_below")
    op.drop_column("projects", "floor_above")
    op.drop_column("projects", "building_type")
    op.drop_column("projects", "max_height")
    op.drop_column("projects", "max_far")
    op.drop_column("projects", "max_bcr")
    op.drop_column("projects", "zone_type")
    op.drop_column("projects", "pnu_codes")

    op.drop_table("standard_price_updates")
    op.drop_table("legal_rate_histories")
    op.drop_table("progress_billings")
    op.drop_table("cost_calculation_sheets")
    op.drop_table("bim_quantities")
    op.drop_table("material_unit_prices")
    op.drop_table("cost_work_types")
    op.drop_table("design_alternatives")
    op.drop_table("permit_document_sets")
    op.drop_table("drawing_edit_histories")
    op.drop_table("drawing_layers")
    op.drop_table("drawings")
    op.drop_table("design_stages")
