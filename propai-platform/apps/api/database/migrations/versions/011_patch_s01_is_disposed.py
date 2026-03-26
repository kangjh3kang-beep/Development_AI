"""S01: properties 테이블 is_disposed 컬럼 추가"""
revision = "011_patch_s01_is_disposed"
down_revision = "010_v49_phase2"

from alembic import op  # noqa: E402


def upgrade():
    op.execute("""
        ALTER TABLE projects
        ADD COLUMN IF NOT EXISTS is_disposed BOOLEAN NOT NULL DEFAULT false;
    """)
    op.execute("""
        COMMENT ON COLUMN projects.is_disposed
        IS '처분 여부 (양도소득세 1세대1주택 판단 기준)';
    """)

def downgrade():
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS is_disposed;")
