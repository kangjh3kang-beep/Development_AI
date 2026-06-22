"""심의 엔진 run_id ↔ 테넌트 결속 + 멱등(engine_run_binding 테이블).

엔진은 테넌트를 모르므로(테넌트-블라인드) BFF가 이 테이블로 두 가지를 강제한다.
1) 테넌트 소유 검증 — (tenant, run_id)가 일치할 때만 결과를 돌려준다(교차테넌트 read 차단).
2) 멱등 — (tenant, content_input_hash, snapshot_id)가 같으면 기존 run을 재사용(엔진 재호출 방지).

스키마는 핫패스 첫 호출 시 _ensure가 1회 자동 생성한다(alembic 미적용 환경 폴백).
원장 서비스(analysis_ledger_service)와 동일한 raw SQL _ensure 패턴.
설계 참조: ../ledger/analysis_ledger_service.py
"""
from __future__ import annotations

import json
from typing import Any

_DDL = (
    "CREATE TABLE IF NOT EXISTS engine_run_binding ("
    "  run_id text PRIMARY KEY,"            # 엔진 analysis_run.id 또는 BFF 발급 uuid
    "  source text NOT NULL,"               # 'sync'
    "  tenant_id text NOT NULL,"            # ★테넌트 결속(교차테넌트 read 차단의 핵심)
    "  project_id text,"
    "  created_by text,"
    "  input_hash text NOT NULL,"           # 엔진 결과 input_hash(snapshot 포함)
    "  content_input_hash text NOT NULL,"   # snapshot 제외 멱등키
    "  snapshot_id text,"
    "  status text,"
    "  result jsonb,"                       # 결과 영속본(평소 조회 권위본)
    "  deterministic boolean NOT NULL DEFAULT true,"  # 비결정 run은 멱등 dedup 제외
    "  created_at timestamptz DEFAULT now()"
    ")"
)
# 부분 유니크 — deterministic run만 (tenant, content_input_hash, snapshot) 멱등 dedup.
# 비결정(라이브) run은 PK(run_id)로만 유일 → 매 호출 별 행(재분석 차단 금지).
_UX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_run_binding_idem_det "
    "ON engine_run_binding(tenant_id, content_input_hash, coalesce(snapshot_id, '')) "
    "WHERE deterministic"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_run_binding_tenant_run "
    "ON engine_run_binding(tenant_id, run_id)"
)

# 핫패스 DDL 왕복(카탈로그 잠금·지연)을 막기 위해 프로세스 1회만 실행.
_ensured = False


async def _ensure(db) -> None:
    """테이블·인덱스 멱등 생성(프로세스 1회). raw SQL — ORM 마이그레이션 의존 없음."""
    global _ensured
    if _ensured:
        return
    from sqlalchemy import text

    await db.execute(text(_DDL))
    await db.execute(text(_UX))
    await db.execute(text(_IDX))
    _ensured = True


async def lookup(
    *, tenant_id: str, content_input_hash: str, snapshot_id: str | None
) -> dict[str, Any] | None:
    """멱등키로 기존 결속 조회 — 없으면 None. 동일 입력 재요청 시 엔진 재호출을 막는 데 쓴다."""
    from sqlalchemy import text

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        await _ensure(db)
        row = (
            await db.execute(
                text(
                    "SELECT run_id, source, status, result, input_hash FROM engine_run_binding "
                    "WHERE tenant_id = :t AND content_input_hash = :c "
                    "AND coalesce(snapshot_id, '') = coalesce(:s, '')"
                ),
                {"t": tenant_id, "c": content_input_hash, "s": snapshot_id},
            )
        ).first()
        await db.commit()
    if row is None:
        return None
    return {"run_id": row[0], "source": row[1], "status": row[2],
            "result": row[3], "input_hash": row[4]}


async def lookup_by_run(*, tenant_id: str, run_id: str) -> dict[str, Any] | None:
    """★테넌트 소유 검증 — (tenant, run_id)가 일치할 때만 반환.

    불일치/미존재면 None(라우터는 404). 다른 테넌트의 run_id를 알아도 결과를 못 읽게 한다.
    """
    from sqlalchemy import text

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        await _ensure(db)
        row = (
            await db.execute(
                text(
                    "SELECT run_id, source, status, result, input_hash "
                    "FROM engine_run_binding WHERE tenant_id = :t AND run_id = :r"
                ),
                {"t": tenant_id, "r": run_id},
            )
        ).first()
        await db.commit()
    if row is None:
        return None
    return {"run_id": row[0], "source": row[1], "status": row[2],
            "result": row[3], "input_hash": row[4]}


async def insert(
    *,
    run_id: str,
    tenant_id: str,
    content_input_hash: str,
    snapshot_id: str | None,
    input_hash: str,
    source: str = "sync",
    project_id: str | None = None,
    created_by: str | None = None,
    status: str | None = None,
    result: dict[str, Any] | None = None,
    deterministic: bool = True,
) -> bool:
    """결속 삽입(멱등). True=신규 삽입, False=이미 존재(deterministic run 멱등 충돌).

    deterministic=False(라이브)는 부분 유니크 대상 외 → 매 호출 신규 행(PK run_id 유일).
    """
    from sqlalchemy import text

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        await _ensure(db)
        res = await db.execute(
            text(
                "INSERT INTO engine_run_binding"
                "(run_id, source, tenant_id, project_id, created_by,"
                " input_hash, content_input_hash, snapshot_id, status, result, deterministic) "
                "VALUES (:run_id, :src, :t, :pid, :cb,"
                " :ih, :cih, :sid, :st, cast(:res as jsonb), :det) "
                "ON CONFLICT (tenant_id, content_input_hash, coalesce(snapshot_id, '')) "
                "WHERE deterministic DO NOTHING"
            ),
            {
                "run_id": run_id, "src": source, "t": tenant_id,
                "pid": project_id, "cb": created_by, "ih": input_hash,
                "cih": content_input_hash, "sid": snapshot_id, "st": status,
                "res": json.dumps(result) if result is not None else None,
                "det": deterministic,
            },
        )
        await db.commit()
        return (res.rowcount or 0) > 0
