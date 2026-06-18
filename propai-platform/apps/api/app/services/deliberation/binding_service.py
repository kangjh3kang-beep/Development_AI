"""중심 엔진 통합 — run_id ↔ 테넌트 결속 + 멱등(engine_run_binding).

엔진은 테넌트-블라인드(get_analysis 무필터)이므로 BFF가 이 테이블로 (1) GET 프록시 시 테넌트 소유 검증
(교차테넌트 read 차단), (2) (tenant, content_input_hash, snapshot_id) 멱등키로 동일 입력 재호출 방지
(비원자 2단계 쓰기 안전, §9 R6/R7)를 강제한다. 원장(analysis_ledger_service)과 동일한 런타임 _ensure 패턴.
public 스키마(엔진 review와 동일 propai_db). 설계: docs/CENTRAL_ENGINE_INTEGRATION_DESIGN.md §9·§12.
"""
from __future__ import annotations

import json
from typing import Any

_DDL = (
    "CREATE TABLE IF NOT EXISTS engine_run_binding ("
    "  run_id text PRIMARY KEY,"           # sync=엔진 analysis_run.id, async=BFF 발급 uuid
    "  engine_task_id text,"
    "  source text NOT NULL,"              # 'sync' | 'async'
    "  tenant_id text NOT NULL,"
    "  project_id text,"
    "  created_by text,"
    "  input_hash text NOT NULL,"          # 엔진 AnalysisResult.input_hash(snapshot 포함)
    "  content_input_hash text NOT NULL,"  # snapshot 제외 멱등/lineage 키
    "  snapshot_id text,"
    "  status text,"
    "  result jsonb,"                      # async 영속본(엔진 미저장 대비)
    "  deterministic boolean NOT NULL DEFAULT true,"  # 비결정(VLLM/라이브) run은 멱등 dedup 제외
    "  created_at timestamptz DEFAULT now()"
    ")"
)
# ★부분 유니크 — deterministic run만 (tenant, content_input_hash, snapshot) 멱등 dedup. 비결정 run은
# PK(run_id)로만 유일(매 호출 별 행 — VLLM/라이브 재분석 차단 금지, §3·§9 R7). coalesce로 NULL 중복 회피.
_UX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_run_binding_idem_det "
    "ON engine_run_binding(tenant_id, content_input_hash, coalesce(snapshot_id, '')) "
    "WHERE deterministic"
)
_IDX = (
    "CREATE INDEX IF NOT EXISTS idx_run_binding_tenant_run "
    "ON engine_run_binding(tenant_id, run_id)"
)


async def _ensure(db) -> None:
    from sqlalchemy import text

    await db.execute(text(_DDL))
    # 기존 테이블 진화(런타임 _ensure 멱등) — 컬럼 보강 + 구 비-partial 인덱스 제거 후 partial 재생성.
    await db.execute(text(
        "ALTER TABLE engine_run_binding ADD COLUMN IF NOT EXISTS deterministic boolean NOT NULL DEFAULT true"))
    await db.execute(text("DROP INDEX IF EXISTS ux_run_binding_idem"))
    await db.execute(text(_UX))
    await db.execute(text(_IDX))


async def lookup(*, tenant_id: str, content_input_hash: str, snapshot_id: str | None) -> dict[str, Any] | None:
    """멱등키로 기존 결속 조회. 없으면 None. (테넌트 소유 GET 검증·멱등 재사용 공용.)"""
    from sqlalchemy import text

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        await _ensure(db)
        row = (await db.execute(
            text(
                "SELECT run_id, source, status, result, input_hash FROM engine_run_binding "
                "WHERE tenant_id = :t AND content_input_hash = :c "
                "AND coalesce(snapshot_id, '') = coalesce(:s, '')"
            ),
            {"t": tenant_id, "c": content_input_hash, "s": snapshot_id},
        )).first()
        await db.commit()
    if row is None:
        return None
    return {"run_id": row[0], "source": row[1], "status": row[2], "result": row[3], "input_hash": row[4]}


async def lookup_by_run(*, tenant_id: str, run_id: str) -> dict[str, Any] | None:
    """GET 프록시 테넌트 소유 검증 — (tenant, run_id) 일치 시만 반환(불일치/미존재 None→404)."""
    from sqlalchemy import text

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        await _ensure(db)
        row = (await db.execute(
            text(
                "SELECT run_id, source, status, result, input_hash FROM engine_run_binding "
                "WHERE tenant_id = :t AND run_id = :r"
            ),
            {"t": tenant_id, "r": run_id},
        )).first()
        await db.commit()
    if row is None:
        return None
    return {"run_id": row[0], "source": row[1], "status": row[2], "result": row[3], "input_hash": row[4]}


async def insert(
    *,
    run_id: str,
    tenant_id: str,
    content_input_hash: str,
    snapshot_id: str | None,
    input_hash: str,
    source: str,
    project_id: str | None = None,
    created_by: str | None = None,
    status: str | None = None,
    engine_task_id: str | None = None,
    result: dict[str, Any] | None = None,
    deterministic: bool = True,
) -> bool:
    """멱등 결속 삽입. True=신규 삽입, False=기존 존재(deterministic run만 ON CONFLICT DO NOTHING).

    deterministic=False(VLLM/라이브)는 부분 유니크 인덱스 대상 외 → 매 호출 신규 행(PK run_id 유일).
    """
    from sqlalchemy import text

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        await _ensure(db)
        res = await db.execute(
            text(
                "INSERT INTO engine_run_binding"
                "(run_id, engine_task_id, source, tenant_id, project_id, created_by,"
                " input_hash, content_input_hash, snapshot_id, status, result, deterministic) "
                "VALUES (:run_id, :etid, :src, :t, :pid, :cb,"
                " :ih, :cih, :sid, :st, cast(:res as jsonb), :det) "
                "ON CONFLICT (tenant_id, content_input_hash, coalesce(snapshot_id, '')) "
                "WHERE deterministic DO NOTHING"
            ),
            {
                "run_id": run_id, "etid": engine_task_id, "src": source, "t": tenant_id,
                "pid": project_id, "cb": created_by, "ih": input_hash,
                "cih": content_input_hash, "sid": snapshot_id, "st": status,
                "res": json.dumps(result) if result is not None else None,
                "det": deterministic,
            },
        )
        await db.commit()
        return (res.rowcount or 0) > 0
