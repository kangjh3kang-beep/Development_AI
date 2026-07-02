"""v62 Part6 — 보증/신탁·실거래/전매·수수료확장·세무 9 테이블

Revision ID: v62_4_p6_tables
Revises: v62_3_p5_tables
Create Date: 2026-06-03

[T]보증/신탁2 [V]실거래/전매3 [W]수수료확장2 [X]세무2 = 9. 모델 메타데이터 create_all(멱등).
P0 라이프사이클(Part5~6) 완료 → sales 88 테이블.
"""
from alembic import op

revision = "v62_4_p6_tables"
down_revision = "v62_3_p5_tables"
branch_labels = None
depends_on = None

_NEW = {
    "sales_guarantee_policies", "sales_trust_accounts",
    "sales_realtx_reports", "sales_resale_restrictions", "sales_resale_transfers",
    "sales_commission_payout_schedule", "sales_commission_holdback",
    "sales_tax_invoices", "sales_withholding_statements",
}


def _tables():
    import apps.api.database.models.sales  # noqa: F401
    from apps.api.database.models.base import Base
    return [t for t in Base.metadata.sorted_tables if t.name in _NEW]


def upgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base
    Base.metadata.create_all(bind=bind, tables=_tables(), checkfirst=True)
    op.execute("CREATE INDEX IF NOT EXISTS idx_realtx_contract ON sales_realtx_reports (site_id, contract_ext_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_resale_restr ON sales_resale_restrictions (site_id, unit_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_comm_sched_split ON sales_commission_payout_schedule (split_id, status);"
    )
    # 수수료 지급은 claim 승인 또는 마일스톤 스케줄(claim 없음) 2소스 → claim_id nullable
    op.execute("ALTER TABLE sales_commission_payouts ALTER COLUMN claim_id DROP NOT NULL;")


def downgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables())), checkfirst=True)
