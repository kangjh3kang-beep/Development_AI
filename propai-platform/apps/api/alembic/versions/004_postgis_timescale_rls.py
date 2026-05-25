"""PostGIS + TimescaleDB + RLS 마이그레이션."""
revision = "004"
down_revision = "003"


def upgrade():
    """PostGIS, TimescaleDB 확장 활성화 및 RLS 정책 적용."""
    sq = chr(39)
    sql_statements = [
        "CREATE EXTENSION IF NOT EXISTS postgis;",
        "CREATE EXTENSION IF NOT EXISTS timescaledb;",
        "ALTER TABLE projects ENABLE ROW LEVEL SECURITY;",
        (
            "CREATE POLICY tenant_isolation_projects ON projects "
            f"USING (tenant_id = current_setting({sq}app.current_tenant{sq})::uuid);"
        ),
    ]
    return sql_statements


def downgrade():
    """RLS 정책 롤백."""
    return [
        "DROP POLICY IF EXISTS tenant_isolation_projects ON projects;",
        "ALTER TABLE projects DISABLE ROW LEVEL SECURITY;",
    ]
