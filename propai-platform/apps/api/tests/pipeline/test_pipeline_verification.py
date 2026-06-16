"""P5 T2/T3 — 파이프라인 단계 검증(_verify_stage) + 공공데이터 cross_validate 신뢰가드.

VerifierService 규칙기반 graceful · cross_validate 결정론. asyncio_mode=auto — 마커 불요.
"""
from app.services.pipeline.project_pipeline import (
    PipelineStage,
    PipelineState,
    PipelineStatus,
    ProjectPipeline,
    StageResult,
)


async def test_verify_stage_attaches_verification_block_additive():
    p = ProjectPipeline()
    state = PipelineState(address="서울 테스트")
    state.stages["feasibility"] = StageResult(
        stage=PipelineStage.FEASIBILITY, status=PipelineStatus.COMPLETED,
        data={"profit_rate_pct": 12.0, "land_area_sqm": 300.0})
    await p._verify_stage(state, PipelineStage.FEASIBILITY)
    v = state.stages["feasibility"].data["verification"]
    assert v["verdict"] in ("pass", "warn", "fail")     # 규칙기반이라도 verdict 산출
    assert "issues" in v
    assert state.stages["feasibility"].data["profit_rate_pct"] == 12.0   # 결정론 수치 불변


async def test_verify_stage_flags_negative_area():
    p = ProjectPipeline()
    state = PipelineState(address="서울 테스트")
    state.stages["site_analysis"] = StageResult(
        stage=PipelineStage.SITE_ANALYSIS, status=PipelineStatus.COMPLETED,
        data={"land_area_sqm": -10.0, "max_far": 200.0})
    await p._verify_stage(state, PipelineStage.SITE_ANALYSIS)
    v = state.stages["site_analysis"].data["verification"]
    assert v["verdict"] == "fail"                       # 음수 면적 → high → fail(규칙)


async def test_verify_stage_skips_non_completed():
    p = ProjectPipeline()
    state = PipelineState(address="x")
    state.stages["cost"] = StageResult(stage=PipelineStage.COST, status=PipelineStatus.SKIPPED, data={})
    await p._verify_stage(state, PipelineStage.COST)
    assert "verification" not in state.stages["cost"].data   # skip 단계는 검증 안 함(정직)


# ── P5 T3: 공공데이터 cross_validate 신뢰가드(site_analysis) ──

def test_trust_guard_cross_validates_price_signals():
    p = ProjectPipeline()
    state = PipelineState(address="x")
    state.stages["site_analysis"] = StageResult(
        stage=PipelineStage.SITE_ANALYSIS, status=PipelineStatus.COMPLETED,
        data={"pricing": {"official_price_per_sqm": 5_000_000,
                          "nearby_transactions": [{"price_per_sqm": 5_200_000},
                                                  {"price_per_sqm": 4_800_000}]}})
    p._attach_trust_guard(state)
    tg = state.stages["site_analysis"].data["trust_guard"]
    cv = tg["price_cross_validation"]
    assert cv["verdict"] in ("pass", "warn", "fail") and cv["trusted_value"] is not None
    assert len(cv["used_sources"]) >= 1
    # 결정론 원본 값 불변
    assert state.stages["site_analysis"].data["pricing"]["official_price_per_sqm"] == 5_000_000


def test_trust_guard_flags_outlier_low_consensus():
    p = ProjectPipeline()
    state = PipelineState(address="x")
    # 공시지가 500만 vs 인근실거래 2500만(5배 괴리) → 이상치 제외/낮은 합의
    state.stages["site_analysis"] = StageResult(
        stage=PipelineStage.SITE_ANALYSIS, status=PipelineStatus.COMPLETED,
        data={"pricing": {"official_price_per_sqm": 5_000_000,
                          "nearby_transactions": [{"price_per_sqm": 25_000_000}]}})
    p._attach_trust_guard(state)
    cv = state.stages["site_analysis"].data["trust_guard"]["price_cross_validation"]
    assert cv["excluded_outliers"] or cv["verdict"] in ("warn", "fail")


def test_trust_guard_skips_assumed_defaults():
    p = ProjectPipeline()
    state = PipelineState(address="x")
    state.stages["site_analysis"] = StageResult(
        stage=PipelineStage.SITE_ANALYSIS, status=PipelineStatus.COMPLETED,
        data={"data_quality": "assumed_defaults", "pricing": {"official_price_per_sqm": 0}})
    p._attach_trust_guard(state)
    assert state.stages["site_analysis"].data["trust_guard"]["skipped"] is True


def test_trust_guard_skips_when_no_price_signal():
    p = ProjectPipeline()
    state = PipelineState(address="x")
    state.stages["site_analysis"] = StageResult(
        stage=PipelineStage.SITE_ANALYSIS, status=PipelineStatus.COMPLETED, data={"pricing": {}})
    p._attach_trust_guard(state)
    assert state.stages["site_analysis"].data["trust_guard"]["reason"] == "no_price_signal"
