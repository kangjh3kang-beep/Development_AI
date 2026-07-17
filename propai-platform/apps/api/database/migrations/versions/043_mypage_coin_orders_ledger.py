"""마이페이지 — 코인 충전 주문(coin_orders)·코인 거래 원장(coin_ledger_events).

2026-07-17 마이페이지 스펙(docs/design/MYPAGE_SAAS_SPEC_2026-07-17.md):
- coin_orders: 충전 주문 수명주기(pending→paid|canceled|failed). 전자상거래법 시행령 §6
  (대금결제·계약 기록 5년 보존) 대상 결제기록의 정본 — 구매자 스냅샷(buyer_name/buyer_email)
  내장으로 탈퇴(users 익명화)와 독립 보존. provider_ref 부분 유니크 = PG 웹훅 멱등 키.
- coin_ledger_events: append-only 해시체인 원장(체인 단위=user_id) — 충전/주문지급/서비스료/
  월기본부여/등급변경/관리자조정 이력. 잔액 SSOT는 기존 users 컬럼(원장은 이력·감사).

★서비스(coin_orders_service/coin_ledger_service)의 lazy DDL(CREATE IF NOT EXISTS)과 **문면 동일**
  DDL을 op.execute로 실행한다(멱등 — 어느 쪽이 먼저 실행돼도 안전, deploy.sh가 alembic을
  건너뛰어도 서비스가 자가 프로비저닝). 스키마 변경은 반드시 양쪽 동시 수정.

Revision ID: 043_mypage_coin_orders_ledger
Revises: 042_member_account_system
"""

from collections.abc import Sequence

from alembic import op

revision: str = "043_mypage_coin_orders_ledger"
down_revision: str | None = "042_member_account_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ★app.services.billing.coin_orders_service._DDL / coin_ledger_service._DDL 과 문면 동일 유지.
_COIN_ORDERS_DDL = (
    "CREATE TABLE IF NOT EXISTS coin_orders ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  order_no text UNIQUE NOT NULL,"
    "  user_id text NOT NULL,"
    "  tenant_id text,"
    "  package_key text NOT NULL,"
    "  amount_krw numeric(14,2) NOT NULL,"
    "  coin_krw numeric(14,2) NOT NULL,"
    "  status text NOT NULL DEFAULT 'pending',"
    "  provider text,"
    "  provider_ref text,"
    "  buyer_name text,"
    "  buyer_email text,"
    "  fail_reason text,"
    "  paid_at timestamptz,"
    "  canceled_at timestamptz,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_COIN_ORDERS_IDX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_coin_orders_provider_ref "
    "ON coin_orders(provider_ref) WHERE provider_ref IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_coin_orders_user_created ON coin_orders(user_id, created_at)",
)

_COIN_LEDGER_DDL = (
    "CREATE TABLE IF NOT EXISTS coin_ledger_events ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  user_id text NOT NULL,"
    "  tenant_id text,"
    "  seq int NOT NULL DEFAULT 1,"
    "  entry_type text NOT NULL,"
    "  amount_krw numeric(14,2) NOT NULL,"
    "  description text,"
    "  ref_type text,"
    "  ref_id text,"
    "  content_hash text NOT NULL,"
    "  prev_hash text,"
    "  created_by text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_COIN_LEDGER_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_coin_ledger_chain ON coin_ledger_events(user_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_coin_ledger_user_created ON coin_ledger_events(user_id, created_at)",
)


def upgrade() -> None:
    op.execute(_COIN_ORDERS_DDL)
    for ddl in _COIN_ORDERS_IDX:
        op.execute(ddl)
    op.execute(_COIN_LEDGER_DDL)
    for ddl in _COIN_LEDGER_IDX:
        op.execute(ddl)


def downgrade() -> None:
    # ★결제기록(coin_orders)은 전상법 §6 보존 대상 — 운영 downgrade 시 반드시 백업 후 수행.
    op.execute("DROP TABLE IF EXISTS coin_ledger_events")
    op.execute("DROP TABLE IF EXISTS coin_orders")
