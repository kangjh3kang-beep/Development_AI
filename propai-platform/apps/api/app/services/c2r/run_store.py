"""run_execution 저장소 — C2R run 추적 레코드 CRUD + 멱등 스키마 보장.

★부팅 시 alembic upgrade 가 강제되지 않으므로(배포 경로·main.py 어디에도 없음, 안전망은
  서비스별 ensure_schema), 이 저장소가 소비 시점에 ensure_schema() 로 run_execution 테이블을
  멱등 생성한다(정본은 마이그레이션 v62_8_run_execution, 여기는 부팅/소비 안전망).
  ORM 메타데이터를 단일 진실원천으로 create_all 하므로 스키마 드리프트가 없다.

무목업: 실제 DB 왕복(insert/select)만 한다. 가짜 레코드/폴백 없음.
"""

from __future__ import annotations

import uuid
from typing import Any

from packages.schemas.run_state import RunStateEnum
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.base import Base
from apps.api.database.models.run_execution import RunExecution


async def ensure_schema(db: AsyncSession) -> None:
    """run_execution 테이블을 멱등 생성(부팅/소비 안전망).

    ORM 메타를 단일원천으로 create_all(checkfirst=True) — 이미 있으면 no-op.
    run_execution 은 신규 테이블이라 UNIQUE(idempotency_key)를 포함해 최초 생성해도 안전
    (기존행 없음 → lazy-DDL UNIQUE 선정리 문제 없음).
    """
    conn = await db.connection()
    try:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=[RunExecution.__table__], checkfirst=True
            )
        )
    except ProgrammingError:
        # 생애 최초 동시 호출 경합: checkfirst 는 has_table→CREATE 사이에 락이 없어, 두 요청이
        # 동시에 통과하면 한쪽이 'relation already exists'를 만날 수 있다. 목적(테이블 존재)은
        # 이미 달성됐으므로 롤백 후 정상 진행한다(자가치유·무목업). 배포 시엔 정본 마이그레이션이
        # 선생성하므로 이 창은 실무상 생애 최초 1회뿐이다.
        await db.rollback()


async def get_run(db: AsyncSession, run_id: str) -> RunExecution | None:
    """run_id 로 단건 조회(없으면 None)."""
    return await db.get(RunExecution, run_id)


async def get_run_by_idempotency(
    db: AsyncSession, idempotency_key: str
) -> RunExecution | None:
    """멱등키로 기존 run 조회(없으면 None)."""
    res = await db.execute(
        select(RunExecution).where(RunExecution.idempotency_key == idempotency_key)
    )
    return res.scalar_one_or_none()


async def create_run(
    db: AsyncSession,
    *,
    project_id: str | None = None,
    tenant_id: str | None = None,
    track: str | None = None,
    s_phase: str | None = None,
    state: str = RunStateEnum.DRAFT.value,
    parent_run_id: str | None = None,
    input_hash: str | None = None,
    artifact_uri: str | None = None,
    approval_gate_json: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> RunExecution:
    """run_execution 레코드 생성.

    idempotency_key 가 주어지면 멱등: 이미 있으면 기존 레코드를 반환(중복 생성 금지).
    동시 요청 경합은 UNIQUE 제약이 최종 방어 — IntegrityError 시 롤백 후 기존행 재조회.
    """
    if idempotency_key:
        existing = await get_run_by_idempotency(db, idempotency_key)
        if existing is not None:
            return existing

    row = RunExecution(
        run_id=str(uuid.uuid4()),
        project_id=project_id,
        tenant_id=tenant_id,
        track=track,
        s_phase=s_phase,
        state=state,
        parent_run_id=parent_run_id,
        input_hash=input_hash,
        artifact_uri=artifact_uri,
        approval_gate_json=approval_gate_json,
        idempotency_key=idempotency_key,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # 동시 요청이 같은 idempotency_key 를 먼저 커밋한 경합 — 롤백 후 기존행 반환(멱등).
        await db.rollback()
        if idempotency_key:
            existing = await get_run_by_idempotency(db, idempotency_key)
            if existing is not None:
                return existing
        raise
    await db.refresh(row)
    return row


async def update_state(
    db: AsyncSession, run_id: str, state: str
) -> RunExecution | None:
    """run 상태 전이(없으면 None). state 는 RunStateEnum 값 문자열."""
    row = await db.get(RunExecution, run_id)
    if row is None:
        return None
    row.state = state
    await db.commit()
    await db.refresh(row)
    return row
