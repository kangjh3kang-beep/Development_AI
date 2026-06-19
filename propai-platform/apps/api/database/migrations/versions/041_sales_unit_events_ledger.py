"""세대 라이프사이클 정본 스키마 — 이벤트 원장(해시체인) + 선점 동시성 컬럼/인덱스(정본).

Revision ID: 041_sales_unit_events_ledger
Revises: 040_sales_resale_realtx_pending_unique
Create Date: 2026-06-19

#6 세대 라이프사이클·추첨 — 런타임 DDL(IF NOT EXISTS)로만 존재하던 스키마를 'DB 정본'으로 승격.

[배경] event_ledger._ensure 와 concurrency.ensure_unit_concurrency_columns 가 요청 경로에서 런타임
  CREATE TABLE / ALTER / CREATE INDEX (IF NOT EXISTS) 를 실행해 왔다. 이는 (1) 여러 워커 동시 부팅 시
  같은 DDL 이 겹쳐 race 가 나고 (2) 스키마의 진실원천이 코드에 흩어지는 문제였다. 본 마이그레이션이
  정본(canonical)이며, 런타임 _ensure 는 advisory-lock 으로 race 만 제거한 1회성 보강 안전망으로 남긴다
  (마이그레이션 미적용 환경 대비). 두 경로 모두 IF NOT EXISTS 라 무회귀(이미 있으면 no-op).

[생성 대상]
  ① sales_unit_events : 세대별 append-only 해시체인 원장(UNIQUE(unit_id, seq)).
     - seq 는 세대별 1,2,3... 단조 증가(append 가 직전 seq+1 부여, advisory-lock 으로 직렬화).
     - content_hash = sha256(prev_hash + 정규화 페이로드) → 사후 변조탐지(verify_chain).
     - UNIQUE(unit_id, seq) 가 동시 append 의 체인 fork(같은 seq 2행)를 DB 레벨에서 차단한다.
  ② sales_unit_inventory 선점 동시성 컬럼 : held_by / hold_expires_at / hold_token.
  ③ 동호 부분 유니크 인덱스(1세대 1행) + 보드 조회 가속 인덱스.

[정직/배포] 샌드박스에선 라이브 DB 적용 불가(deploy-pending) — 코드 정본만 추가한다. 운영 적용은
  alembic upgrade 로 수행한다. sales_unit_inventory 는 v62_1_sales_tables 에서 이미 생성되므로 본
  마이그레이션은 컬럼/인덱스만 보강한다(테이블 재생성 아님).

[헤드] 직전 단일 헤드는 040_sales_resale_realtx_pending_unique 였다(041 이 040 을 단일 부모로 받아
  헤드를 1개로 유지 — orphan 금지).
"""
from alembic import op

revision = "041_sales_unit_events_ledger"
down_revision = "040_sales_resale_realtx_pending_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ① 세대 이벤트 원장(해시체인) — append-only. UNIQUE(unit_id, seq) 가 체인 fork 의 DB 백스톱.
    op.execute(
        "CREATE TABLE IF NOT EXISTS sales_unit_events ("
        "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
        "  site_id uuid NOT NULL,"
        "  unit_id uuid NOT NULL,"
        "  seq integer NOT NULL,"
        "  event_type varchar(20) NOT NULL,"
        "  from_status varchar(20),"
        "  to_status varchar(20),"
        "  message text,"
        "  meta jsonb,"
        "  created_by uuid,"
        "  occurred_at timestamptz NOT NULL DEFAULT now(),"
        "  occurred_iso varchar(40) NOT NULL,"
        "  content_hash varchar(64) NOT NULL,"
        "  prev_hash varchar(64),"
        "  UNIQUE (unit_id, seq)"
        ")"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_unit_events_unit ON sales_unit_events(unit_id, seq)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_unit_events_site ON sales_unit_events(site_id, occurred_at)"
    )

    # ② 선점 동시성 컬럼(멱등 ALTER) — held_by/hold_expires_at/hold_token.
    op.execute(
        "ALTER TABLE sales_unit_inventory "
        "ADD COLUMN IF NOT EXISTS held_by uuid, "
        "ADD COLUMN IF NOT EXISTS hold_expires_at timestamptz, "
        "ADD COLUMN IF NOT EXISTS hold_token text"
    )
    # ③ 동호 1세대 1행(부분 유니크) + 보드 조회 가속.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_unit_inventory_site_dong_ho "
        "ON sales_unit_inventory (site_id, dong, ho) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_unit_inventory_site_status "
        "ON sales_unit_inventory (site_id, status)"
    )


def downgrade() -> None:
    # 인덱스/원장만 되돌린다. 컬럼(held_by 등)은 데이터 보존을 위해 downgrade 에서 제거하지 않는다
    # (운영 롤백 시 선점 메타 유실 방지 — 필요 시 수동 DROP COLUMN).
    op.execute("DROP INDEX IF EXISTS ix_unit_inventory_site_status")
    op.execute("DROP INDEX IF EXISTS uq_unit_inventory_site_dong_ho")
    op.execute("DROP INDEX IF EXISTS ix_unit_events_site")
    op.execute("DROP INDEX IF EXISTS ix_unit_events_unit")
    op.execute("DROP TABLE IF EXISTS sales_unit_events")
