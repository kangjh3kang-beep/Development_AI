"""분양가 그룹 멤버 멱등 — sales_price_group_members(group_id, unit_id) 유니크 인덱스(정본).

Revision ID: 039_sales_price_group_member_unique
Revises: 038_sales_price_group_idempotency
Create Date: 2026-06-19

#8 적정분양가·원가 iter-7 HIGH(멤버레벨 복리 사각) 마감 — 그룹 멤버 중복행·RATE 복리가산 차단의 'DB 정본'.

[배경] 038 은 '그룹레벨' 멱등(같은 멱등키 그룹 중복생성 차단)을 DB 인덱스로 정본화했다. 그러나 그룹에
  세대를 매다는 sales_price_group_members 에는 UNIQUE(group_id, unit_id) 가 없었다(units_pricing.py
  의 PKMixin id 만). 그래서:
  - apply_group_pricing._attach_members 가 SELECT-then-INSERT(TOCTOU)로 멤버를 단다. 동시 트랜잭션
    2건이 거의 동시에 '이 세대는 아직 멤버 아님'을 보고 둘 다 INSERT 하면 같은 (group_id, unit_id)
    멤버행이 2건 생긴다.
  - generate_price_table·resolve_unit_price·solve_base_for_target 가 공용으로 쓰는 _load_group_map 이
    '멤버행 수만큼' 같은 그룹을 unit 의 그룹리스트에 append 한다 → _match_weights 가 그 그룹을 2회
    반환 → compute_unit_price rate_sum 이 2배(예 +5% 가 +10%)로 복리된다(분양가/매출 머니패스 왜곡).
  그룹레벨 멱등(038)만으론 이 '멤버레벨' 복리를 막지 못한다.

[해소·2겹]
  ① 애플리케이션 즉시방어(코드, deploy 무관): _load_group_map 이 unit 별 그룹을 'group.id 기준 dedup'
     해 멤버행이 몇 개든 한 그룹은 1회만 가산. _attach_members 가 SAVEPOINT 안에서 멤버 INSERT 를
     flush 해 23505(아래 인덱스 위반)를 graceful 흡수(미가공 500 금지).
  ② DB 정본(이 마이그레이션): sales_price_group_members(group_id, unit_id) 부분 유니크 인덱스.
     group_id/unit_id 가 NULL 인 행은 제외(부분 인덱스 — 기존 정상 동작 무간섭). 어떤 경로/동시성에서도
     중복 멤버행을 23505 로 거부한다.

[정직/배포] 샌드박스에선 라이브 DB 적용 불가(deploy-pending) — 코드 정본만 추가한다. 운영 적용은
  alembic upgrade 로 수행한다. 기존 데이터에 이미 동일 (group_id, unit_id) 멤버행이 중복돼 있으면
  인덱스 생성이 실패할 수 있으므로, 운영 적용 전 아래 사전점검·정리로 정합을 맞춘 뒤 적용한다.

  -- 사전점검(중복 멤버행):
  -- SELECT group_id, unit_id, count(*)
  --   FROM sales_price_group_members
  --   WHERE group_id IS NOT NULL AND unit_id IS NOT NULL
  --   GROUP BY 1,2 HAVING count(*)>1;
  -- 정리(중복 중 id 가장 작은 1건만 남김 — 운영 적용 직전 수동 검토 후 실행):
  -- DELETE FROM sales_price_group_members a USING sales_price_group_members b
  --   WHERE a.group_id = b.group_id AND a.unit_id = b.unit_id AND a.id > b.id;

[헤드] 직전 단일 헤드는 038_sales_price_group_idempotency 였다(039 가 038 을 단일 부모로 받아 헤드를
  1개로 유지).
"""
from alembic import op

revision = "039_sales_price_group_member_unique"
down_revision = "038_sales_price_group_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 동일 그룹·세대 멤버행 중복 차단(멤버레벨 RATE 복리가산 DB 백스톱).
    # 테이블은 v62_1_sales_tables 등에서 이미 생성돼 있으므로 인덱스만 멱등 생성(IF NOT EXISTS).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_price_group_member "
        "ON sales_price_group_members (group_id, unit_id) "
        "WHERE group_id IS NOT NULL AND unit_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sales_price_group_member")
