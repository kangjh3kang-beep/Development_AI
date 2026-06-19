"""계약·청약 머니패스 멱등·이중점유 차단 — DB레벨 부분 유니크 인덱스(정본).

Revision ID: 037_sales_contract_subscription_idempotency
Revises: 036_sales_market_tables
Create Date: 2026-06-19

#7 계약·CRM·청약 Wave2 P1 — 상태머신·동시성 안전화의 'DB 정본'.

[배경] 계약 체결·청약 추첨·선착순(FCFS)은 '머니패스'다. 서비스 코드(contract/service.py,
  subscription/engine.py)에서 SELECT ... FOR UPDATE 로 같은 세대를 동시에 건드리는 트랜잭션을
  직렬화해 이중계약·이중당첨을 막았지만, 행잠금만으로는 '한 세대에 살아있는 계약이 2건'이나
  '한 공고-세대에 당첨자가 2명' 같은 불변식을 영구 보장하지 못한다(앱 버그·다른 경로 유입 시 재발).
  DB 부분 유니크 인덱스를 정본으로 둬, 어떤 경로로 들어와도 중복을 23505 로 거부하게 한다.

[해소] 두 가지 부분 유니크 인덱스를 만든다(IF NOT EXISTS — 멱등).
  1) uq_sales_contract_active_unit
     : sales_contracts_ext(unit_id) UNIQUE WHERE status = 'ACTIVE' AND unit_id IS NOT NULL
     → 한 세대에 살아있는(ACTIVE) 계약은 단 1건. 취소(CANCELLED) 계약은 제외되므로 재분양
       후 새 ACTIVE 계약을 또 만들 수 있다(정상 동작 보존). 1호 1계약을 DB가 강제.
  2) uq_sales_sub_winner_ann_unit
     : sales_subscription_winners(application_id) — 폐기. 대신 (announcement 경유) 세대 1점유.
       추첨/예비/선착순 당첨은 결국 'unit_id' 점유다. 같은 unit_id 로 NOTIFIED/CONTRACTED 당첨이
       2행 생기면 이중당첨이므로, unit_id 가 있는 행에 한해 유니크를 둔다(win_type 무관).
     : sales_subscription_winners(unit_id) UNIQUE WHERE unit_id IS NOT NULL
       AND status <> 'FORFEITED'
     → 포기(FORFEITED)된 당첨은 제외 → 예비 승계로 같은 세대를 다음 사람에게 줄 수 있다.

[정직/배포] 샌드박스에선 라이브 DB 적용 불가(deploy-pending) — 코드 정본만 추가한다. 운영 적용은
  alembic upgrade 로 수행한다. 기존 데이터에 이미 중복이 있으면 인덱스 생성이 실패할 수 있으므로,
  운영 적용 전 중복정리(아래 주석 쿼리)로 정합을 맞춘 뒤 적용한다.

  -- 사전점검(중복 ACTIVE 계약): SELECT unit_id, count(*) FROM sales_contracts_ext
  --   WHERE status='ACTIVE' AND unit_id IS NOT NULL GROUP BY unit_id HAVING count(*)>1;
  -- 사전점검(중복 점유 당첨): SELECT unit_id, count(*) FROM sales_subscription_winners
  --   WHERE unit_id IS NOT NULL AND status<>'FORFEITED' GROUP BY unit_id HAVING count(*)>1;
  -- 사전점검(중복 수수료 이벤트): SELECT contract_ext_id, count(*) FROM sales_commission_events
  --   WHERE contract_ext_id IS NOT NULL AND status<>'VOID' GROUP BY contract_ext_id HAVING count(*)>1;

[헤드] 직전 단일 헤드는 036_sales_market_tables 였다(037 이 단일 부모로 받아 헤드 1개 유지).
"""
from alembic import op

revision = "037_sales_contract_subscription_idempotency"
down_revision = "036_sales_market_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 한 세대당 살아있는(ACTIVE) 계약 1건 — 1호 1계약을 DB가 강제(취소건은 제외해 재분양 허용).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_contract_active_unit "
        "ON sales_contracts_ext (unit_id) "
        "WHERE status = 'ACTIVE' AND unit_id IS NOT NULL"
    )
    # 2) 한 세대당 유효 당첨(점유) 1건 — 이중당첨 차단(포기 건은 제외해 예비 승계 허용).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_sub_winner_unit "
        "ON sales_subscription_winners (unit_id) "
        "WHERE unit_id IS NOT NULL AND status <> 'FORFEITED'"
    )
    # 3) 한 계약당 유효 수수료 이벤트 1건 — 더블서명·재처리로 split_commission 이 중복 실행돼도
    #    같은 contract_ext_id 로 두 번째 이벤트 INSERT 가 23505 로 거부된다(수수료 2배 DB 백스톱).
    #    서비스 코드(split_commission)도 '이미 발생한 contract_ext_id 이벤트면 조기반환' 으로 멱등을
    #    보장하지만, 다른 경로 유입·앱버그 시에도 불변식(계약당 유효 이벤트 ≤ 1)을 DB가 영구 강제한다.
    #    VOID(무효처리)만 제외해 정정 후 재배분을 허용한다(환수 REVERSED 는 '발생 후 되돌림' 이라 포함).
    #    contract_ext_id IS NOT NULL 조건으로 계약 미연결 이벤트(있다면)는 제약 대상에서 제외한다.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_commission_event_contract "
        "ON sales_commission_events (contract_ext_id) "
        "WHERE contract_ext_id IS NOT NULL AND status <> 'VOID'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sales_commission_event_contract")
    op.execute("DROP INDEX IF EXISTS uq_sales_sub_winner_unit")
    op.execute("DROP INDEX IF EXISTS uq_sales_contract_active_unit")
