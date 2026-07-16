"""실효FAR 위생 라운드(WP-U1d) 회귀 테스트 — 날조 기본값 제거·far_reliable 시맨틱 통일·그림자표 가드.

실효FAR SSOT 캠페인(PR#333/#334/#336/#337/#339/#341) 잔여 위생 4건+가드 1건:

① far_incentive_calculator: zone 미매칭 시 `NATIONAL_FAR_LIMITS.get(zone_type, 250.0)`이
   250%를 발명(실측: 개발제한구역 → max_far 250 / base 300 → allowed 250 자기모순 왜곡).
   → 미산정(skipped) 정직 반환.
② development_type_analyzer: ZONE_LIMITS 미매칭 시 `or 200.0`/`or 60.0`으로 법정값을 발명해
   max_gfa까지 날조(실측: 개발제한구역 1000㎡ → 최대 연면적 2000㎡ 발명). → None(미산정).
③ project_pipeline: E7 폴백(assumed_defaults)이 zone/max_far를 발명하면 SSOT가 가정 zone
   라벨로 250%를 실측처럼 산정해 far_reliable=True 모순(#337 리뷰 MEDIUM — 실측 재현).
   → 값 유지 + far_reliable=False 강등 + far_basis 가정 표기.
④ persona runner._ssot_effective_limits: 양수 far면 무조건 far_reliable=True(#339 리뷰
   MEDIUM). → 법정폴백(far_basis "법정/조례" 류·조례 미확인)이면 False — 프론트 계약
   (node-body-builders.ts design 노드: basis=national이면 false)과 시맨틱 통일.
⑤ NATIONAL_FAR_LIMITS(far_incentive_calculator 그림자표) ↔ ZONE_LIMITS(auto_zoning SSOT)
   parity 가드 — 어느 한쪽만 갱신되는 침묵 드리프트를 CI가 즉시 잡는다.
"""

from typing import Any

from app.services.pipeline.project_pipeline import (
    PipelineStage,
    PipelineState,
    ProjectPipeline,
    StageResult,
)

# ──────────────────────────────────────────────────────────────────────────
# ① far_incentive_calculator — zone 미매칭 시 미산정(무날조)
# ──────────────────────────────────────────────────────────────────────────


def test_incentive_zone_unmatched_returns_skipped_not_250():
    """zone 미매칭+법정상한 미전달 → 250% 발명 대신 skipped 정직 반환."""
    from app.services.zoning.far_incentive_calculator import calculate

    out = calculate("개발제한구역", ordinance_far=100.0, donation_ratio_pct=10.0)
    assert "skipped" in out, "미매칭 zone에 임의 상한 시뮬을 만들면 안 된다"
    assert out["simulation_table"] == []
    assert "max_far" not in out  # 250 날조값 미노출
    assert "allowed_far" not in out


def test_incentive_zone_unmatched_no_self_contradiction_cap():
    """과거 왜곡 재발 방지: base 300 > 날조 cap 250 → allowed 250으로 깎이던 자기모순 제거."""
    from app.services.zoning.far_incentive_calculator import calculate

    out = calculate("용도지역미상", ordinance_far=300.0, donation_ratio_pct=15.0)
    assert "skipped" in out
    assert out.get("allowed_far") is None


def test_incentive_matched_zone_unchanged():
    """정상 매칭 zone은 기존 산식 그대로(무회귀)."""
    from app.services.zoning.far_incentive_calculator import calculate

    out = calculate("제2종일반주거지역", ordinance_far=200.0, donation_ratio_pct=10.0)
    assert out["max_far"] == 250.0  # NATIONAL_FAR_LIMITS 매칭
    # 인센티브 = 200 × 0.10 × 1.5(주거 alpha) = 30 → allowed 230
    assert out["allowed_far"] == 230.0
    assert len(out["simulation_table"]) == 7


def test_incentive_explicit_national_far_still_calculates():
    """호출자가 법정상한을 명시 전달하면 zone 미매칭이어도 산정(far_tier 경로 무회귀)."""
    from app.services.zoning.far_incentive_calculator import calculate

    out = calculate("개발제한구역", ordinance_far=80.0, donation_ratio_pct=0.0,
                    national_far=100.0)
    assert "skipped" not in out
    assert out["max_far"] == 100.0


# ──────────────────────────────────────────────────────────────────────────
# ② development_type_analyzer — ZONE_LIMITS 미매칭 시 None(미산정)
# ──────────────────────────────────────────────────────────────────────────


def test_dev_type_zone_unmatched_returns_none_not_200_60():
    """미매칭 zone(개발제한구역) → 200/60·max_gfa 발명 금지(None 정직)."""
    from app.services.zoning.development_type_analyzer import analyze

    out = analyze("개발제한구역", 1000.0)
    assert out["max_far_pct"] is None, "과거엔 200.0이 날조됐다(실측)"
    assert out["max_bcr_pct"] is None, "과거엔 60.0이 날조됐다(실측)"
    assert out["max_gfa_sqm"] is None, "과거엔 2000㎡가 날조됐다(실측)"
    assert out["max_gfa_legal_sqm"] is None
    assert out["max_far_legal_pct"] is None
    for t in out["allowed_types"]:
        assert t["max_gfa_sqm"] is None


def test_dev_type_effective_far_still_computes_on_unmatched_zone():
    """실효값이 전달되면(SSOT 산정 성공) 미매칭 zone이어도 실효 기준 GFA는 산출."""
    from app.services.zoning.development_type_analyzer import analyze

    out = analyze("개발제한구역", 1000.0, effective_far_pct=80.0, effective_bcr_pct=20.0)
    assert out["max_far_pct"] == 80.0
    assert out["max_gfa_sqm"] == 800.0
    assert out["max_gfa_legal_sqm"] is None  # 법정은 여전히 미확인(정직 분리)
    assert out["is_effective_applied"] is True


def test_dev_type_matched_zone_unchanged():
    """정상 매칭 zone은 기존 산출 그대로(무회귀)."""
    from app.services.zoning.development_type_analyzer import analyze

    out = analyze("제2종일반주거지역", 660.0)
    assert out["max_far_pct"] == 250
    assert out["max_bcr_pct"] == 60
    assert out["max_gfa_sqm"] == 1650.0
    assert out["max_gfa_legal_sqm"] == 1650.0


# ──────────────────────────────────────────────────────────────────────────
# ③ project_pipeline — E7 assumed_defaults 시 far_reliable=False 강제(#337 MEDIUM)
#    hermetic 패턴은 tests/pipeline/test_pipeline_effective_far_ssot.py와 동일
#    (외부 수집·LLM만 mock, calc_effective_far는 실물 SSOT).
# ──────────────────────────────────────────────────────────────────────────


def _patch_pipeline_externals(monkeypatch):
    import app.services.land_intelligence.land_info_service as land_info_module
    import app.services.land_intelligence.ordinance_service as ordinance_module

    async def _fake_comprehensive(self, address, pnu=None):  # noqa: ANN001
        return {}

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}

    async def _noop_ai(self, state):  # noqa: ANN001
        return None

    monkeypatch.setattr(
        land_info_module.LandInfoService, "collect_comprehensive", _fake_comprehensive,
    )
    monkeypatch.setattr(
        ordinance_module.OrdinanceService, "get_ordinance_limits", _fake_ordinance,
    )
    monkeypatch.setattr(ProjectPipeline, "_attach_site_ai", _noop_ai)


_E7_ASSUMED_RESULT: dict[str, Any] = {
    # _fetch_real_site_data E7 폴백이 외부수집 전면 실패 시 발명하는 형상(project_pipeline
    # 1133~1155 계약과 동일) — zone/면적/한도 전부 가정치.
    "zone_type": "제2종일반주거지역",
    "land_area_sqm": 500.0,
    "max_bcr": 60.0,
    "max_far": 250.0,
    "assumed_fields": ["zone_type", "land_area_sqm", "max_bcr", "max_far"],
    "data_quality": "assumed_defaults",
    "warnings": ["외부 데이터 미확보로 기본 가정값을 적용했습니다"],
}


async def _run_site_case_b(monkeypatch, opts_extra: dict[str, Any] | None = None):
    """site_data 없이(Case B) E7 가정치 형상을 주입해 _run_site_analysis를 구동."""
    _patch_pipeline_externals(monkeypatch)
    pipeline = ProjectPipeline()

    async def _fake_fetch(address, pre_collected=None):  # noqa: ANN001
        return dict(_E7_ASSUMED_RESULT)

    pipeline._fetch_real_site_data = _fake_fetch
    state = PipelineState(address="외부수집 전면실패 모의 주소")
    state.project_id = ""  # DB 자동저장 경로 미진입(hermetic)
    state.stages["site_analysis"] = StageResult(stage=PipelineStage.SITE_ANALYSIS)
    opts: dict[str, Any] = {}
    if opts_extra:
        opts.update(opts_extra)
    await pipeline._run_site_analysis(state, opts)
    return state


async def test_e7_assumed_defaults_forces_far_reliable_false(monkeypatch):
    """E7 가정치(max_far=250 발명) 경로 → far_reliable=False 강제+가정 표기(#337 MEDIUM).

    수정 전 실측: effective_far=250.0 / far_basis='법정/조례' / far_reliable=True(모순).
    """
    state = await _run_site_case_b(monkeypatch)
    data = state.stages["site_analysis"].data
    zoning = data["zoning"]
    assert data["data_quality"] == "assumed_defaults"
    assert "max_far" in data["assumed_fields"]
    # 값은 유지(파이프라인 무중단·W3-8 계약) — 신뢰 표기만 정직 강등.
    assert zoning["effective_far"] == 250.0
    assert zoning["far_reliable"] is False, "가정 zone 라벨 기반 SSOT 산정을 실측으로 오인하면 안 된다"
    assert "가정 기본값" in (zoning["far_basis"] or "")


async def test_e7_assumed_user_override_recovers_reliability(monkeypatch):
    """E7 가정 경로여도 사용자 max_far 직접 입력은 최종 권위(True 회복 — 기존 계약 보존)."""
    state = await _run_site_case_b(
        monkeypatch,
        opts_extra={"stage_overrides": {"site_analysis": {"max_far": 120}}},
    )
    zoning = state.stages["site_analysis"].data["zoning"]
    assert zoning["effective_far"] == 120.0
    assert zoning["far_basis"] == "사용자 오버라이드(직접 입력)"
    assert zoning["far_reliable"] is True


# ──────────────────────────────────────────────────────────────────────────
# ④ persona runner — 법정폴백이면 far_reliable=False(#339 MEDIUM·프론트 계약 통일)
# ──────────────────────────────────────────────────────────────────────────


def test_persona_ssot_legal_fallback_not_reliable():
    """조례 미확인·법정상한만으로 산정(far_basis '법정/조례') → far_reliable=False.

    수정 전 실측: {'far': 250.0, 'far_basis': '법정/조례', 'far_reliable': True}(모순).
    프론트 node-body-builders design 노드는 basis=national(법정폴백)이면 false — 시맨틱 통일.
    """
    from app.services.persona.runner import _ssot_effective_limits

    out = _ssot_effective_limits("제2종일반주거지역", 1000.0)
    assert out is not None
    assert out["far"] == 250.0  # 값은 불변(표기 시맨틱만 교정)
    assert out["far_basis"] == "법정/조례"
    assert out["far_reliable"] is False


def test_persona_ssot_structural_cap_stays_reliable():
    """구조상한(건폐율×층수) 등 계층 확정 산정은 기존대로 True(PR#334 계약·무회귀)."""
    from app.services.persona.runner import _ssot_effective_limits

    out = _ssot_effective_limits("자연녹지지역", 1000.0)
    assert out is not None
    assert out["far"] == 80.0
    assert out["far_basis"] == "구조상한(건폐율×층수)"
    assert out["far_reliable"] is True


# ──────────────────────────────────────────────────────────────────────────
# ⑤ NATIONAL_FAR_LIMITS 그림자표 ↔ ZONE_LIMITS SSOT parity 가드(WP-U3)
# ──────────────────────────────────────────────────────────────────────────


def test_national_far_limits_parity_with_zone_limits_ssot():
    """far_incentive_calculator.NATIONAL_FAR_LIMITS는 auto_zoning ZONE_LIMITS(법정 SSOT,
    legal_zone_limits가 재노출)의 그림자표다 — 키·max_far 값이 1건이라도 드리프트하면
    인센티브 시뮬 상한과 법정 SSOT가 이중 진실이 되므로 CI에서 즉시 깬다.
    (2026-07-16 실측: 전 23키 키·값 일치 — 가드만 상설.)
    """
    from app.services.zoning.auto_zoning_service import ZONE_LIMITS
    from app.services.zoning.far_incentive_calculator import NATIONAL_FAR_LIMITS

    assert set(NATIONAL_FAR_LIMITS) == set(ZONE_LIMITS), (
        "그림자표 키 드리프트 — 한쪽에만 zone이 추가/삭제됐다. "
        f"NATIONAL에만: {set(NATIONAL_FAR_LIMITS) - set(ZONE_LIMITS)} / "
        f"ZONE_LIMITS에만: {set(ZONE_LIMITS) - set(NATIONAL_FAR_LIMITS)}"
    )
    drift = {
        zone: (NATIONAL_FAR_LIMITS[zone], ZONE_LIMITS[zone]["max_far"])
        for zone in NATIONAL_FAR_LIMITS
        if float(NATIONAL_FAR_LIMITS[zone]) != float(ZONE_LIMITS[zone]["max_far"])
    }
    assert not drift, f"그림자표 max_far 값 드리프트(그림자표/SSOT): {drift}"
