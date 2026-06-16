"""P5 T2 — 파이프라인 단계별 검증 강제(_verify_stage). VerifierService 규칙기반 graceful."""
import pytest

from app.services.pipeline.project_pipeline import (
    PipelineStage,
    PipelineState,
    PipelineStatus,
    ProjectPipeline,
    StageResult,
)

pytestmark = pytest.mark.asyncio


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
