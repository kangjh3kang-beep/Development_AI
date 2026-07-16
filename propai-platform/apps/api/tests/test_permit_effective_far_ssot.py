"""인허가분석엔진 실효 용적률 SSOT 단일화(WP-U1) 회귀 테스트.

근본: permit_analysis_service._enrich_site(AutoZoning 경로)가 과거 `min(법정,조례)`만 하고
구조상한(건폐율×층수)을 누락해 자연/생산녹지를 100%로 과대표시, 인허가 가능성을 과대낙관했다.
수정: 실효 용적률을 far_tier_service.calc_effective_far(SSOT) 단일경유로 전환 —
자연녹지 20%×4층=80% 정직 산정(수지·종합·규제 표면과 교차 일치).

★calc_effective_far는 재계산하지 않고 그대로 소비한다(SSOT 진실원천). 따라서 이 테스트는
AutoZoningService/OrdinanceService만 hermetic mock하고 calc_effective_far는 실물을 태워
'인허가 표면이 정말 SSOT 값(80%)을 소비하는지'를 검증한다.
"""

import pytest

from app.services.permit.permit_analysis_service import PermitAnalysisService


def _patch_zone(monkeypatch, *, zone_type: str, zone_limits: dict, land_area: float = 1000.0,
                ordinance: dict | None = None):
    """AutoZoningService·OrdinanceService만 hermetic mock(calc_effective_far는 실물 SSOT)."""
    import app.services.land_intelligence.ordinance_service as ordinance_module
    import app.services.zoning.auto_zoning_service as auto_zoning_module

    async def _fake_analyze(self, address):
        return {
            "zone_type": zone_type,
            "zone_limits": zone_limits,
            "land_area_sqm": land_area,
            "land_category": None,
            "special_districts": [],
        }

    async def _fake_ordinance(self, address, zone_type_arg, force_refresh=False):
        return ordinance if ordinance is not None else {}

    monkeypatch.setattr(auto_zoning_module.AutoZoningService, "analyze_by_address", _fake_analyze)
    monkeypatch.setattr(ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance)


# 법정 zone_limits 페이로드(auto_zoning build_zone_limits shape).
_NATURAL_GREEN = {"max_bcr_pct": 20, "max_far_pct": 100}   # 자연녹지: 건폐20×4층=80% 구조상한
_R2 = {"max_bcr_pct": 60, "max_far_pct": 250}              # 제2종일반주거: 층수제한 없음
_COMMERCIAL = {"max_bcr_pct": 80, "max_far_pct": 1300}     # 일반상업: 층수제한 없음


@pytest.mark.asyncio
async def test_natural_green_zone_effective_far_is_80(monkeypatch):
    """자연녹지 인허가분석 실효 용적률 = 80%(구조상한). 100% 과대표시 회귀 방지."""
    _patch_zone(monkeypatch, zone_type="자연녹지지역", zone_limits=_NATURAL_GREEN)
    site = await PermitAnalysisService()._enrich_site("경기 어딘가 산 12", {})
    assert site["max_far"] == 80.0, "자연녹지 실효 용적률은 구조상한 80%여야 한다(100% 과대 금지)"
    assert site["far_basis"] == "구조상한(건폐율×층수)"
    assert site["structural_cap_pct"] == 80.0
    assert site["floor_cap"] == 4
    assert site["far_reliable"] is True
    assert site["legal_max_far"] == 100  # 법정범위 상한은 정직 보존


@pytest.mark.asyncio
async def test_natural_green_zone_ordinance_cannot_inflate_above_structural_cap(monkeypatch):
    """조례 effective_far=100이 실려와도 구조상한 80%가 최종 상한(과대낙관 차단)."""
    _patch_zone(
        monkeypatch, zone_type="자연녹지지역", zone_limits=_NATURAL_GREEN,
        ordinance={"effective_far": 100, "effective_bcr": 20, "source": "법정상한"},
    )
    site = await PermitAnalysisService()._enrich_site("경기 어딘가 산 12", {})
    assert site["max_far"] == 80.0
    assert site["far_basis"] == "구조상한(건폐율×층수)"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "zone_type, zl, expected_far",
    [("제2종일반주거지역", _R2, 250.0), ("일반상업지역", _COMMERCIAL, 1300.0)],
)
async def test_non_clamped_zones_unaffected(monkeypatch, zone_type, zl, expected_far):
    """층수클램프 없는 지역은 무영향(안 낮아짐) — 구조상한 None."""
    _patch_zone(monkeypatch, zone_type=zone_type, zone_limits=zl)
    site = await PermitAnalysisService()._enrich_site("서울 어딘가 1-1", {})
    assert site["max_far"] == expected_far, f"{zone_type} 실효 용적률은 {expected_far}%로 유지돼야 한다"
    assert site["structural_cap_pct"] is None
    assert site["floor_cap"] is None
    assert site["far_basis"] == "법정/조례"


@pytest.mark.asyncio
async def test_provided_site_is_consumed_not_recomputed(monkeypatch):
    """SSOT 소비처(설계엔진 등)가 실효 용적률을 이미 주입한 site는 재계산하지 않고 소비."""
    # AutoZoning이 호출되면 실패시켜 '재계산 경로 미진입'을 강제 검증.
    import app.services.zoning.auto_zoning_service as auto_zoning_module

    async def _boom(self, address):  # noqa: ANN001
        raise AssertionError("provided site는 AutoZoning 재계산을 타면 안 된다")

    monkeypatch.setattr(auto_zoning_module.AutoZoningService, "analyze_by_address", _boom)
    provided = {"zone_type": "자연녹지지역", "max_far": 82.0, "max_bcr": 20, "land_area_sqm": 500}
    site = await PermitAnalysisService()._enrich_site("경기 어딘가 산 12", provided)
    assert site["max_far"] == 82.0  # 주입값 그대로 소비(구조상한 재계산 안 함)


@pytest.mark.asyncio
async def test_analyze_propagates_far_basis_to_result_site(monkeypatch):
    """analyze(use_llm=False) 결과 site에 실효 용적률(80%)·far_basis가 정직 전파된다."""
    _patch_zone(monkeypatch, zone_type="자연녹지지역", zone_limits=_NATURAL_GREEN)
    res = await PermitAnalysisService().analyze(
        "경기 어딘가 산 12", use_llm=False, with_senior=False,
    )
    assert res["site"]["max_far"] == 80.0
    assert res["site"]["far_basis"] == "구조상한(건폐율×층수)"
    assert res["site"]["structural_cap_pct"] == 80.0


@pytest.mark.asyncio
async def test_cross_surface_parity_with_calc_effective_far(monkeypatch):
    """인허가 실효 용적률 = 수지·종합이 쓰는 calc_effective_far(SSOT) 산출값과 동일(교차 일치)."""
    from app.services.land_intelligence.far_tier_service import calc_effective_far

    _patch_zone(monkeypatch, zone_type="자연녹지지역", zone_limits=_NATURAL_GREEN)
    site = await PermitAnalysisService()._enrich_site("경기 어딘가 산 12", {})

    ssot = calc_effective_far(
        {"zone_limits": _NATURAL_GREEN, "special_districts": [], "local_ordinance": {}},
        "자연녹지지역", 1000.0,
    )
    # 인허가 표면이 소비한 실효 용적률이 SSOT 진실원천과 정확히 일치해야 한다(발산 0).
    assert site["max_far"] == ssot["effective_far_pct"] == 80.0
    assert site["far_basis"] == ssot["far_basis"]
