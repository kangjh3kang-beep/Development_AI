"""★A-2(배선 P1 — usable 면적 전파) project_pipeline 회귀 테스트.

site 단계(_run_site_analysis)가 다필지 통합 경로(build_integrated_context)에서 면적을
스스로 채우는 지점에서 GFA/개발규모(land_area_sqm)는 usable(land_area_effective_sqm),
토지비(land_area_gross_sqm, 신설 additive 필드)는 gross(total_area_sqm)로 이원화하고,
feasibility 단계(_run_feasibility)가 그 gross 필드를 토지비 산정에 채택하는지 검증한다.
comprehensive_analysis_service F2/P0-2(c)·rough_feasibility_orchestrator A-2(a)·
feasibility_service_v2 A-2(b)와 동일 이원화 원칙(build_integrated_context 출력 채택만,
산식복제 0). 외부 네트워크(LandInfoService)는 monkeypatch로 대역한다(무네트워크·무행).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.services.land_intelligence import comprehensive_analysis_service as comp_module  # noqa: E402
from app.services.land_intelligence.land_info_service import LandInfoService  # noqa: E402
from app.services.pipeline.project_pipeline import (  # noqa: E402
    PipelineStage,
    PipelineState,
    PipelineStatus,
    ProjectPipeline,
    SiteToDesignPayload,
    StageResult,
)

pytestmark = pytest.mark.asyncio


async def _fake_collect_comprehensive(self, address):
    """LandInfoService.collect_comprehensive 대역 — 라이브 네트워크(VWorld/MOLIT 등) 차단."""
    return {}


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch):
    monkeypatch.setattr(LandInfoService, "collect_comprehensive", _fake_collect_comprehensive)


def _fresh_state(project_id: str) -> PipelineState:
    state = PipelineState(
        project_id=project_id, address="서울특별시 강남구 역삼동 736", status=PipelineStatus.RUNNING,
    )
    for stage in PipelineStage:
        state.stages[stage.value] = StageResult(stage=stage)
    return state


async def test_site_stage_usable_for_gfa_gross_for_land_cost(monkeypatch):
    """도로 지목 혼입 다필지: gross=2000㎡(대 1600+도로 400), usable=1600㎡(도로 제외).

    site_to_design.land_area_sqm(GFA 기준) = usable(1600), land_area_gross_sqm(토지비 기준) =
    gross(2000). 단계 결과(site_analysis.data)에 land_area_basis 명세가 additive로 붙는다.
    """
    integrated = {
        "total_area_sqm": 2000.0, "land_area_effective_sqm": 1600.0,
        "dominant_zone": "제2종일반주거지역", "parcel_count": 2,
        "blended_far_eff_pct": 200.0, "blended_bcr_eff_pct": 50.0,
    }

    async def _fake_integrated(parcels):
        return integrated

    monkeypatch.setattr(comp_module, "build_integrated_context", _fake_integrated)

    pipeline = ProjectPipeline()
    state = _fresh_state("t-a2-site")
    opts = {
        "site_data": {
            "zone_type": "제2종일반주거지역",
            # 조례 실조회(OrdinanceService) 스킵 — 결정론·무네트워크.
            "ordinance_bcr": 50.0, "ordinance_far": 200.0,
            "official_land_price": 3_000_000.0,
        },
        "parcels": [
            {"area_sqm": 1600, "land_category": "대"},
            {"area_sqm": 400, "land_category": "도로"},
        ],
    }

    await pipeline._run_site_analysis(state, opts)

    site = state.site_to_design
    assert site is not None
    assert site.land_area_sqm == 1600.0          # usable 채택(GFA/개발규모)
    assert site.land_area_gross_sqm == 2000.0    # gross 유지(토지비)

    basis = state.stages["site_analysis"].data.get("land_area_basis")
    assert basis == {
        "gfa_sqm_basis": "usable", "land_cost_basis": "gross",
        "gross_sqm": 2000.0, "usable_sqm": 1600.0,
    }


async def test_site_stage_single_parcel_no_dual_basis(monkeypatch):
    """단일/미통합(parcels<2) 경로는 land_area_gross_sqm=None, land_area_basis=None(무회귀)."""
    pipeline = ProjectPipeline()
    state = _fresh_state("t-a2-single")
    opts = {
        "site_data": {
            "zone_type": "제2종일반주거지역",
            "ordinance_bcr": 50.0, "ordinance_far": 200.0,
            "land_area_sqm": 900.0,
            "official_land_price": 3_000_000.0,
        },
    }

    await pipeline._run_site_analysis(state, opts)

    site = state.site_to_design
    assert site is not None
    assert site.land_area_sqm == 900.0
    assert site.land_area_gross_sqm is None
    assert state.stages["site_analysis"].data.get("land_area_basis") is None


async def test_feasibility_stage_land_cost_uses_gross(monkeypatch):
    """feasibility 단계 — 토지비는 site.land_area_gross_sqm(gross) 채택, usable(land_area_sqm) 아님."""
    pipeline = ProjectPipeline()
    state = _fresh_state("t-a2-feas")
    state.site_to_design = SiteToDesignPayload(
        address="서울특별시 강남구 역삼동 736",
        zone_type="제2종일반주거지역",
        land_area_sqm=1600.0, land_area_gross_sqm=2000.0,
        official_land_price=3_000_000.0,
    )

    await pipeline._run_feasibility(state, {})

    fdata = state.stages["feasibility"].data
    assert isinstance(fdata, dict) and fdata, "feasibility 단계 산출 실패(빈 data)"
    # 토지비 = gross(2000) × 공시지가(3,000,000) × 1.3 — usable(1600) 기준이면 다른 값이 나온다.
    expected_gross_cost = 2000.0 * 3_000_000.0 * 1.3
    expected_usable_cost = 1600.0 * 3_000_000.0 * 1.3
    assert fdata["land_cost"] == pytest.approx(expected_gross_cost)
    assert fdata["land_cost"] != pytest.approx(expected_usable_cost)


async def test_feasibility_stage_land_cost_falls_back_when_gross_absent(monkeypatch):
    """land_area_gross_sqm 미설정(단일/미통합)이면 기존 동작대로 land_area_sqm 그대로 사용(무회귀)."""
    pipeline = ProjectPipeline()
    state = _fresh_state("t-a2-feas-fallback")
    state.site_to_design = SiteToDesignPayload(
        address="서울특별시 강남구 역삼동 736",
        zone_type="제2종일반주거지역",
        land_area_sqm=900.0, land_area_gross_sqm=None,
        official_land_price=3_000_000.0,
    )

    await pipeline._run_feasibility(state, {})

    fdata = state.stages["feasibility"].data
    assert fdata["land_cost"] == pytest.approx(900.0 * 3_000_000.0 * 1.3)
