"""분양 수수료 — 런타임 DDL 정본화(세금유형 선호·지급 부가컬럼·정산 멱등키).

Revision ID: 033_sales_commission_tax_pref
Revises: 032_sales_admin_accounting
Create Date: 2026-06-19

#3 수수료·더치페이·원천징수 Wave1 P0-2/P0-3 정본화.

기존에 런타임(매 요청) DDL 로 만들던 것을 마이그레이션 정본으로 이관한다.
런타임 DDL(engine.ensure_tax_pref / extension._ensure_payout_columns)은 advisory-lock +
프로세스 1회 게이트로 강등되어 'race 만 제거하는 부팅 안전망'으로만 남고, 정본은 본 마이그레이션이다.

이관 대상
- sales_commission_tax_pref : 수령자(조직노드)별 수수료 세금유형(WITHHOLDING/VAT) 선호.
  (engine.py 의 CREATE TABLE IF NOT EXISTS sales_commission_tax_pref 를 정본화.)
- sales_commission_payouts.tax_type / vat : 부가세 가산 지급액 추적 컬럼.
  (extension.py 의 매 건 ALTER TABLE ADD COLUMN IF NOT EXISTS 를 정본화.)
- sales_commission_settlements : 정산 헤더 테이블 정본 생성(부재 시) + (site_id, period) 멱등키 —
  동일 현장·동일 기간 정산 중복적재 차단. 기존엔 이 테이블 create 마이그레이션이 없어(런타임 ORM
  자동생성만 의존) 클린 DB 에 033 먼저 적용 시 인덱스가 skip 됐다. 이제 ORM 정의와 일치하게 생성한 뒤
  유니크 인덱스를 '무조건' 만들어 멱등키 존재를 보장한다(정산 원장 무결성·해시체인 미존재 도메인 보강).

★헤드: 본 리비전 직전 단일 헤드는 032_sales_admin_accounting 였다(다른 두 tip
  021_v62_design_tables·022_user_project_store 는 v62_1_sales_tables 의 down_revision 튜플로
  이미 병합돼 있어 헤드가 아니다). 본 033 이 032 를 단일 부모로 받아 헤드를 1개로 유지한다.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "033_sales_commission_tax_pref"
down_revision = "032_sales_admin_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # ── sales_commission_tax_pref (수령자별 세금유형 선호: WITHHOLDING/VAT) ──
    if "sales_commission_tax_pref" not in tables:
        op.create_table(
            "sales_commission_tax_pref",
            sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
            # node_id 가 PK — 노드당 1개 세금유형(set 시 ON CONFLICT (node_id) DO UPDATE).
            sa.Column("node_id", postgresql.UUID(as_uuid=True), primary_key=True),
            # WITHHOLDING(3.3% 원천징수, 기본) | VAT(부가세 10% 가산)
            sa.Column("tax_type", sa.String(length=16), nullable=False,
                      server_default=sa.text("'WITHHOLDING'")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
        )

    # ── sales_commission_payouts.tax_type / vat (부가세 가산 지급액 추적) ──
    if "sales_commission_payouts" in tables:
        cols = {c["name"] for c in insp.get_columns("sales_commission_payouts")}
        if "tax_type" not in cols:
            op.add_column("sales_commission_payouts",
                          sa.Column("tax_type", sa.String(length=16), nullable=True,
                                    server_default=sa.text("'WITHHOLDING'")))
        if "vat" not in cols:
            op.add_column("sales_commission_payouts",
                          sa.Column("vat", sa.Numeric(16, 0), nullable=True,
                                    server_default=sa.text("0")))

    # ── sales_commission_settlements (정산 헤더) — 정본 생성 + (site_id, period) 멱등키 ──
    #   ★[멱등키 미배선 해소] 기존엔 'settlements 가 이미 있을 때만' 인덱스를 만들었으나, 이 테이블을
    #     create_table 하는 마이그레이션이 전무했다(런타임 ORM 자동생성만 의존). 그래서 '클린 DB →
    #     033 먼저 적용' 순서에선 테이블 부재로 인덱스가 skip 되어 멱등키가 영구 미적용이었다.
    #   → 본 마이그레이션을 정본으로 삼아: 테이블이 없으면 ORM(SalesCommissionSettlement) 정의와
    #     동일하게 생성(IF NOT EXISTS 의미의 'not in tables' 가드)한 뒤, 유니크 인덱스를 '무조건' 만든다.
    #     (런타임 ORM 자동생성과 충돌하지 않게 컬럼/타입/PK 를 ORM 과 1:1 일치시킨다.)
    if "sales_commission_settlements" not in tables:
        op.create_table(
            "sales_commission_settlements",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text("gen_random_uuid()")),
            sa.Column("site_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("sales_sites.id"), nullable=False),
            sa.Column("period", sa.String(length=20), nullable=True),
            sa.Column("total_gross", sa.Numeric(16, 0), nullable=True),
            sa.Column("total_withholding", sa.Numeric(16, 0), nullable=True),
            sa.Column("total_net", sa.Numeric(16, 0), nullable=True),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=True),
        )
        # SiteMixin 의 site_id index=True 와 정합(ORM 자동생성 시 동일 인덱스가 생기므로 IF NOT EXISTS).
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_sales_commission_settlements_site_id "
            "ON sales_commission_settlements (site_id)"
        )

    #   동일 현장·동일 기간(period 'YYYY-MM') 정산이 중복 적재되지 않게 부분 유니크 인덱스를 둔다.
    #   period NULL(미지정) 행은 유니크 미적용(사람이 의도적으로 임시 정산을 여러 번 기록 가능).
    #   ★테이블 생성 직후 '무조건' 실행 — 클린 upgrade head 후에도 멱등키 존재 보장.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_comm_settlement_site_period "
        "ON sales_commission_settlements (site_id, period) WHERE period IS NOT NULL"
    )


def downgrade() -> None:
    # 데이터 보존: 런타임 DDL 로 만들어진 테이블/컬럼과 충돌하지 않도록 본 마이그레이션 추가분만 되돌린다.
    op.execute("DROP INDEX IF EXISTS uq_comm_settlement_site_period")
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())
    if "sales_commission_payouts" in tables:
        cols = {c["name"] for c in insp.get_columns("sales_commission_payouts")}
        if "vat" in cols:
            op.drop_column("sales_commission_payouts", "vat")
        if "tax_type" in cols:
            op.drop_column("sales_commission_payouts", "tax_type")
    # sales_commission_tax_pref 는 런타임 생성분과 충돌 방지 위해 드롭하지 않는다(데이터 보존).
