"""분양 지급명세서(원천징수) 멱등키 — (site_id, period, payee_node_id) 유니크.

Revision ID: 034_sales_withholding_idempotency
Revises: 033_sales_commission_tax_pref
Create Date: 2026-06-19

#3 수수료·원천징수 iter-7(최종) HIGH 마감.

[배경] sales_withholding_statements(지급명세서, 법적 세무서류)는 '동일 현장(site_id)·동일 기간
  (period 'YYYY-MM')·동일 수령노드(payee_node_id)'당 1건이어야 한다. 그런데 기존엔 이 3컬럼에 대한
  유니크 제약이 없었고(database/models/sales/tax.py 확인), build_withholding_statements 가
  GET 호출마다 db.add()+commit 으로 무조건 INSERT 했다. 그래서 동일 기간 재호출 시 같은
  (site,period,node) 명세가 N행으로 중복누적되어 법적 서류가 부풀려졌다.

[해소] (site_id, period, payee_node_id) 부분 유니크 인덱스를 둔다. 이 인덱스가 있어야
  build_withholding_statements 의 'DELETE before INSERT' 멱등화(중복 방지)와, 향후 필요 시
  ON CONFLICT upsert 가 성립한다(정본은 본 마이그레이션).
  - period 또는 payee_node_id 가 NULL 인 행은 유니크 미적용(부분 인덱스 WHERE) — 집계 미확정/
    무노드 임시행을 막지 않는다(정상 동작 보존). build 경로는 항상 period·payee_node_id 를 채우므로
    실효 범위는 정상 명세 전부다.

[헤드] 직전 단일 헤드는 033_sales_commission_tax_pref 였다(034 가 033 를 단일 부모로 받아
  헤드를 1개로 유지). 샌드박스에선 라이브 적용 불가(deploy-pending) — 코드 정본만 추가한다.
"""
from alembic import op

revision = "034_sales_withholding_idempotency"
down_revision = "033_sales_commission_tax_pref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 동일 현장·기간·수령노드 지급명세서 중복적재 차단(법적 세무서류 멱등키).
    # 테이블이 이미 v62_4_p6_tables 에서 생성돼 있으므로 인덱스만 '무조건' 만든다(IF NOT EXISTS).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_withholding_site_period_node "
        "ON sales_withholding_statements (site_id, period, payee_node_id) "
        "WHERE period IS NOT NULL AND payee_node_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_withholding_site_period_node")
