"""v62: projects 누락컬럼 보강 + design_stages/drawings 테이블 생성.

목적:
- projects ORM(Project)이 가진 컬럼 중 운영 DB에 없던 8개(pnu_codes·zone_type·
  max_bcr·max_far·max_height·building_type·floor_above·floor_below) 추가 →
  ORM 컬럼 불일치(UndefinedColumnError) 근본 해결.
- v61_design.py ORM(DesignStage·Drawing)에 대응하는 테이블 생성 → CAD 도면을
  design_versions 우회 없이 정식 저장 가능.

모두 IF NOT EXISTS 멱등. design_versions는 이미 존재하므로 건드리지 않는다.
"""

from __future__ import annotations

from alembic import op

revision = "021_v62_design_tables"
down_revision = "020_g2b_bid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1) projects 누락 컬럼 보강 ──
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS pnu_codes JSON")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS zone_type VARCHAR(100)")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS max_bcr NUMERIC(5,2)")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS max_far NUMERIC(6,2)")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS max_height NUMERIC(6,1)")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS building_type VARCHAR(50)")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS floor_above INTEGER")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS floor_below INTEGER")

    # ── 2) design_stages ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS design_stages (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL,
            project_id UUID NOT NULL REFERENCES projects(id),
            stage_no INTEGER NOT NULL,
            stage_name VARCHAR(50) NOT NULL,
            stage_status VARCHAR(30) DEFAULT 'pending',
            completion_pct NUMERIC(5,2) DEFAULT 0,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            permit_ref VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_design_stages_project ON design_stages(project_id)")

    # ── 3) drawings ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS drawings (
            id BIGSERIAL PRIMARY KEY,
            tenant_id UUID NOT NULL,
            project_id UUID NOT NULL REFERENCES projects(id),
            stage_id BIGINT REFERENCES design_stages(id),
            drawing_code VARCHAR(20) NOT NULL,
            drawing_type VARCHAR(50) NOT NULL,
            drawing_name VARCHAR(200),
            floor_level VARCHAR(20),
            direction VARCHAR(10),
            scale VARCHAR(20) DEFAULT '1:200',
            vector_data JSON DEFAULT '{}'::json,
            svg_content TEXT,
            dxf_path TEXT,
            ai_generated BOOLEAN DEFAULT true,
            ai_model VARCHAR(50) DEFAULT 'PropAI-v61',
            generation_params JSON DEFAULT '{}'::json,
            compliance_ok BOOLEAN,
            compliance_issues JSON DEFAULT '[]'::json,
            version INTEGER DEFAULT 1,
            is_latest BOOLEAN DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_drawings_project ON drawings(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_drawings_code ON drawings(project_id, drawing_code)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS drawings")
    op.execute("DROP TABLE IF EXISTS design_stages")
    # projects 컬럼은 데이터 보존 위해 downgrade에서 제거하지 않음(안전).
