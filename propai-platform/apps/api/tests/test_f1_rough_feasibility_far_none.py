"""F1 2차 싱크: rough_feasibility_orchestrator.py effective_far=None 무크래시 회귀 테스트.

comprehensive_analysis_service의 P0-1 무날조 정직 반환(용도 미확인 → effective_far_pct=None)이
build_rough_scenario까지 전파될 수 있다(build_integrated_context.blended_far_eff_pct 또는
auto_recommend_top3의 effective_far_pct가 None인 경우). 이 파일의 GFA 산정부(:411
`land_area * effective_far / 100`)는 이미 `if land_area and effective_far:` 가드로
None을 방어하고 있어 크래시가 나지 않는다 — 이 테스트는 그 기존 관례가 계속 유지되는지
(GFA 미산정 + degraded_notes 명시, 임의 폴백 없음) 고정한다.
"""
from __future__ import annotations

import pytest

from app.services.feasibility import rough_feasibility_orchestrator as orch
from app.services.feasibility.modules.base_module import ModuleInput


def _module_input_placeholder(dev: str, land_area: float, official: float) -> ModuleInput:
    """엔진(비용비율 등) 소비용 최소 스텁 — build_rough_scenario의 GFA/degraded 판단(:407-414)과는
    별개 경로(chosen.input_used)라 far=None 전파와 무관한 placeholder 값을 채운다."""
    gfa = land_area * 200.0 / 100.0
    return ModuleInput(
        development_type=dev,
        total_land_area_sqm=land_area,
        official_price_per_sqm=official,
        price_multiplier=1.1,
        total_gfa_sqm=gfa,
        total_households=max(1, int(gfa / 84)),
        avg_sale_price_per_pyeong=15_000_000,
        avg_area_pyeong=34.0,
        sale_ratio=0.95,
        equity_won=10_000_000_000,
    )


def _fake_reco_far_none(*, land_area: float = 1000.0, dev: str = "M06",
                        official: float = 3_000_000) -> dict:
    """auto_recommend_top3가 실효 용적률을 산출하지 못한 경우(P0-1 zone_unmatched 전파)를 흉내."""
    rec = {
        "development_type": dev,
        "type_name": "일반분양",
        "feasibility": {"total_cost_won": 1, "total_revenue_won": 1, "net_profit_won": 0},
        "unit_summary": {"total_gfa_sqm": 0.0, "total_households": 0, "avg_area_pyeong": 34.0},
        "input_used": _module_input_placeholder(dev, land_area, official),
        "composite_score": 80.0,
    }
    return {
        "address": "개발제한구역-QA재현",
        "zone_type": "개발제한구역",
        "land_area_sqm": land_area,
        "effective_far_pct": None,  # ★핵심: P0-1 무날조 None 반환 재현
        "recommendations": [rec],
        "all_results": [rec],
        "land_price_reliable": True,
        "area_reliable": True,
        "scenario_status": "actual",
    }


def _stub_far_none(monkeypatch, *, land_area: float = 1000.0):
    async def _fake_integrated(parcels):
        return None  # 다필지 미제공(단일 경로) — integrated.blended_far_eff_pct 개입 없음

    async def _fake_auto(**kwargs):
        return _fake_reco_far_none(land_area=land_area)

    async def _fake_desk(**kwargs):
        return {"ok": True, "appraised_price_per_sqm": 5_000_000,
                "appraised_total_won": int(5_000_000 * (kwargs.get("area_sqm") or 0)),
                "evidence": {"evidence": [{"label": "채택 단가"}]},
                "source": "NED 토지특성", "confidence": 0.8}

    async def _fake_price(*, db, site_id, dev_type, region, address):
        return 40_000_000, "지역 시세 테이블(sigungu)", "지역×유형 시장표준 시세", None

    def _fake_ratios(input_used):
        return 0.08, 0.04, None

    monkeypatch.setattr(orch, "build_integrated_context", _fake_integrated)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)
    monkeypatch.setattr(orch, "desk_appraisal", _fake_desk)
    monkeypatch.setattr(orch, "_resolve_sale_price_per_pyeong", _fake_price)
    monkeypatch.setattr(orch, "_engine_cost_ratios", _fake_ratios)


@pytest.mark.asyncio
async def test_effective_far_none_no_crash_gfa_not_computed_and_degraded(monkeypatch):
    _stub_far_none(monkeypatch, land_area=1000.0)

    # 크래시 없이 완주해야 한다(예외 시 pytest가 즉시 실패로 잡는다).
    out = await orch.build_rough_scenario(address="개발제한구역-QA재현")

    assert out["inputs"]["effective_far_pct"] is None
    # GFA는 임의 폴백 없이 미산정(None)이어야 한다(:411 land_area*effective_far/100 도달 안 함).
    assert out["inputs"]["gfa_sqm"] is None
    assert any(
        "면적" in n and "실효용적률" in n for n in out["degraded_notes"]
    ), f"GFA 미산정 사유가 degraded_notes에 없음: {out['degraded_notes']}"
