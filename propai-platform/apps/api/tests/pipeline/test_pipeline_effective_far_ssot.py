"""파이프라인 부지분석 실효 용적률 SSOT 단일화(WP-U1c) 회귀 테스트.

근본: project_pipeline._run_site_analysis가 과거 `min(법정,조례)`만 독자 재계산해
①구조상한(건폐율×층수) 계층을 누락 — 자연녹지(건폐 20%×4층=80% < 법정 100%)를 100%로
과대표시하고, ②무자료 시 `or 200`/`or 60` 날조 기본값으로 자연녹지에 200%를 발명했다
(라이브 실측: 조례조회 실패 시 200%, 조례 100% 시 100% — 정답 80%).

수정: far_tier_service.calc_effective_far(SSOT — 법정범위→조례→계획상한→인센티브→구조상한)
단일경유 소비 + far_basis/far_reliable/structural_cap_pct 정직 전파 + 무자료 시 None(미산정)
정직 전파(날조 금지). 수지·종합·규제(PR#333)·인허가(PR#334)·90초진단(PR#336)과 교차 일치.

★calc_effective_far는 재계산하지 않고 그대로 소비한다(SSOT 진실원천). 이 테스트는 외부 수집
(LandInfoService/OrdinanceService/LLM 해석)만 hermetic mock하고 calc_effective_far는 실물을
태워 '파이프라인 표면이 정말 SSOT 값(80%)을 소비하는지'를 검증한다.
"""

from typing import Any

import pytest

from app.services.pipeline.project_pipeline import (
    PipelineStage,
    PipelineState,
    ProjectPipeline,
    StageResult,
)


def _patch_externals(monkeypatch, *, ordinance: dict | None = None,
                     ordinance_raises: bool = False):
    """외부 수집·LLM만 hermetic mock(calc_effective_far는 실물 SSOT)."""
    import app.services.land_intelligence.land_info_service as land_info_module
    import app.services.land_intelligence.ordinance_service as ordinance_module

    async def _fake_comprehensive(self, address, pnu=None):  # noqa: ANN001
        return {}

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        if ordinance_raises:
            raise RuntimeError("조례 조회 실패(모의)")
        return ordinance if ordinance is not None else {}

    async def _noop_ai(self, state):  # noqa: ANN001 — LLM 해석은 본 회귀와 무관(네트워크 차단)
        return None

    monkeypatch.setattr(
        land_info_module.LandInfoService, "collect_comprehensive", _fake_comprehensive,
    )
    monkeypatch.setattr(
        ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance,
    )
    monkeypatch.setattr(ProjectPipeline, "_attach_site_ai", _noop_ai)


async def _run_site(site_data: dict[str, Any], opts_extra: dict[str, Any] | None = None):
    """_run_site_analysis만 직접 실행해 site stage 산출을 반환한다."""
    pipeline = ProjectPipeline()
    state = PipelineState(address=site_data.get("address") or "경기도 어딘가 산 12")
    state.project_id = ""  # DB 자동저장 경로 미진입(hermetic)
    state.stages["site_analysis"] = StageResult(stage=PipelineStage.SITE_ANALYSIS)
    opts: dict[str, Any] = {"site_data": dict(site_data)}
    if opts_extra:
        opts.update(opts_extra)
    await pipeline._run_site_analysis(state, opts)
    return state


_NATURAL_GREEN_SITE = {"zone_type": "자연녹지지역", "land_area_sqm": 1000.0}


# ── (a) 자연녹지 80% — 구조상한(건폐율×층수) 정직 산정 ──


async def test_natural_green_effective_far_is_80(monkeypatch):
    """자연녹지 실효 용적률 = 80%(구조상한). 100%/200% 과대표시 회귀 방지."""
    _patch_externals(monkeypatch)
    state = await _run_site(_NATURAL_GREEN_SITE)
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == 80.0, "자연녹지 실효 용적률은 구조상한 80%여야 한다"
    assert zoning["far_basis"] == "구조상한(건폐율×층수)"
    assert zoning["far_reliable"] is True
    assert zoning["structural_cap_pct"] == 80.0
    assert zoning["floor_cap"] == 4
    assert zoning["national_far"] == 100.0  # 법정상한(라벨 SSOT 재확인)은 정직 보존
    # 단계간 payload·하위호환 flat 키까지 동일값 전파(설계 GFA 산정 입력)
    assert state.site_to_design is not None
    assert state.site_to_design.max_far == 80.0
    assert state.stages["site_analysis"].data["max_far"] == 80.0


async def test_natural_green_ordinance_cannot_inflate_above_structural_cap(monkeypatch):
    """조례 100%가 실려와도 구조상한 80%가 최종 상한(과대낙관 차단)."""
    _patch_externals(
        monkeypatch,
        ordinance={"ordinance_bcr": 20, "ordinance_far": 100, "source": "조례"},
    )
    state = await _run_site(_NATURAL_GREEN_SITE)
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == 80.0
    assert zoning["far_basis"] == "구조상한(건폐율×층수)"


# ── (b) 비클램프 지역 무영향 ──


@pytest.mark.parametrize(
    "zone_type, expected_far",
    [("제2종일반주거지역", 250.0), ("일반상업지역", 1300.0)],
)
async def test_non_clamped_zones_unaffected(monkeypatch, zone_type, expected_far):
    """층수클램프 없는 지역은 무영향(안 낮아짐) — 구조상한 None."""
    _patch_externals(monkeypatch)
    state = await _run_site({"zone_type": zone_type, "land_area_sqm": 660.0})
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == expected_far
    assert zoning["structural_cap_pct"] is None
    assert zoning["floor_cap"] is None
    assert zoning["far_reliable"] is True


# ── (c) 무자료 시 날조 기본값(200/60) 미부활 ──


async def test_ordinance_failure_does_not_fabricate_200(monkeypatch):
    """조례조회 실패(과거 200% 날조 발화 조건)에도 SSOT 라벨 산정으로 80% 정직 산정."""
    _patch_externals(monkeypatch, ordinance_raises=True)
    state = await _run_site(_NATURAL_GREEN_SITE)
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == 80.0, "과거엔 이 조건에서 200%가 날조됐다(라이브 실측)"
    assert zoning["national_far"] == 100.0, "법정상한에 200%를 지어내면 안 된다"


async def test_zone_unmatched_propagates_none_not_200(monkeypatch):
    """용도지역 미매칭(개발제한구역 등)+무자료 → 미산정 None 정직 전파(임의 상한 발명 금지)."""
    _patch_externals(monkeypatch)
    state = await _run_site({"zone_type": "개발제한구역", "land_area_sqm": 1000.0})
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] is None
    assert zoning["national_far"] is None
    assert zoning["far_reliable"] is False
    assert zoning["far_basis"] == "zone_unmatched"
    # 인센티브 시뮬도 임의 200 기준으로 지어내지 않는다
    assert "skipped" in zoning["far_incentive"]
    # 단계간 payload는 0.0 센티널 — _run_design이 W3-8 계약(가정 표기)으로 소비
    assert state.site_to_design is not None
    assert state.site_to_design.max_far == 0.0


# ── (d) SSOT 실패 시 정직강등(far_reliable=False, 실측값만 보수 적용) ──


async def test_ssot_failure_honest_degrade(monkeypatch):
    """calc_effective_far 예외 시 임의값 없이 실제 수집값 min만 적용 + far_reliable=False."""
    _patch_externals(monkeypatch)
    import app.services.land_intelligence.far_tier_service as far_tier_module

    def _boom(base, zone_type, land_area=0):  # noqa: ANN001
        raise RuntimeError("SSOT 실패(모의)")

    monkeypatch.setattr(far_tier_module, "calc_effective_far", _boom)
    state = await _run_site(
        {"zone_type": "자연녹지지역", "land_area_sqm": 1000.0,
         "national_far": 100.0, "national_bcr": 20.0},
    )
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == 100.0  # 실측 법정값 보수 유지(200 날조 금지)
    assert zoning["far_reliable"] is False
    assert zoning["far_basis"] is None


async def test_ssot_failure_without_any_data_yields_none(monkeypatch):
    """SSOT 실패+실측값 전무 → None(미산정) — 어떤 임의 상한도 발명하지 않는다."""
    _patch_externals(monkeypatch)
    import app.services.land_intelligence.far_tier_service as far_tier_module

    def _boom(base, zone_type, land_area=0):  # noqa: ANN001
        raise RuntimeError("SSOT 실패(모의)")

    monkeypatch.setattr(far_tier_module, "calc_effective_far", _boom)
    state = await _run_site(_NATURAL_GREEN_SITE)
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] is None
    assert zoning["far_reliable"] is False


# ── 기존 계약 보존: 사용자 오버라이드 최종 권위·다필지 블렌드 대체 ──


async def test_user_override_remains_final_authority(monkeypatch):
    """stage_overrides.site_analysis.max_far 직접 입력은 SSOT 산정과 무관하게 최종 한도."""
    _patch_externals(monkeypatch)
    state = await _run_site(
        {"zone_type": "제2종일반주거지역", "land_area_sqm": 660.0},
        opts_extra={"stage_overrides": {"site_analysis": {"max_far": 120}}},
    )
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == 120.0
    assert zoning["far_basis"] == "사용자 오버라이드(직접 입력)"


async def test_multiparcel_blend_still_overrides(monkeypatch):
    """다필지 통합(area_basis=integrated_parcels) 시 면적가중 블렌드 실효율이 최종(기존 계약)."""
    _patch_externals(monkeypatch)
    import app.services.land_intelligence.comprehensive_analysis_service as cas_module

    async def _fake_integrated(parcels):  # noqa: ANN001
        return {
            "total_area_sqm": 2000.0,
            "land_area_effective_sqm": 1800.0,
            "dominant_zone": "자연녹지지역",
            "blended_far_eff_pct": 95.5,
            "blended_bcr_eff_pct": 20.0,
            "parcel_count": 2,
        }

    monkeypatch.setattr(cas_module, "build_integrated_context", _fake_integrated)
    state = await _run_site(
        _NATURAL_GREEN_SITE,
        opts_extra={"parcels": [{"pnu": "1"}, {"pnu": "2"}]},
    )
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == 95.5
    assert zoning["far_basis"] == "다필지 통합(면적가중 실효율)"
    assert zoning["far_reliable"] is True
