"""집행 원장(DisbursementEvent) 회귀가드 (설계도 §13 영속).

해시체인 결정성(변조탐지 기반) + DB 미가용 graceful(never-raise·수지 무손상)을 고정한다.
실 DB 연동(lazy-DDL 자가 프로비저닝·append/read)은 통합 환경(asyncpg)에서 검증.
"""
from __future__ import annotations

import asyncio

from app.services.feasibility.disbursement_ledger_service import (
    _content_hash,
    append_disbursement,
    list_disbursements,
)


def test_content_hash_is_deterministic_and_order_independent():
    """동일 내용 → 동일 해시(키 순서 무관) — 변조탐지 체인의 기반."""
    a = {"amount_won": 100, "line_item_key": "토지비::토지매입", "memo": "1차"}
    b = {"memo": "1차", "line_item_key": "토지비::토지매입", "amount_won": 100}
    assert _content_hash(a) == _content_hash(b)
    # 내용이 바뀌면 해시도 바뀐다(위변조 감지).
    assert _content_hash(a) != _content_hash({**a, "amount_won": 101})


def test_graceful_when_db_unavailable():
    """DB 미가용 → list={}·append persisted=False (절대 raise 안 함·수지 무손상)."""
    async def _run():
        lst = await list_disbursements("proj-x")
        ap = await append_disbursement(
            project_id="proj-x", line_item_key="토지비::토지매입", amount_won=1000
        )
        return lst, ap

    lst, ap = asyncio.run(_run())
    assert lst == {}
    assert ap["persisted"] is False
    assert isinstance(ap.get("content_hash"), str)
