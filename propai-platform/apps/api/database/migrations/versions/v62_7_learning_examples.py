"""v62 자가성장 엔진 Phase 5 — learning_examples(L3 자가학습 few-shot 큐레이션, 정본).

Revision ID: v62_7_learning_examples
Revises: v62_6_platform_settings
Create Date: 2026-06-14

learning_examples: ai_feedback(verdict=up)·verify_result(pass)·analysis_ledger 신호로
큐레이션한 few-shot 후보 예시 풀.
- input_summary  : 익명화(PII 마스킹)한 입력 요약(원본 미저장).
- good_output    : 고평가 출력 요약.
- service        : base_interpreter.name(귀속 서비스).
- analysis_type  : analysis_ledger.analysis_type 와 정합(원장 연결).
- source_feedback_id : 출처 ai_feedback.id(추적용).
- content_hash   : analysis_ledger.content_hash 조인키(버전별 결과 추적).
- status         : candidate(자동 등록 기본) | active(사람 승인 후) | rejected.
                   ★자동 활성화 금지 — promote API(사람 승인)로만 candidate→active.

down_revision 은 Phase 3 platform_settings(v62_6_platform_settings)에 연결.
schema_guard.ensure_schema 가 부팅 멱등 안전망을 별도 제공(정본은 이 마이그레이션).
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "v62_7_learning_examples"
down_revision = "v62_6_platform_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "learning_examples" in insp.get_table_names():
        return
    op.create_table(
        "learning_examples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("good_output", sa.Text(), nullable=True),
        sa.Column("service", sa.Text(), nullable=True),
        sa.Column("analysis_type", sa.Text(), nullable=True),
        sa.Column("source_feedback_id", postgresql.UUID(as_uuid=True), nullable=True),
        # 동일 (service, content_hash) 사례 중복등록 차단용 멱등키.
        sa.Column("content_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'candidate'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("idx_le_service_status", "learning_examples", ["service", "status"])
    op.create_index("idx_le_created", "learning_examples", ["created_at"])
    # (service, content_hash) 멱등 — 같은 사례를 매주 배치가 중복 적재하지 않음.
    # content_hash NULL 은 UNIQUE 충돌하지 않으므로(없는 사례) 안전.
    op.create_index("uq_le_service_hash", "learning_examples",
                    ["service", "content_hash"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "learning_examples" not in insp.get_table_names():
        return
    op.drop_index("uq_le_service_hash", table_name="learning_examples")
    op.drop_index("idx_le_created", table_name="learning_examples")
    op.drop_index("idx_le_service_status", table_name="learning_examples")
    op.drop_table("learning_examples")
