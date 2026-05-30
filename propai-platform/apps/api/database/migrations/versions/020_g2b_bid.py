"""add g2b bid/award tables (나라장터 공공입찰)

Revision ID: 020_g2b_bid
Revises: 018_v57_completion
Create Date: 2026-05-31

G2B 입찰/낙찰 테이블. app/models/g2b_bid.py(G2BBid, G2BAwardStat)의 컬럼/인덱스와
1:1 동일하게 생성한다. (G2B 모델은 app.core.database.Base 레지스트리라 활성 alembic의
autogenerate 대상이 아니므로 수동 작성.)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "020_g2b_bid"
down_revision = "018_v57_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "g2b_bids",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # 공고 식별
        sa.Column("bid_notice_no", sa.String(length=50), nullable=False, unique=True),
        sa.Column("bid_notice_nm", sa.Text(), nullable=False),
        sa.Column("bid_notice_ord", sa.String(length=10), nullable=True),
        # 분류
        sa.Column("bid_type", sa.String(length=20), nullable=False),
        sa.Column("category_tags", postgresql.ARRAY(sa.String()), nullable=True),
        # 발주기관
        sa.Column("org_name", sa.String(length=200), nullable=False),
        sa.Column("org_type", sa.String(length=50), nullable=True),
        sa.Column("demand_org_name", sa.String(length=200), nullable=True),
        # 금액
        sa.Column("estimated_price", sa.Numeric(20, 0), nullable=True),
        sa.Column("budget_amount", sa.Numeric(20, 0), nullable=True),
        # 일정
        sa.Column("bid_begin_dt", sa.DateTime(), nullable=True),
        sa.Column("bid_close_dt", sa.DateTime(), nullable=True),
        sa.Column("open_dt", sa.DateTime(), nullable=True),
        sa.Column("notice_dt", sa.DateTime(), nullable=True),
        # 지역
        sa.Column("region_sido", sa.String(length=50), nullable=True),
        sa.Column("region_sigungu", sa.String(length=50), nullable=True),
        sa.Column("delivery_place", sa.Text(), nullable=True),
        # 입찰 조건
        sa.Column("bid_method", sa.String(length=50), nullable=True),
        sa.Column("contract_method", sa.String(length=50), nullable=True),
        sa.Column("qualification", sa.Text(), nullable=True),
        # 상태
        sa.Column("status", sa.String(length=30), nullable=True),
        # 낙찰 정보
        sa.Column("award_price", sa.Numeric(20, 0), nullable=True),
        sa.Column("award_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("award_company", sa.String(length=200), nullable=True),
        sa.Column("award_dt", sa.DateTime(), nullable=True),
        sa.Column("bid_count", sa.Integer(), nullable=True),
        # 나라장터 연결
        sa.Column("g2b_url", sa.Text(), nullable=True),
        # AI 분석
        sa.Column("ai_risk_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("ai_recommended_bid_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("ai_analysis_summary", sa.Text(), nullable=True),
        # 원본
        sa.Column("raw_data", postgresql.JSON(), nullable=True),
        # 타임스탬프
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_g2b_bids_bid_type", "g2b_bids", ["bid_type"])
    op.create_index("ix_g2b_bids_status", "g2b_bids", ["status"])
    op.create_index("ix_g2b_bids_region", "g2b_bids", ["region_sido", "region_sigungu"])
    op.create_index("ix_g2b_bids_bid_close_dt", "g2b_bids", ["bid_close_dt"])
    op.create_index("ix_g2b_bids_notice_dt", "g2b_bids", ["notice_dt"])

    op.create_table(
        "g2b_award_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stat_period", sa.String(length=10), nullable=False),
        sa.Column("bid_type", sa.String(length=20), nullable=False),
        sa.Column("region_sido", sa.String(length=50), nullable=True),
        sa.Column("avg_award_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("min_award_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("max_award_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("bid_count", sa.Integer(), nullable=True),
        sa.Column("avg_competition_ratio", sa.Numeric(6, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_g2b_award_stats_period_type", "g2b_award_stats", ["stat_period", "bid_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_g2b_award_stats_period_type", table_name="g2b_award_stats")
    op.drop_table("g2b_award_stats")
    op.drop_index("ix_g2b_bids_notice_dt", table_name="g2b_bids")
    op.drop_index("ix_g2b_bids_bid_close_dt", table_name="g2b_bids")
    op.drop_index("ix_g2b_bids_region", table_name="g2b_bids")
    op.drop_index("ix_g2b_bids_status", table_name="g2b_bids")
    op.drop_index("ix_g2b_bids_bid_type", table_name="g2b_bids")
    op.drop_table("g2b_bids")
