"""초기 스키마 — 15개 핵심 테이블 + RLS 정책 + TimescaleDB 하이퍼테이블.

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 1. tenants ──
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("encryption_key_id", sa.String(200), nullable=True, comment="AWS KMS 암호화 키 ID"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 2. users ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 3. projects ──
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("total_area_sqm", sa.Float(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # PostGIS geometry 컬럼 추가
    op.execute("SELECT AddGeometryColumn('projects', 'location', 4326, 'POINT', 2)")

    # ── 4. parcels ──
    op.create_table(
        "parcels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("pnu", sa.String(19), nullable=True, comment="필지고유번호"),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("land_use_zone", sa.String(100), nullable=True, comment="용도지역"),
        sa.Column("official_price", sa.Float(), nullable=True, comment="공시지가 (원/㎡)"),
        sa.Column("zoning_info", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("SELECT AddGeometryColumn('parcels', 'boundary', 4326, 'POLYGON', 2)")

    # ── 5. designs ──
    op.create_table(
        "designs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("design_type", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("thumbnail_url", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("total_area_sqm", sa.Float(), nullable=True),
        sa.Column("total_volume_m3", sa.Float(), nullable=True),
        sa.Column("element_count", sa.Integer(), nullable=True),
        sa.Column("room_count", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 6. regulations ──
    op.create_table(
        "regulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("regulation_type", sa.String(50), nullable=False),
        sa.Column("is_compliant", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("violations", postgresql.JSON(), nullable=True),
        sa.Column("recommendations", postgresql.JSON(), nullable=True),
        sa.Column("source_documents", postgresql.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 7. avm_valuations ──
    op.create_table(
        "avm_valuations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("estimated_price", sa.Float(), nullable=False),
        sa.Column("price_per_sqm", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("comparable_count", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("feature_importance", postgresql.JSON(), nullable=True),
        sa.Column("comparables", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 8. financial_analyses ──
    op.create_table(
        "financial_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("npv", sa.Float(), nullable=False),
        sa.Column("irr", sa.Float(), nullable=False),
        sa.Column("payback_period_months", sa.Integer(), nullable=False),
        sa.Column("total_investment", sa.Float(), nullable=False),
        sa.Column("total_revenue", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("scenario_name", sa.String(200), nullable=True),
        sa.Column("assumptions", postgresql.JSON(), nullable=True),
        sa.Column("cash_flow_yearly", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 9. construction_logs ──
    op.create_table(
        "construction_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("log_date", sa.Date(), nullable=False),
        sa.Column("weather", sa.String(50), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("worker_count", sa.Integer(), nullable=True),
        sa.Column("work_description", sa.Text(), nullable=True),
        sa.Column("equipment_used", postgresql.JSON(), nullable=True),
        sa.Column("issues", postgresql.JSON(), nullable=True),
        sa.Column("progress_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 10. drone_inspections ──
    op.create_table(
        "drone_inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("flight_id", sa.String(100), nullable=True),
        sa.Column("images_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("defects_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("defects", postgresql.JSON(), nullable=True),
        sa.Column("severity_summary", postgresql.JSON(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("detection_f1", sa.Float(), nullable=True),
        sa.Column("report_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 11. tax_calculations ──
    op.create_table(
        "tax_calculations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("tax_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("taxable_value", sa.Float(), nullable=False),
        sa.Column("tax_rate", sa.Float(), nullable=False),
        sa.Column("deductions", postgresql.JSON(), nullable=True),
        sa.Column("optimization_tips", postgresql.JSON(), nullable=True),
        sa.Column("scenario_name", sa.String(100), nullable=True),
        sa.Column("calculation_basis", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 12. escrow_transactions ──
    op.create_table(
        "escrow_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False, index=True,
        ),
        sa.Column("on_chain_escrow_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending_funding"),
        sa.Column("amount_wei", sa.String(78), nullable=False, server_default="0"),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.Column("contract_address", sa.String(42), nullable=True),
        sa.Column("buyer_address", sa.String(42), nullable=False),
        sa.Column("seller_address", sa.String(42), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=True),
        sa.Column("block_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 13. legal_audit_trail (INSERT-ONLY) ──
    op.create_table(
        "legal_audit_trail",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("before_state", postgresql.JSON(), nullable=True),
        sa.Column("after_state", postgresql.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 14. ai_usage_log ──
    op.create_table(
        "ai_usage_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service_name", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("request_summary", postgresql.JSON(), nullable=True),
        sa.Column("response_summary", postgresql.JSON(), nullable=True),
        sa.Column("is_cached", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 15. model_performance ──
    op.create_table(
        "model_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_name", sa.String(100), nullable=False, index=True),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("mlflow_run_id", sa.String(100), nullable=True),
        sa.Column("metrics", postgresql.JSON(), nullable=False),
        sa.Column("dataset_info", postgresql.JSON(), nullable=True),
        sa.Column("is_champion", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hyperparameters", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── 16. iot_carbon_sensors (TimescaleDB 하이퍼테이블) ──
    op.create_table(
        "iot_carbon_sensors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("sensor_id", sa.String(100), nullable=False),
        sa.Column("co2_ppm", sa.Float(), nullable=True),
        sa.Column("pm25", sa.Float(), nullable=True),
        sa.Column("pm10", sa.Float(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("humidity", sa.Float(), nullable=True),
        sa.Column("location", sa.String(200), nullable=True),
        sa.Column("raw_data", postgresql.JSON(), nullable=True),
    )

    # ── 17. drone_detection_events (TimescaleDB 하이퍼테이블) ──
    op.create_table(
        "drone_detection_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drone_inspections.id"), nullable=True),
        sa.Column("defect_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox_x", sa.Float(), nullable=True),
        sa.Column("bbox_y", sa.Float(), nullable=True),
        sa.Column("bbox_w", sa.Float(), nullable=True),
        sa.Column("bbox_h", sa.Float(), nullable=True),
        sa.Column("image_url", sa.String(500), nullable=True),
        sa.Column("gps_lat", sa.Float(), nullable=True),
        sa.Column("gps_lon", sa.Float(), nullable=True),
        sa.Column("gps_alt", sa.Float(), nullable=True),
    )

    # ══════════════════════════════════════
    # RLS (Row Level Security) 정책
    # ══════════════════════════════════════
    _rls_tables = [
        "users", "projects", "parcels", "designs", "regulations",
        "avm_valuations", "financial_analyses", "construction_logs",
        "drone_inspections", "tax_calculations", "escrow_transactions",
        "legal_audit_trail", "ai_usage_log",
        "iot_carbon_sensors", "drone_detection_events",
    ]
    for table in _rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
        """)

    # legal_audit_trail: INSERT-ONLY 정책 (수정/삭제 금지)
    op.execute("""
        CREATE POLICY audit_insert_only ON legal_audit_trail
        FOR INSERT WITH CHECK (true)
    """)


def downgrade() -> None:
    _rls_tables = [
        "drone_detection_events", "iot_carbon_sensors",
        "ai_usage_log", "legal_audit_trail",
        "escrow_transactions", "tax_calculations",
        "drone_inspections", "construction_logs",
        "financial_analyses", "avm_valuations",
        "regulations", "designs", "parcels",
        "projects", "users",
    ]
    for table in _rls_tables:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS audit_insert_only ON legal_audit_trail")

    op.drop_table("drone_detection_events")
    op.drop_table("iot_carbon_sensors")
    op.drop_table("model_performance")
    op.drop_table("ai_usage_log")
    op.drop_table("legal_audit_trail")
    op.drop_table("escrow_transactions")
    op.drop_table("tax_calculations")
    op.drop_table("drone_inspections")
    op.drop_table("construction_logs")
    op.drop_table("financial_analyses")
    op.drop_table("avm_valuations")
    op.drop_table("regulations")
    op.drop_table("designs")
    op.drop_table("parcels")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("tenants")
