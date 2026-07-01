"""add g2b bid analysis history table (입찰 AI 분석 히스토리)

Revision ID: 021_g2b_bid_analysis
Revises: 020_g2b_bid
Create Date: 2026-06-02

입찰 AI 정밀분석 결과를 영속화해 재조회·재분석·삭제를 지원한다.
app/models/g2b_bid.py(G2BBidAnalysis)의 컬럼/인덱스와 1:1 동일.
(G2B 모델은 app.core.database.Base 레지스트리라 수동 작성.)
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "021_g2b_bid_analysis"
down_revision = "020_g2b_bid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "g2b_bid_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bid_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bid_notice_no", sa.String(length=50), nullable=True),
        sa.Column("bid_notice_nm", sa.Text(), nullable=True),
        sa.Column("params", postgresql.JSON(), nullable=True),
        sa.Column("recommended_bid_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("expected_roi", sa.Numeric(8, 3), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_g2b_bid_analyses_bid_id", "g2b_bid_analyses", ["bid_id"])
    op.create_index("ix_g2b_bid_analyses_created_at", "g2b_bid_analyses", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_g2b_bid_analyses_created_at", table_name="g2b_bid_analyses")
    op.drop_index("ix_g2b_bid_analyses_bid_id", table_name="g2b_bid_analyses")
    op.drop_table("g2b_bid_analyses")
