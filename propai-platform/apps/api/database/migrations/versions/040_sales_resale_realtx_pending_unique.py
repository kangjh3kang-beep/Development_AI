"""전매·실거래신고 PENDING 멱등 — 계약당 단일 PENDING 부분 유니크 인덱스(정본).

Revision ID: 040_sales_resale_realtx_pending_unique
Revises: 039_sales_price_group_member_unique
Create Date: 2026-06-19

#9 해촉·전매·MH iter-2 HIGH(TOCTOU) 마감 — 전매요청/실거래신고 중복 PENDING 차단의 'DB 정본'.

[배경] resale/service.py 의 멱등이 앱레벨 'SELECT-then-INSERT' 만이었다(DB 제약 부재). v62_4_p6_tables
  는 sales_resale_transfers·sales_realtx_reports 에 비유니크 인덱스(idx_realtx_contract)만 만들었고
  부분 유니크는 없었다. 그래서 동시 두 요청이 거의 동시에 'PENDING 없음'을 읽고 둘 다 INSERT 하면
  같은 계약에 중복 PENDING 행이 생긴다(read-then-write 경합). 전매는 머니패스(명의변경)라 중복 PENDING
  이 쌓이면 누가 승인하느냐에 따라 명의가 흔들린다(이중 명의변경 토대).

[해소·2겹]
  ① 애플리케이션 즉시방어(코드, deploy 무관): request_transfer/create_realtx_report 의 INSERT 를
     SAVEPOINT(begin_nested)+flush 로 감싸 23505(아래 인덱스 위반)를 graceful 흡수 → 기존 PENDING 행을
     재조회·반환(미가공 500 금지). 인덱스 미적용 환경에선 위반이 없어 정상 INSERT(무회귀).
  ② DB 정본(이 마이그레이션): 계약당 '결정 안 된(PENDING) 1건' 만 허용하는 부분 유니크 인덱스.
     · sales_resale_transfers : UNIQUE(site_id, contract_ext_id) WHERE decided_at IS NULL
       (결정되면 decided_at 채워져 술어에서 빠지므로, 다음 전매요청을 정상 허용 — 종결 후 재요청 가능)
     · sales_realtx_reports   : UNIQUE(site_id, contract_ext_id) WHERE status = 'PENDING'
       (제출/수리되면 status 가 PENDING 아니게 되어 술어에서 빠짐 — 다음 신고 정상 허용)
     '계약당 단일 PENDING' 정책이라 전매 종류(RESALE/NAME_CHANGE)는 술어에 넣지 않는다. 앱쪽
     duplicate 응답이 기존 transfer_type 을 노출해 종류 오인(과대매칭)을 막으므로 앱-인덱스 정합.

[정직/배포] 샌드박스에선 라이브 DB 적용 불가(deploy-pending) — 코드 정본만 추가한다. 운영 적용은
  alembic upgrade 로 수행한다. 기존 데이터에 이미 같은 계약의 PENDING 이 중복돼 있으면 인덱스 생성이
  실패할 수 있으므로, 운영 적용 전 아래 사전점검·정리로 정합을 맞춘 뒤 적용한다.

  -- 사전점검(전매 중복 PENDING):
  -- SELECT site_id, contract_ext_id, count(*) FROM sales_resale_transfers
  --   WHERE decided_at IS NULL GROUP BY 1,2 HAVING count(*)>1;
  -- 정리(가장 먼저 요청된 1건만 남김 — 운영 적용 직전 수동 검토 후 실행):
  -- DELETE FROM sales_resale_transfers a USING sales_resale_transfers b
  --   WHERE a.site_id=b.site_id AND a.contract_ext_id=b.contract_ext_id
  --     AND a.decided_at IS NULL AND b.decided_at IS NULL AND a.requested_at > b.requested_at;
  -- 사전점검(실거래신고 중복 PENDING):
  -- SELECT site_id, contract_ext_id, count(*) FROM sales_realtx_reports
  --   WHERE status='PENDING' GROUP BY 1,2 HAVING count(*)>1;
  -- 정리(id 가장 작은 1건만 남김):
  -- DELETE FROM sales_realtx_reports a USING sales_realtx_reports b
  --   WHERE a.site_id=b.site_id AND a.contract_ext_id=b.contract_ext_id
  --     AND a.status='PENDING' AND b.status='PENDING' AND a.id > b.id;

[헤드] 직전 단일 헤드는 039_sales_price_group_member_unique 였다(040 이 039 를 단일 부모로 받아 헤드를
  1개로 유지 — orphan 금지).
"""
from alembic import op

revision = "040_sales_resale_realtx_pending_unique"
down_revision = "039_sales_price_group_member_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 계약당 결정 안 된(PENDING) 전매요청 1건만 허용 — 동시 INSERT 로 인한 중복 PENDING 의 DB 백스톱.
    # 결정된(decided_at NOT NULL) 행은 술어에서 빠져 종결 후 재요청을 막지 않는다(부분 인덱스).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_resale_transfer_pending "
        "ON sales_resale_transfers (site_id, contract_ext_id) "
        "WHERE decided_at IS NULL"
    )
    # 계약당 미제출(PENDING) 실거래신고 1건만 허용 — 제출/수리되면 status 가 바뀌어 술어에서 빠진다.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_realtx_report_pending "
        "ON sales_realtx_reports (site_id, contract_ext_id) "
        "WHERE status = 'PENDING'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sales_resale_transfer_pending")
    op.execute("DROP INDEX IF EXISTS uq_sales_realtx_report_pending")
