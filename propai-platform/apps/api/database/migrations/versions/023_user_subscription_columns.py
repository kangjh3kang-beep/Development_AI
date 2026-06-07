"""023 — 사용자 구독·과금 컬럼 정식화(public.users) + UserSubscription ORM 대응

Revision ID: 023_user_subscription_columns
Revises: v62_4_p6_tables
Create Date: 2026-06-07

billing_service가 raw SQL로 사용해 온 과금 컬럼을 마이그레이션으로 정식화한다.
모두 ADD COLUMN IF NOT EXISTS 라 billing_service.ensure_schema()의 런타임 DDL과
멱등하게 공존한다(기존 흐름 무파괴·additive). 데이터 백필/제약 변경 없음.

대상 컬럼:
- tier (text)                  : 구독 등급
- llm_billed_krw (numeric)     : 사이클 누적 청구액
- billing_budget_krw (numeric) : 하위호환 총 한도(monthly_base+topup)
- billing_cycle_start (tstz)   : 사이클 시작
- monthly_base_krw (numeric)   : 월 제공 기본
- topup_krw (numeric)          : 충전 잔액
- analysis_count (int)         : 무료 분석 사용 횟수
- service_fee_krw (numeric)    : 서비스 사용료 누적
"""
from alembic import op

revision = "023_user_subscription_columns"
down_revision = "v62_4_p6_tables"
branch_labels = None
depends_on = None


_ADD_COLS = [
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS tier text",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS llm_billed_krw numeric(14,2) DEFAULT 0",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS billing_budget_krw numeric(14,2) DEFAULT 0",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS billing_cycle_start timestamptz",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS monthly_base_krw numeric(14,2) DEFAULT 0",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS topup_krw numeric(14,2) DEFAULT 0",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS analysis_count integer DEFAULT 0",
    "ALTER TABLE public.users ADD COLUMN IF NOT EXISTS service_fee_krw numeric(14,2) DEFAULT 0",
]


def upgrade() -> None:
    for ddl in _ADD_COLS:
        op.execute(ddl)


def downgrade() -> None:
    # 과금 데이터 보존을 위해 다운그레이드에서 컬럼을 제거하지 않는다(안전·무손실).
    # 필요 시 운영자가 명시적으로 DROP COLUMN 한다.
    pass
