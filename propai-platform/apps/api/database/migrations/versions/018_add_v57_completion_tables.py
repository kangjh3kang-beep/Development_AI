"""Add v57 completion tables.

Revision ID: 018_v57_completion
Revises: 017_v53_phase2_operations
Create Date: 2026-03-27

레퍼런스 이미지, 친환경 인증, 저탄소 대체자재, 이해관계자,
개발 워크플로, 평면도, CAD 요소 7개 테이블을 추가한다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "018_v57_completion"
down_revision: str | None = "019_spatial"
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



_NEW_TABLES = (
    "reference_images",
    "green_certifications",
    "low_carbon_alternatives",
    "stakeholders",
    "development_workflows",
    "floor_plans",
    "cad_elements",
)


def upgrade() -> None:
    # -- reference_images --
    op.create_table(
        "reference_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("image_url", sa.String(length=1000), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=1000), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("aspect_ratio", sa.Float(), nullable=True),
        sa.Column("brightness", sa.Float(), nullable=True),
        sa.Column("contrast", sa.Float(), nullable=True),
        sa.Column("style_tags", postgresql.JSON(), nullable=True),
        sa.Column("feature_vector_json", postgresql.JSON(), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False, server_default="upload"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_reference_images_tenant_id", "reference_images", ["tenant_id"])
    op.create_index("ix_reference_images_project_id", "reference_images", ["project_id"])

    # -- green_certifications --
    op.create_table(
        "green_certifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("cert_type", sa.String(length=30), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(length=10), nullable=False),
        sa.Column("category_scores_json", postgresql.JSON(), nullable=True),
        sa.Column("is_compliant", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_green_certifications_tenant_id", "green_certifications", ["tenant_id"])
    op.create_index("ix_green_certifications_project_id", "green_certifications", ["project_id"])

    # -- low_carbon_alternatives --
    op.create_table(
        "low_carbon_alternatives",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("original_material", sa.String(length=200), nullable=False),
        sa.Column("alternative_material", sa.String(length=200), nullable=False),
        sa.Column("original_gwp", sa.Float(), nullable=False),
        sa.Column("alternative_gwp", sa.Float(), nullable=False),
        sa.Column("reduction_pct", sa.Float(), nullable=False),
        sa.Column("cost_change_pct", sa.Float(), nullable=True),
        sa.Column("availability", sa.String(length=50), nullable=False, server_default="available"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_low_carbon_alternatives_tenant_id", "low_carbon_alternatives", ["tenant_id"])
    op.create_index("ix_low_carbon_alternatives_project_id", "low_carbon_alternatives", ["project_id"])

    # -- stakeholders --
    op.create_table(
        "stakeholders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("organization", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=300), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("responsibility", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
    )
    op.create_index("ix_stakeholders_tenant_id", "stakeholders", ["tenant_id"])
    op.create_index("ix_stakeholders_project_id", "stakeholders", ["project_id"])

    # -- development_workflows --
    op.create_table(
        "development_workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        sa.Column("workflow_name", sa.String(length=200), nullable=False),
        sa.Column("current_stage", sa.String(length=100), nullable=False, server_default="init"),
        sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stages_json", postgresql.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _uuid_column("assigned_to", nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
    )
    op.create_index("ix_development_workflows_tenant_id", "development_workflows", ["tenant_id"])
    op.create_index("ix_development_workflows_project_id", "development_workflows", ["project_id"])

    op.create_table(
        "floor_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("project_id"),
        _uuid_column("design_version_id", nullable=True),
        sa.Column("floor_number", sa.Integer(), nullable=False),
        sa.Column("floor_area_sqm", sa.Float(), nullable=True),
        sa.Column("floor_height_m", sa.Float(), nullable=False, server_default="3.3"),
        sa.Column("elements_json", postgresql.JSON(), nullable=True),
        sa.Column("is_ground_floor", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        # design_version_id: FK 없이 UUID 참조 (design_versions 테이블 독립 마이그레이션)
    )
    op.create_index("ix_floor_plans_tenant_id", "floor_plans", ["tenant_id"])
    op.create_index("ix_floor_plans_project_id", "floor_plans", ["project_id"])
    op.create_index("ix_floor_plans_design_version_id", "floor_plans", ["design_version_id"])


    # -- cad_elements --
    op.create_table(
        "cad_elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        _uuid_column("tenant_id"),
        _uuid_column("floor_plan_id"),
        sa.Column("element_type", sa.String(length=50), nullable=False),
        sa.Column("x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("y", sa.Float(), nullable=False, server_default="0"),
        sa.Column("width", sa.Float(), nullable=False, server_default="0"),
        sa.Column("height", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rotation_deg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("material", sa.String(length=100), nullable=True),
        sa.Column("properties_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["floor_plan_id"], ["floor_plans.id"]),
    )
    op.create_index("ix_cad_elements_tenant_id", "cad_elements", ["tenant_id"])
    op.create_index("ix_cad_elements_floor_plan_id", "cad_elements", ["floor_plan_id"])

    # RLS 활성화
    for table in _NEW_TABLES:
        _enable_tenant_rls(table)


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        _disable_tenant_rls(table)

    op.drop_table("cad_elements")
    op.drop_table("floor_plans")
    op.drop_table("development_workflows")
    op.drop_table("stakeholders")
    op.drop_table("low_carbon_alternatives")
    op.drop_table("green_certifications")
    op.drop_table("reference_images")
