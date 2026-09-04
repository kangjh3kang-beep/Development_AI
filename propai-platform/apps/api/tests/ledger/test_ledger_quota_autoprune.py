"""쿼터 초과 시 자동 프룬(prune_old_versions) 배선 — 무조건 거부 대신 선제 정리 후 재검사.

쿼터 자체는 상향하지 않는다(운영 결정) — 기존 prune_old_versions(keep_per_chain=5)를 재사용해
초과 시 1회 선제 정리 후 재검사하고, 그래도 초과면 기존과 동일하게 정직 거부한다.
"""
from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_quota_exceeded_triggers_autoprune_then_succeeds(ledger_db, tnt):
    from app.services.ledger import analysis_ledger_service as als

    await als.set_quota(tnt, 6)
    pnu = f"P{uuid.uuid4().hex[:10]}"

    # 같은 체인(pnu 고정)에 서로 다른 payload로 6회 append → 정확히 쿼터(6)에 도달.
    for i in range(6):
        res = await als.append_analysis(
            analysis_type="site_analysis", payload={"v": i}, tenant_id=tnt, pnu=pnu)
        assert res["ok"] is True, res

    usage_before = await als.get_usage(tnt)
    assert usage_before["used"] == 6

    # 7번째(새 payload) — used(6) >= quota(6) → 자동 프룬(keep 5, 체인 버전 6>5라 1개 삭제)
    # → count 5 → 재검사(5<6) 통과 → 정상 적재.
    res7 = await als.append_analysis(
        analysis_type="site_analysis", payload={"v": 6}, tenant_id=tnt, pnu=pnu)
    assert res7["ok"] is True
    assert not res7.get("quota_exceeded")
    assert res7["version"] == 7

    history = await als.get_history(analysis_type="site_analysis", tenant_id=tnt, pnu=pnu, limit=10)
    versions = sorted(h["version"] for h in history)
    # 프룬은 '재검사 이전에 이미 있던' 6개(버전 1~6)를 keep_per_chain(5)로 줄인다(버전 1 삭제 →
    # 2~6 유지) — 그 뒤에 7번째가 새로 적재되므로 최종 행 수는 keep_per_chain+1(=6)이 된다.
    assert versions == [2, 3, 4, 5, 6, 7], versions


@pytest.mark.asyncio
async def test_quota_exceeded_still_rejected_when_prune_cannot_reduce(ledger_db, tnt):
    """체인이 여러 개로 분산돼 각 체인 버전수가 keep_per_chain(5) 이하면 프룬이 못 줄인다 — 정직 거부."""
    from app.services.ledger import analysis_ledger_service as als

    await als.set_quota(tnt, 2)
    # 서로 다른 체인(pnu) 2개에 1버전씩 — 쿼터(2) 도달, 각 체인 버전수(1) < keep(5)라 프룬 무효.
    await als.append_analysis(analysis_type="site_analysis", payload={"v": 1},
                               tenant_id=tnt, pnu=f"PA{uuid.uuid4().hex[:8]}")
    await als.append_analysis(analysis_type="site_analysis", payload={"v": 1},
                               tenant_id=tnt, pnu=f"PB{uuid.uuid4().hex[:8]}")

    res = await als.append_analysis(analysis_type="site_analysis", payload={"v": 1},
                                     tenant_id=tnt, pnu=f"PC{uuid.uuid4().hex[:8]}")
    assert res["ok"] is False
    assert res.get("quota_exceeded") is True
    assert res["used"] == 2 and res["quota"] == 2
