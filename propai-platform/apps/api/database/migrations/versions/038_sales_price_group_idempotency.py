"""분양가 그룹 멱등키 — (site_id, selector→round_id, selector→idem) 부분 유니크 인덱스(정본).

Revision ID: 038_sales_price_group_idempotency
Revises: 037_sales_contract_subscription_idempotency
Create Date: 2026-06-19

#8 적정분양가·원가 iter-3 MED(멱등성) 마감 — 그룹 일괄단가 중복생성·RATE 복리가산 차단의 'DB 정본'.

[배경] apply_group_pricing(RATE/FIXED)은 과거 호출마다 무조건 새 SalesPriceGroup 을 만들었다.
  _match_weights 가 세대당 매칭 그룹을 '전부 합산'(rate_sum += value)하므로, 더블클릭·재시도·
  재전송으로 같은 그룹이 N개 생기면 RATE 가 N배 가산(복리)돼 분양가/매출이 부풀려졌다(머니패스 왜곡).
  서비스 코드(engine.apply_group_pricing)에서 (site_id, round_id, 멱등키) get-or-create 로 1차 차단
  하지만, 애플리케이션 조회만으로는 동시 트랜잭션 2건이 거의 동시에 '없음'을 보고 둘 다 INSERT 하는
  race 를 막지 못한다. DB 부분 유니크 인덱스를 정본으로 둬, 어떤 경로/동시성에서도 중복생성을 23505 로
  거부한다. 서비스는 둘째 INSERT 의 23505(IntegrityError)를 SAVEPOINT 안에서 잡아 기존 그룹 재사용으로
  graceful 매핑한다(미가공 500 금지) — 이 인덱스가 그 race 백스톱의 정본이다.

[해소] sales_price_groups(selector JSONB)에 멱등키를 적재한다(전용 컬럼 없이 보관):
  selector = {"round_id": "<UUID>", "idem": "<RATE|FIXED>:<group_name> 또는 클라 idempotency_key>"}.
  (site_id, (selector->>'round_id'), (selector->>'idem')) 에 부분 유니크 인덱스를 만든다.
  - selector->>'idem' 또는 selector->>'round_id' 가 NULL 인 행(과거 데이터·OVERRIDE 경로 등 멱등키
    미보유 그룹)은 WHERE 로 제외 → 기존 정상 동작을 막지 않는다(부분 인덱스).

[정직/배포] 샌드박스에선 라이브 DB 적용 불가(deploy-pending) — 코드 정본만 추가한다. 운영 적용은
  alembic upgrade 로 수행한다. 기존 데이터에 이미 동일 키 그룹이 중복돼 있으면 인덱스 생성이
  실패할 수 있으므로, 운영 적용 전 아래 사전점검으로 정합을 맞춘 뒤 적용한다.

  -- 사전점검(중복 멱등키 그룹):
  -- SELECT site_id, selector->>'round_id' AS rid, selector->>'idem' AS idem, count(*)
  --   FROM sales_price_groups
  --   WHERE selector->>'round_id' IS NOT NULL AND selector->>'idem' IS NOT NULL
  --   GROUP BY 1,2,3 HAVING count(*)>1;

[헤드] 직전 단일 헤드는 037_sales_contract_subscription_idempotency 였다(038 이 037 을 단일 부모로
  받아 헤드를 1개로 유지).
"""
from alembic import op

revision = "038_sales_price_group_idempotency"
down_revision = "037_sales_contract_subscription_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 동일 현장·차수·멱등키 그룹 중복생성 차단(RATE 복리가산 DB 백스톱).
    # 테이블은 v62_1_sales_tables 등에서 이미 생성돼 있으므로 인덱스만 멱등 생성(IF NOT EXISTS).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_price_group_idem "
        "ON sales_price_groups (site_id, (selector->>'round_id'), (selector->>'idem')) "
        "WHERE selector->>'round_id' IS NOT NULL AND selector->>'idem' IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sales_price_group_idem")
