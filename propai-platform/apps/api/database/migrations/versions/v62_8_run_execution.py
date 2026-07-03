"""v62 C2R P0 — run_execution 추적 테이블(정본).

Revision ID: v62_8_run_execution
Revises: 034_ledger_unique_version, 041_sales_unit_events_ledger
Create Date: 2026-07-03

C2R/HITL run 추적 1테이블(run_execution). ORM(database/models/run_execution.py)
메타데이터로 create_all(멱등) — __table_args__ 의 인덱스/UNIQUE(idempotency_key) 함께 생성.

★현재 alembic 히스토리가 2개 head(034_ledger_unique_version · 041_sales_unit_events_ledger)로
  분기돼 `upgrade head`가 모호하던 상태였다. 본 리비전이 **두 head를 튜플 down_revision 으로
  병합**해 단일 head로 정상화한다(v62_1_sales_tables·032_sales_admin_accounting_tables 관례 동일).
  한쪽 head만 체이닝하면 다른 head가 미병합으로 남아 3-head 로 악화된다.

★부팅 강제 부재: 이 프로젝트는 배포/부팅에 alembic upgrade 를 강제하지 않으므로(안전망은
  서비스별 ensure_schema), run_execution 은 이 마이그레이션 + run_store.ensure_schema 이중
  경로로 생성된다. 둘 다 동일 ORM 메타를 단일원천으로 쓰므로 드리프트가 없다.
"""
from alembic import op

revision = "v62_8_run_execution"
down_revision = ("034_ledger_unique_version", "041_sales_unit_events_ledger")
branch_labels = None
depends_on = None

_NEW = {"run_execution"}


def _tables():
    import apps.api.database.models.run_execution  # noqa: F401  (Base.metadata 등록)
    from apps.api.database.models.base import Base

    # ★sorted_tables 대신 tables dict 직접 접근. sorted_tables 는 전체 metadata 를 위상정렬하며
    #   모든 FK 를 resolve 하는데, 테스트/부분 import 상태에서 다른 모델의 FK 대상 테이블(예:
    #   collaborator_invites→organizations)이 metadata 에 없으면 NoReferencedTableError 로 깨진다.
    #   run_execution 은 FK 가 없어 dict 직접 접근으로 안전하며, create_all/drop_all 동작은 동일.
    return [Base.metadata.tables[n] for n in _NEW if n in Base.metadata.tables]


def upgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base

    # 테이블 + (ORM __table_args__/컬럼의) 인덱스·UNIQUE(idempotency_key) 를 멱등 생성.
    Base.metadata.create_all(bind=bind, tables=_tables(), checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    from apps.api.database.models.base import Base

    Base.metadata.drop_all(bind=bind, tables=list(reversed(_tables())), checkfirst=True)
