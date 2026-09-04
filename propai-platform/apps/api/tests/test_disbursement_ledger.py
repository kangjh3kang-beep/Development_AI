"""집행 원장(DisbursementEvent) 회귀가드 (설계도 §13 영속).

정통 해시체인(prev_hash·seq를 해시 입력에 접어넣어 캐스케이드 변조탐지) + tenant 스코프 +
DB 미가용 graceful(never-raise·수지 무손상)을 고정한다. 실 DB append/read/verify는 asyncpg
통합 환경에서 검증.
"""
from __future__ import annotations

import asyncio

from app.services.feasibility.disbursement_ledger_service import (
    _chain_hash,
    append_disbursement,
    list_disbursements,
    verify_chain,
)


def test_chain_hash_folds_prev_and_seq():
    """★prev_hash·seq가 해시 입력에 접혀 캐스케이드 — 중간 변조 시 후행 전체가 깨진다."""
    p = {"amount_won": 100, "line_item_key": "토지비::토지매입"}
    genesis = _chain_hash(p, None, 1)
    chained = _chain_hash(p, "abc123", 2)
    # 동일 payload여도 prev/seq가 다르면 해시가 다르다(정통 체인).
    assert genesis != chained
    # prev가 바뀌면 해시가 바뀐다(캐스케이드).
    assert _chain_hash(p, "abc123", 2) != _chain_hash(p, "xyz999", 2)
    # 내용이 바뀌어도 해시가 바뀐다(위변조 감지).
    assert _chain_hash(p, None, 1) != _chain_hash({**p, "amount_won": 101}, None, 1)


def test_graceful_when_db_unavailable():
    """DB 미가용 → list={}·append persisted=False·verify ok=None (절대 raise 안 함·수지 무손상)."""
    async def _run():
        return (
            await list_disbursements("t1", "proj-x"),
            await append_disbursement(
                tenant_id="t1", project_id="proj-x",
                line_item_key="토지비::토지매입", amount_won=1000, created_by="u1",
            ),
            await verify_chain("t1", "proj-x", "토지비::토지매입"),
        )

    lst, ap, vf = asyncio.run(_run())
    assert lst == {}
    assert ap["persisted"] is False
    assert vf["ok"] is None
