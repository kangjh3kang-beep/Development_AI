"""분양 관리자 콘솔 회계/급여 테이블 — 런타임 DDL 정본화 + 자동전기 멱등키.

Revision ID: 032_sales_admin_accounting
Revises: (merge) v62_7_learning_examples, 031_analysis_ledger
Create Date: 2026-06-18

기존에 console.py 가 런타임 CREATE TABLE/ALTER(IF NOT EXISTS)로 생성하던
sales_site_accounting / sales_staff_wage 를 마이그레이션 정본으로 이관한다.
(런타임 DDL 은 advisory-lock 으로 race 만 제거하고, 정본은 본 마이그레이션이다.)

★헤드 통합(코드 검증 완료): 본 리비전 직전 alembic 히스토리는 정확히 두 헤드로
  분기되어 있었다 — v62_7_learning_examples(자가성장 체인)·031_analysis_ledger(협업/원장 체인).
  본 리비전이 두 헤드를 동시에 down_revision 튜플로 받아 단일 헤드(032_sales_admin_accounting)
  로 머지한다(upgrade head 정상화).
  검증 사실(마이그레이션 그래프 정적분석, 2026-06-18): 본 리비전 포함 시 head=1(032),
  미존재 down_revision 참조=0건, 사이클=0. 본 리비전 제외 시 head=2(031_analysis_ledger,
  v62_7_learning_examples). 따라서 추가 merge 리비전(033)은 불필요하다(만들면 오히려 헤드를
  다시 분기시킨다). 과거 '5 헤드·누락참조 3건' 보고는 본 032 적용 전후 상태와 불일치하는
  stale 진단이며, 실제 누락처럼 보였던 010_v49_phase2·018_v53_contract_generation·
  018_v57_completion 은 모두 실존 revision id 다(파일명 접두어 ≠ revision id).

추가 사항:
- sales_site_accounting.ym(전기 귀속월 'YYYY-MM') 컬럼 — 자동전기(급여 등) 멱등 귀속키.
- UNIQUE(site_id, ym, entry_type) WHERE ym IS NOT NULL — 동일월·동일항목 중복전기 차단.
  (수기 전기는 ym 미지정 → 유니크 미적용. 사람이 의도적으로 같은 항목을 여러 번 기록 가능.)
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "032_sales_admin_accounting"
down_revision = ("v62_7_learning_examples", "031_analysis_ledger")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # ── sales_site_accounting (현장 회계 원장: 인건비/경비/공과금/광고비/기타) ──
    if "sales_site_accounting" not in tables:
        op.create_table(
            "sales_site_accounting",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
            # LABOR/EXPENSE/UTILITY/AD/ETC
            sa.Column("entry_type", sa.String(length=12), nullable=False),
            sa.Column("amount", sa.Numeric(16, 0), nullable=False),
            sa.Column("memo", sa.Text(), nullable=True),
            sa.Column("entry_date", sa.Date(), nullable=False,
                      server_default=sa.text("current_date")),
            # ym: 자동전기(급여 등) 귀속월 'YYYY-MM'. 수기 전기는 NULL.
            sa.Column("ym", sa.String(length=7), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )
    else:
        # 기존(런타임 DDL로 생성된) 테이블에 ym 컬럼 멱등 추가.
        cols = {c["name"] for c in insp.get_columns("sales_site_accounting")}
        if "ym" not in cols:
            op.add_column("sales_site_accounting",
                          sa.Column("ym", sa.String(length=7), nullable=True))

    op.execute("CREATE INDEX IF NOT EXISTS ix_site_acct_site ON sales_site_accounting (site_id)")
    # 자동전기 멱등 — 동일 (site_id, ym, entry_type) 중복 차단. ym NULL(수기)은 미적용.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_site_acct_site_ym_type "
        "ON sales_site_accounting (site_id, ym, entry_type) WHERE ym IS NOT NULL"
    )

    # ── sales_staff_wage (직원 단가·세무모드) ──
    if "sales_staff_wage" not in tables:
        op.create_table(
            "sales_staff_wage",
            sa.Column("staff_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
            # DAILY/HOURLY/MONTHLY
            sa.Column("wage_type", sa.String(length=10), nullable=False,
                      server_default=sa.text("'DAILY'")),
            sa.Column("base_wage", sa.Numeric(14, 0), nullable=False,
                      server_default=sa.text("0")),
            # FREELANCE/EMPLOYEE/NONE
            sa.Column("tax_mode", sa.String(length=12), nullable=False,
                      server_default=sa.text("'FREELANCE'")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )
    else:
        cols = {c["name"] for c in insp.get_columns("sales_staff_wage")}
        if "tax_mode" not in cols:
            op.add_column("sales_staff_wage",
                          sa.Column("tax_mode", sa.String(length=12), nullable=False,
                                    server_default=sa.text("'FREELANCE'")))
    op.execute("CREATE INDEX IF NOT EXISTS ix_staff_wage_site ON sales_staff_wage (site_id)")


def downgrade() -> None:
    # 데이터 보존: 테이블 자체는 드롭하지 않고(런타임 생성분과 충돌 방지),
    # 본 마이그레이션이 추가한 인덱스/컬럼만 되돌린다.
    op.execute("DROP INDEX IF EXISTS uq_site_acct_site_ym_type")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "sales_site_accounting" in set(insp.get_table_names()):
        cols = {c["name"] for c in insp.get_columns("sales_site_accounting")}
        if "ym" in cols:
            op.drop_column("sales_site_accounting", "ym")
