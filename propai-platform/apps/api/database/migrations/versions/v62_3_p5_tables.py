"""v62 Part5 — 청약/옵션/대출/수납 13 테이블 + 인덱스

Revision ID: v62_3_p5_tables
Revises: v62_2_sales_rls
Create Date: 2026-06-03

[Q]청약5 [R]옵션2 [S]대출3 [U]수납3 = 13. 모델 메타데이터 기반 create_all(멱등).
RLS는 v62_2 패턴(미적용 보류)과 동일 정책으로 추후 일괄 적용(신규 sales_* 자동 포함).
"""
from alembic import op

revision = "v62_3_p5_tables"
down_revision = "v62_2_sales_rls"
branch_labels = None
depends_on = None

_NEW = {
    "sales_subscription_announcements", "sales_subscription_applications", "sales_subscription_winners",
    "sales_subscription_reserve_queue", "sales_unranked_offers",
    "sales_option_catalog", "sales_contract_options",
    "sales_loan_programs", "sales_loan_agreements", "sales_loan_disbursements",
    "sales_virtual_accounts", "sales_payments", "sales_overdue_interest",
}


def _tables():
    import apps.api.database.models.sales  # noqa: F401 (모델 등록)
    from apps.api.database.models.base import Base
    return [t for t in Base.metadata.sorted_tables if t.name in _NEW]


def upgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base
    Base.metadata.create_all(bind=bind, tables=_tables(), checkfirst=True)
    op.execute("CREATE INDEX IF NOT EXISTS idx_pay_contract ON sales_payments (site_id, contract_ext_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_va_enc ON sales_virtual_accounts (site_id, va_number_enc);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sub_app_ann ON sales_subscription_applications (announcement_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sub_reserve "
        "ON sales_subscription_reserve_queue (site_id, unit_type_id, reserve_no);"
    )


def downgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base
    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables())), checkfirst=True)
