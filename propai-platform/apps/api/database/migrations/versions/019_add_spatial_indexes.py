"""공간 인덱스 추가 (PostGIS GIST).

Revision ID: 019_spatial
Revises: 018_v53_contract_generation
"""

from alembic import op

revision = "019_spatial"
down_revision = "018_v53_contract_generation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostGIS 확장 활성화 (이미 있으면 무시)
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # GIST 공간 인덱스
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_location_gist ON projects USING GIST (location)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_parcels_boundary_gist ON parcels USING GIST (boundary)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_parcels_boundary_gist")
    op.execute("DROP INDEX IF EXISTS ix_projects_location_gist")
