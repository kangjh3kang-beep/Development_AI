"""#4 수납·대출·보증 — 할인/환급 테이블 + 입금 상태머신/회차지정 + 연체 멱등 + 대출 상환 정본.

Revision ID: 035_sales_payment_loan_settlement
Revises: 034_sales_withholding_idempotency
Create Date: 2026-06-19

#4 수납·대출·보증 Wave2 P1-1(6.5→8.2)의 스키마 정본(런타임 DDL 이관 + 멱등키 신설).

[배경/해소]
1) sales_payment_adjustments(할인/환급) 테이블이 라우터(lifecycle_p5.py)에서 런타임
   CREATE TABLE 로 만들어졌다(런타임 DDL). 정본을 본 마이그레이션으로 이관한다. 라우터의
   _ensure_adj 는 마이그레이션 미적용 환경용 '런타임 안전망'으로만 남기고(advisory-lock 1회),
   정본은 여기다(IF NOT EXISTS 라 적용환경에선 no-op).
2) sales_payments 에 입금 상태머신(status: PENDING/MATCHED/UNMATCHED/REVERSED/SURPLUS)과
   회차지정 충당(preferred_installment_seq)을 추가한다. 기존 matched(bool) 와 동기화.
   추가로 같은 현장의 같은 거래참조(raw_ref)는 1건만 허용하는 partial UNIQUE 인덱스
   (uq_pay_site_raw_ref, WHERE raw_ref IS NOT NULL)를 건다 → 앱레벨 read-then-write(TOCTOU)
   만으로는 못 막는 동시 webhook 재시도의 이중 충당을 DB 가 23505 로 원천 차단한다.
3) sales_overdue_interest 에 산정기준일(calc_date)을 추가하고 (site_id, installment_id,
   calc_date) 부분 UNIQUE 인덱스(uq_overdue_site_inst_date, WHERE calc_date IS NOT NULL)를
   건다 → overdue_calc 가 ON CONFLICT (site_id, installment_id, calc_date) DO UPDATE 로
   적재하므로 일배치·수동 트리거가 동시에 같은 현장·기준일을 산정해도 23505 없이 멱등(덮어쓰기).
   ★이 인덱스가 ON CONFLICT 의 arbiter 다(항상 non-null calc_date 로 INSERT 하므로 부분인덱스 유효).
4) sales_loan_disbursements 에 누적 상환액(repaid_amount)을 추가한다 → 부분/전액 상환 누적·
   전액상환 시 약정 status=REPAID 전이(repay_loan)의 정본.

전부 additive(컬럼/테이블/인덱스 추가)·IF NOT EXISTS 라 기존 데이터·동작 무회귀. 컬럼은
server_default 를 둬 기존 행도 안전하게 채워진다.

[헤드] 직전 단일 헤드는 034_sales_withholding_idempotency 였다(035 가 034 를 단일 부모로 받아
  헤드 1개 유지). 샌드박스에선 라이브 적용 불가(deploy-pending) — 코드 정본만 추가한다.
"""
from alembic import op

revision = "035_sales_payment_loan_settlement"
down_revision = "034_sales_withholding_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 할인/환급 조정 테이블(런타임 DDL 이관, 정본).
    op.execute(
        "CREATE TABLE IF NOT EXISTS sales_payment_adjustments ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  site_id uuid NOT NULL,"
        "  contract_ext_id uuid NOT NULL,"
        "  adj_type varchar(12) NOT NULL,"        # DISCOUNT(할인) | REFUND(환급)
        "  amount numeric(16,0) NOT NULL,"
        "  reason text,"
        "  created_by uuid,"
        "  created_at timestamptz NOT NULL DEFAULT now()"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pay_adj_contract "
        "ON sales_payment_adjustments (site_id, contract_ext_id)"
    )

    # 2) 입금 상태머신 + 회차지정 충당(sales_payments).
    op.execute(
        "ALTER TABLE sales_payments "
        "ADD COLUMN IF NOT EXISTS status varchar(12) NOT NULL DEFAULT 'PENDING'"
    )
    # 기존 행 동기화: matched=True 였던 입금은 MATCHED, 그 외는 UNMATCHED 로 1회 백필.
    op.execute(
        "UPDATE sales_payments SET status = CASE WHEN matched THEN 'MATCHED' ELSE 'UNMATCHED' END "
        "WHERE status = 'PENDING'"
    )
    op.execute(
        "ALTER TABLE sales_payments "
        "ADD COLUMN IF NOT EXISTS preferred_installment_seq integer"
    )
    # 다회차 충당 내역(JSONB): 한 입금이 여러 회차에 분산 충당되면 회차별 실제 충당액을
    # [{installment_id, applied_amount}, ...] 로 기록한다 → 취소(reverse) 시 회차별 정확 역배분.
    # 구행은 NULL(단일 installment_id 폴백) → 무회귀.
    op.execute(
        "ALTER TABLE sales_payments "
        "ADD COLUMN IF NOT EXISTS allocations jsonb"
    )
    # ★멱등 DB 게이트(이중 충당 원천 차단): 같은 현장의 같은 거래참조(raw_ref)는 1건만 허용한다.
    #   앱레벨 read-then-write(중복조회 후 INSERT)는 두 콜백이 동시에 조회→둘 다 미발견→둘 다 INSERT
    #   하는 TOCTOU race 가 있었다(같은 입금 2회 충당). partial UNIQUE(WHERE raw_ref IS NOT NULL)로
    #   DB 가 2번째 INSERT 를 23505 로 막는다. raw_ref 없는(NULL) 수동 입금은 중복 허용(미적용).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_pay_site_raw_ref "
        "ON sales_payments (site_id, raw_ref) WHERE raw_ref IS NOT NULL"
    )

    # 3) 연체이자 산정기준일 + 멱등 UNIQUE(sales_overdue_interest).
    op.execute("ALTER TABLE sales_overdue_interest ADD COLUMN IF NOT EXISTS calc_date date")
    # 기존 행 백필: calculated_at 의 날짜로 채운다(없으면 NULL → 유니크 미적용).
    op.execute(
        "UPDATE sales_overdue_interest SET calc_date = (calculated_at AT TIME ZONE 'UTC')::date "
        "WHERE calc_date IS NULL AND calculated_at IS NOT NULL"
    )
    # 같은 현장·회차·기준일은 1건만(일배치 재실행 중복 차단). NULL calc_date 행은 미적용(부분 인덱스).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_overdue_site_inst_date "
        "ON sales_overdue_interest (site_id, installment_id, calc_date) "
        "WHERE calc_date IS NOT NULL"
    )

    # 4) 대출 누적 상환액(sales_loan_disbursements). 기본 0 → 기존 실행분은 '미상환'으로 시작.
    op.execute(
        "ALTER TABLE sales_loan_disbursements "
        "ADD COLUMN IF NOT EXISTS repaid_amount numeric(16,0) NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sales_loan_disbursements DROP COLUMN IF EXISTS repaid_amount")
    op.execute("DROP INDEX IF EXISTS uq_overdue_site_inst_date")
    op.execute("ALTER TABLE sales_overdue_interest DROP COLUMN IF EXISTS calc_date")
    op.execute("DROP INDEX IF EXISTS uq_pay_site_raw_ref")
    op.execute("ALTER TABLE sales_payments DROP COLUMN IF EXISTS allocations")
    op.execute("ALTER TABLE sales_payments DROP COLUMN IF EXISTS preferred_installment_seq")
    op.execute("ALTER TABLE sales_payments DROP COLUMN IF EXISTS status")
    op.execute("DROP INDEX IF EXISTS idx_pay_adj_contract")
    op.execute("DROP TABLE IF EXISTS sales_payment_adjustments")
