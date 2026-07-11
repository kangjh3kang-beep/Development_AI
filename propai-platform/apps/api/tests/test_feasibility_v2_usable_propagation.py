"""★A-2(배선 P1 — usable 면적 전파) feasibility_service_v2.auto_recommend_top3 회귀 테스트.

다필지 통합 경로(백엔드가 build_integrated_context에서 스스로 면적을 채우는 경로만 —
스칼라 land_area_sqm을 사용자가 명시하면 이 분기 자체가 스킵되어 무영향)에서:
  - GFA/개발규모(land_area_sqm, 각 후보의 input_used.total_gfa_sqm)는 usable
    (land_area_effective_sqm) 채택.
  - 토지비(input_used.total_land_area_sqm, build_module_input 경유)는 gross
    (total_area_sqm) 채택.
comprehensive_analysis_service의 F2/P0-2(c) 이원화 원칙과 동일 SSOT(build_integrated_context)
를 채택만 한다(산식복제 0). rough_feasibility_orchestrator A-2(a)와 병행 소비처.

네트워크(AutoZoningService·OrdinanceService)는 monkeypatch로 대역해 결정론 검증한다
(무네트워크·무행 — 표적 테스트 요건).
"""
from __future__ import annotations

import pytest

from app.services.feasibility import feasibility_service_v2 as fv2
from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.land_intelligence import comprehensive_analysis_service as comp_module
from app.services.land_intelligence import far_tier_service as far_tier_module
from app.services.land_intelligence import ordinance_service as ordinance_module
from app.services.zoning import auto_zoning_service as auto_zoning_module

pytestmark = pytest.mark.asyncio


def _zoning_result() -> dict:
    return {
        "zone_type": "제2종일반주거지역",
        "zone_limits": {"max_bcr_pct": 60, "max_far_pct": 250},
        "land_area_sqm": None,
        "official_price_per_sqm": 3_000_000,
        "special_districts": [],
        "land_category": "대",
    }


@pytest.fixture(autouse=True)
def _stub_network(monkeypatch):
    """AutoZoningService·OrdinanceService·calc_effective_far — 라이브 네트워크 완전 차단.

    calc_effective_far는 순수함수이나 ordinance 인자에 따라 값이 달라져 fixture간
    수치가 흔들릴 수 있어, 고정치(200.0%)로 대역해 GFA 기대값을 결정론으로 계산한다.
    """

    async def _fake_analyze(self, address):
        return _zoning_result()

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):
        return {}

    def _fake_calc_effective_far(base, zone_type, land_area):
        return {"effective_far_pct": 200.0, "effective_bcr_pct": 50.0, "far_basis": "테스트고정"}

    monkeypatch.setattr(auto_zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance)
    monkeypatch.setattr(far_tier_module, "calc_effective_far", _fake_calc_effective_far)


async def test_multiparcel_usable_for_gfa_gross_for_land_cost(monkeypatch):
    """도로 지목 혼입 다필지: gross=2000㎡(대 1600+도로 400), usable=1600㎡(도로 제외).

    land_area_sqm(GFA 산정 기준) = usable(1600) 채택, 각 후보 input_used.total_land_area_sqm
    (토지비 산정 기준, ModuleInput)은 gross(2000) 채택.
    """
    integrated = {
        "total_area_sqm": 2000.0, "land_area_effective_sqm": 1600.0,
        "dominant_zone": "제2종일반주거지역", "parcel_count": 2,
    }

    async def _fake_integrated(parcels):
        return integrated

    monkeypatch.setattr(comp_module, "build_integrated_context", _fake_integrated)

    svc = FeasibilityServiceV2()
    out = await svc.auto_recommend_top3(
        address="서울특별시 강남구 역삼동 736",
        parcels=[{"area_sqm": 1600, "land_category": "대"}, {"area_sqm": 400, "land_category": "도로"}],
        use_llm=False,
    )

    # GFA/개발규모(land_area_sqm) = usable(1600) 채택.
    assert out["land_area_sqm"] == 1600.0
    assert out["zone_basis"] == "integrated_dominant"

    # 이원화 근거 additive 노출(양 면적 병기).
    basis = out["land_area_basis"]
    assert basis is not None
    assert basis["gross_sqm"] == 2000.0
    assert basis["usable_sqm"] == 1600.0
    assert basis["gfa_sqm_basis"] == "usable"
    assert basis["land_cost_basis"] == "gross"

    assert out["all_results"], "후보가 산출되어야 함(제2종일반주거지역은 허용유형 다수)"
    for r in out["all_results"]:
        inp = r["input_used"]
        dev_type = r["development_type"]
        # 토지비 산정 기준(ModuleInput.total_land_area_sqm) = gross(2000) — usable(1600) 아님.
        assert inp.total_land_area_sqm == 2000.0
        # GFA는 usable(1600) × 유형별 클램프 실효FAR(고정 200.0%와 유형 typical 중 작은 값).
        expected_far = min(200.0, svc._get_type_typical_far(dev_type))
        assert inp.total_gfa_sqm == pytest.approx(1600.0 * expected_far / 100)


async def test_scalar_land_area_sqm_bypasses_dual_basis(monkeypatch):
    """사용자가 land_area_sqm(스칼라)을 명시하면 통합 이원화 분기 자체가 스킵된다(사용자 입력 존중).

    이 경우 land_area_basis는 None(다필지 자동보강이 발동하지 않았다는 정직 신호)이고,
    GFA/토지비 모두 사용자 지정 스칼라 그대로 사용된다(기존 정답 경로 무회귀).
    """
    integrated = {
        "total_area_sqm": 2000.0, "land_area_effective_sqm": 1600.0,
        "dominant_zone": "제2종일반주거지역", "parcel_count": 2,
    }

    async def _fake_integrated(parcels):
        return integrated

    monkeypatch.setattr(comp_module, "build_integrated_context", _fake_integrated)

    svc = FeasibilityServiceV2()
    out = await svc.auto_recommend_top3(
        address="서울특별시 강남구 역삼동 736",
        land_area_sqm=900.0,
        parcels=[{"area_sqm": 1600, "land_category": "대"}, {"area_sqm": 400, "land_category": "도로"}],
        use_llm=False,
    )

    assert out["land_area_sqm"] == 900.0
    assert out["land_area_basis"] is None
    for r in out["all_results"]:
        assert r["input_used"].total_land_area_sqm == 900.0
