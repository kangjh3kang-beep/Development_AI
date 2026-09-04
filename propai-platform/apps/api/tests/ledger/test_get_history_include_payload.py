"""get_history(include_payload=True) — 상세 비교 화면 옵트인 payload 노출.

append 경로(해시체인 버전·해시)는 이 변경으로 건드리지 않는다(read 확장만). 기본값(False)은
기존 응답과 바이트 동일해야 한다(payload 키 자체가 없음 — 무회귀).
"""
from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_get_history_default_omits_payload(ledger_db, tnt):
    from app.services.ledger import analysis_ledger_service as als

    pnu = f"P{uuid.uuid4().hex[:10]}"
    res = await als.append_analysis(analysis_type="site_analysis", payload={"v": 1}, tenant_id=tnt, pnu=pnu)
    assert res["ok"] is True

    history = await als.get_history(analysis_type="site_analysis", tenant_id=tnt, pnu=pnu)
    assert len(history) == 1
    assert "payload" not in history[0]  # 기본값 False — 기존 응답과 무회귀


@pytest.mark.asyncio
async def test_get_history_include_payload_true_returns_stored_payload_newest_first(ledger_db, tnt):
    from app.services.ledger import analysis_ledger_service as als

    pnu = f"P{uuid.uuid4().hex[:10]}"
    await als.append_analysis(analysis_type="site_analysis", payload={"v": 1, "note": "a"},
                               tenant_id=tnt, pnu=pnu)
    await als.append_analysis(analysis_type="site_analysis", payload={"v": 2, "note": "b"},
                               tenant_id=tnt, pnu=pnu)

    history = await als.get_history(
        analysis_type="site_analysis", tenant_id=tnt, pnu=pnu, include_payload=True)
    assert len(history) == 2
    assert history[0]["version"] == 2  # 최신순(version DESC)
    assert history[0]["payload"] == {"v": 2, "note": "b"}
    assert history[1]["version"] == 1
    assert history[1]["payload"] == {"v": 1, "note": "a"}


@pytest.mark.asyncio
async def test_get_history_include_payload_respects_limit(ledger_db, tnt):
    from app.services.ledger import analysis_ledger_service as als

    pnu = f"P{uuid.uuid4().hex[:10]}"
    for i in range(3):
        await als.append_analysis(analysis_type="site_analysis", payload={"v": i}, tenant_id=tnt, pnu=pnu)

    history = await als.get_history(
        analysis_type="site_analysis", tenant_id=tnt, pnu=pnu, limit=2, include_payload=True)
    assert len(history) == 2
    assert all("payload" in h for h in history)
