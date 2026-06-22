"""Fix #3(감사 HIGH): 파이프라인 결정론 산출(cost/feasibility) → 분석원장 write-back.

배경: /run·/report가 cost/feasibility 결정론 수치를 산출하지만 분석원장에 적재하지 않아
모순탐지·lineage·SSOT 단일출처에서 누락됐다(어댑터는 v2_feasibility/cost 별도 엔드포인트 전용).
이 테스트는 파이프라인 stage data → 원장 어댑터 인자 매핑과 best-effort 적재 오케스트레이션을 고정한다.
"""
import pytest

from app.services.pipeline.pipeline_ledger_writeback import (
    cost_stage_to_adapter,
    extract_chain_ids,
    feasibility_stage_to_adapter,
    record_pipeline_results,
)

COST = {
    "total_construction_cost": 3_000_000_000,
    "direct_cost": 2_000_000_000,
    "cost_per_pyeong": 5_500_000,
    "total_gfa_pyeong": 545.4,
    "cost_breakdown": {"direct_cost": 2_000_000_000, "total_project_cost": 3_000_000_000},
}
DESIGN = {"building_type": "공동주택", "structure_type": "RC", "total_gfa_sqm": 1803.0}
FEAS = {
    "total_revenue_won": 5_000_000_000, "total_revenue": 5_000_000_000,
    "net_profit_won": 1_000_000_000, "net_profit": 1_000_000_000,
    "profit_rate_pct": 25.0, "grade": "A",
}
SITE = {"basic": {"address": "서울 강남구 역삼동 1", "pnu": "1168010100"}}


def test_cost_mapper_total_direct_indirect():
    summary, header = cost_stage_to_adapter(COST, DESIGN)
    assert summary["total"] == 3_000_000_000
    assert summary["direct"] == 2_000_000_000
    assert summary["indirect"] == 1_000_000_000  # total - direct(파생, 무날조)
    assert header["building_type"] == "공동주택"
    assert header["structure_type"] == "RC"
    assert header["total_gfa_sqm"] == 1803.0


def test_cost_mapper_indirect_none_when_unknown():
    # direct 미상이면 indirect 날조 금지(None).
    summary, _ = cost_stage_to_adapter({"total_construction_cost": 3_000_000_000}, DESIGN)
    assert summary["total"] == 3_000_000_000
    assert summary["direct"] is None
    assert summary["indirect"] is None


def test_feasibility_mapper_maps_aliases_and_dev_type():
    r = feasibility_stage_to_adapter(FEAS, DESIGN)
    assert r["total_revenue_won"] == 5_000_000_000
    assert r["net_profit_won"] == 1_000_000_000
    assert r["profit_rate_pct"] == 25.0
    assert r["grade"] == "A"
    assert r["development_type"] == "공동주택"
    assert r["npv_won"] is None  # 부재 시 정직 None


def test_extract_chain_ids_from_basic():
    ids = extract_chain_ids({"site_analysis": {"data": SITE}})
    assert ids["pnu"] == "1168010100"
    assert ids["address"].startswith("서울")


@pytest.mark.asyncio
async def test_record_pipeline_results_calls_both_recorders():
    calls: dict = {}

    async def fake_cost(**kw):
        calls["cost"] = kw
        return {"ok": True}

    async def fake_feas(**kw):
        calls["feas"] = kw
        return {"ok": True, "contradictions": {"contradictions": []}}

    stages = {
        "site_analysis": {"data": SITE},
        "design": {"data": DESIGN},
        "cost": {"data": COST},
        "feasibility": {"data": FEAS},
    }
    out = await record_pipeline_results(
        stages=stages, project_id="p1", tenant_id="t1",
        cost_recorder=fake_cost, feasibility_recorder=fake_feas)
    assert out["cost"]["ok"] and out["feasibility"]["ok"]
    assert calls["cost"]["summary"]["total"] == 3_000_000_000
    assert calls["cost"]["tenant_id"] == "t1"
    assert calls["cost"]["project_id"] == "p1"
    assert calls["feas"]["result"]["profit_rate_pct"] == 25.0
    assert calls["feas"]["pnu"] == "1168010100"


@pytest.mark.asyncio
async def test_record_skips_without_chain_id():
    called = {"n": 0}

    async def fake(**kw):
        called["n"] += 1
        return {}

    out = await record_pipeline_results(
        stages={"cost": {"data": COST}},
        cost_recorder=fake, feasibility_recorder=fake)
    assert out == {}
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_record_skips_empty_stages():
    async def fake(**kw):
        raise AssertionError("빈 stage인데 적재가 호출됨")

    out = await record_pipeline_results(
        stages={"site_analysis": {"data": SITE}}, project_id="p1",
        cost_recorder=fake, feasibility_recorder=fake)
    assert out == {}  # cost/feasibility data 없음 → 적재 없음


@pytest.mark.asyncio
async def test_record_best_effort_swallows_recorder_error():
    async def boom(**kw):
        raise RuntimeError("ledger down")

    async def fake_feas(**kw):
        return {"ok": True}

    # cost 적재가 터져도 feasibility는 적재되고 전체는 무중단(best-effort).
    out = await record_pipeline_results(
        stages={"site_analysis": {"data": SITE}, "design": {"data": DESIGN},
                "cost": {"data": COST}, "feasibility": {"data": FEAS}},
        project_id="p1", cost_recorder=boom, feasibility_recorder=fake_feas)
    assert "cost" not in out  # 실패는 결과에서 생략(정직)
    assert out["feasibility"]["ok"]
