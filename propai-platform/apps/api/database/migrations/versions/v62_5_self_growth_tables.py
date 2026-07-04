"""v62 자가성장 엔진 Phase 1 — 텔레메트리 3 테이블(정본).

Revision ID: v62_5_self_growth_tables
Revises: 024_project_analysis_snapshot
Create Date: 2026-06-14

platform_events(원시 이벤트·append-only·bigserial) /
platform_insights(배치 분석결과) / ai_feedback(사용자 교정·학습신호).
ORM(database/models/platform_event.py) 메타데이터로 create_all(멱등) +
인덱스/UNIQUE 명시 생성. schema_guard 와 정합(부팅 멱등 안전망은 별도).

down_revision 은 현재 v62 lineage tip(024_project_analysis_snapshot)에 연결.
"""
from alembic import op

revision = "v62_5_self_growth_tables"
down_revision = "024_project_analysis_snapshot"
branch_labels = None
depends_on = None

_NEW = {"platform_events", "platform_insights", "ai_feedback"}


def _tables():
    import apps.api.database.models.platform_event  # noqa: F401
    from apps.api.database.models.base import Base
    return [t for t in Base.metadata.sorted_tables if t.name in _NEW]


def upgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base
    # 테이블 + (ORM __table_args__ 의) 인덱스/UNIQUE 를 멱등 생성.
    Base.metadata.create_all(bind=bind, tables=_tables(), checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables())), checkfirst=True)
