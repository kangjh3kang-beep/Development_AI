"""W3-4(스펙 P) 소비 배선 테스트 — auto_recommend_top3 opt-in 최적화 파이프라인.

검증 범위:
1. 기본값(use_optimization_pipeline 미지정/False) — 기존 출력과 바이트 단위 동일
   (optimization_pipeline 키 없음, 나머지 키 전부 무회귀).
2. opt-in(True) — result["optimization_pipeline"]이 additive로 부착되고 기존 키는 무손상.
3. 동일 seed 재현성 — 두 번 호출 시 shortlist 순서·내용 동일.
4. Pareto front가 이미 계산된 net_profit_won/profit_rate_pct/permit_complexity를
   그대로 소비(중복 재계산 없음 — evaluator_grade="precise" 정직 표기).

mocking 패턴은 tests/test_silent_fallback_disclosure.py의 _install_stubs를 재사용(동일 방식).
"""
from __future__ import annotations

import pytest

from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.land_intelligence import far_tier_service as far_tier_module
from app.services.land_intelligence import ordinance_service as ordinance_module
from app.services.zoning import auto_zoning_service as auto_zoning_module

pytestmark = pytest.mark.asyncio

ADDR = "서울특별시 강남구 역삼동 736"


def _zoning_result() -> dict:
    return {
        "zone_type": "제2종일반주거지역",
        "zone_limits": {"max_bcr_pct": 60, "max_far_pct": 250},
        "land_area_sqm": 1000.0,
        "official_price_per_sqm": 3_000_000,
        "special_districts": [],
        "land_category": "대",
    }


def _install_stubs(monkeypatch):
    async def _fake_analyze(self, address):
        return _zoning_result()

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):
        return {}

    def _fake_calc_effective_far(base, zone_type, land_area):
        return {"effective_far_pct": 200.0, "effective_bcr_pct": 50.0, "far_basis": "테스트고정"}

    monkeypatch.setattr(auto_zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance)
    monkeypatch.setattr(far_tier_module, "calc_effective_far", _fake_calc_effective_far)


async def test_기본값_무회귀_optimization_pipeline_키_없음(monkeypatch):
    _install_stubs(monkeypatch)
    svc = FeasibilityServiceV2()

    out_default = await svc.auto_recommend_top3(address=ADDR, land_area_sqm=1000.0, use_llm=False)
    out_explicit_false = await svc.auto_recommend_top3(
        address=ADDR, land_area_sqm=1000.0, use_llm=False, use_optimization_pipeline=False,
    )

    assert "optimization_pipeline" not in out_default
    assert "optimization_pipeline" not in out_explicit_false
    # 기존 계약 키는 무손상(회귀 0).
    assert out_default["recommendations"] == out_explicit_false["recommendations"]
    assert out_default["all_results"] == out_explicit_false["all_results"]


async def test_optin_additive_기존키_무손상(monkeypatch):
    _install_stubs(monkeypatch)
    svc = FeasibilityServiceV2()

    baseline = await svc.auto_recommend_top3(address=ADDR, land_area_sqm=1000.0, use_llm=False)
    optin = await svc.auto_recommend_top3(
        address=ADDR, land_area_sqm=1000.0, use_llm=False, use_optimization_pipeline=True,
    )

    assert "optimization_pipeline" in optin
    # additive — optimization_pipeline을 제외한 나머지 키는 기존 출력과 동일.
    optin_without_pipeline = {k: v for k, v in optin.items() if k != "optimization_pipeline"}
    assert optin_without_pipeline == baseline


async def test_optimization_pipeline_형상(monkeypatch):
    _install_stubs(monkeypatch)
    svc = FeasibilityServiceV2()
    out = await svc.auto_recommend_top3(
        address=ADDR, land_area_sqm=1000.0, use_llm=False, use_optimization_pipeline=True,
    )
    pipeline = out["optimization_pipeline"]

    assert pipeline["sampling_method"] == "full_enumeration"
    assert pipeline["evaluator_grade"] == "precise"
    assert pipeline["candidates_generated"] == len(out["all_results"])
    assert pipeline["hard_filter_survivors"] == pipeline["candidates_generated"]
    assert 0 < len(pipeline["shortlist"]) <= 3
    assert pipeline["pareto_front_size"] >= len(pipeline["shortlist"])

    # shortlist 항목의 objectives는 all_results의 원본 feasibility/permit 값과 정확히 일치
    # (중복 재계산 없이 그대로 재사용했는지 검증).
    by_type = {r["development_type"]: r for r in out["all_results"]}
    for item in pipeline["shortlist"]:
        r = by_type[item["development_type"]]
        assert item["objectives"]["net_profit_won"] == pytest.approx(float(r["feasibility"]["net_profit_won"]))
        assert item["objectives"]["profit_rate_pct"] == pytest.approx(float(r["feasibility"]["profit_rate_pct"]))
        assert item["objectives"]["permit_complexity"] == float(r["permit"]["permit_complexity"])
        assert "Pareto front" in item["reason"]


async def test_seed_재현성(monkeypatch):
    _install_stubs(monkeypatch)
    svc = FeasibilityServiceV2()

    out1 = await svc.auto_recommend_top3(
        address=ADDR, land_area_sqm=1000.0, use_llm=False,
        use_optimization_pipeline=True, optimization_seed=7,
    )
    out2 = await svc.auto_recommend_top3(
        address=ADDR, land_area_sqm=1000.0, use_llm=False,
        use_optimization_pipeline=True, optimization_seed=7,
    )
    assert out1["optimization_pipeline"]["shortlist"] == out2["optimization_pipeline"]["shortlist"]


async def test_shortlist_k_파라미터(monkeypatch):
    _install_stubs(monkeypatch)
    svc = FeasibilityServiceV2()
    out = await svc.auto_recommend_top3(
        address=ADDR, land_area_sqm=1000.0, use_llm=False,
        use_optimization_pipeline=True, optimization_shortlist_k=1,
    )
    assert len(out["optimization_pipeline"]["shortlist"]) <= 1
