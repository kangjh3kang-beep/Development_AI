"""A1 회귀가드 — `_run_design_review`(project_pipeline.py)가 실존 라우터 심볼만 import하는지 잠근다.

★배경(버그): 과거 `_run_design_review`가 `from apps.api.app.routers.deliberation import
_post_analyze, _wrap_result`를 했으나 두 심볼 모두 현 라우터에 부재(실존 심볼은
`_engine_post_analyze`·`_compat_fields`)했다. 함수 전체가 넓은 `except Exception`으로 감싸여
있어 ImportError가 삼켜지고 design_review 단계가 매번 무음 SKIPPED였다. 이 테스트는
(1) import 자체가 실제로 성공하는지, (2) 정상 경로에서 단계 data가 기대 계약을 채우는지,
(3) rules[] 무날조 가드(대지면적 미확보 시 rule 생략)를 잠근다.
"""
from __future__ import annotations

from app.services.pipeline.project_pipeline import (
    DesignToCostPayload,
    PipelineStage,
    PipelineState,
    PipelineStatus,
    ProjectPipeline,
    SiteToDesignPayload,
    StageResult,
)
from apps.api.app.routers import deliberation as delib


def test_design_review_imports_symbols_that_exist_in_router():
    """★핵심 회귀가드: project_pipeline이 실제로 import하는 심볼(_engine_post_analyze·_compat_fields)이
    라우터에 실존하고 callable인지 직접 검증한다(과거 _post_analyze/_wrap_result는 부재라 ImportError였다)."""
    from apps.api.app.routers.deliberation import _compat_fields, _engine_post_analyze

    assert callable(_engine_post_analyze)
    assert callable(_compat_fields)
    # ★과거 버그 심볼은 더 이상 라우터에 없어야 한다(재도입 시 이 assert가 깨져 알려준다).
    assert not hasattr(delib, "_post_analyze")
    assert not hasattr(delib, "_wrap_result")


def _state_with_design(*, land_area_sqm: float, building_area_sqm: float,
                       total_gfa_sqm: float, max_bcr: float = 60.0, max_far: float = 200.0) -> PipelineState:
    state = PipelineState(address="서울 강남구 역삼동 1")
    state.site_to_design = SiteToDesignPayload(
        pnu_codes=["1168010100101230000"], zone_type="제2종일반주거지역",
        max_bcr=max_bcr, max_far=max_far, land_area_sqm=land_area_sqm,
        address="서울 강남구 역삼동 1",
    )
    state.design_to_cost = DesignToCostPayload(total_gfa_sqm=total_gfa_sqm)
    state.stages["design"] = StageResult(
        stage=PipelineStage.DESIGN, status=PipelineStatus.COMPLETED,
        data={"building_area_sqm": building_area_sqm})
    state.stages[PipelineStage.DESIGN_REVIEW.value] = StageResult(stage=PipelineStage.DESIGN_REVIEW)
    return state


async def test_design_review_populates_compat_fields_on_success(monkeypatch):
    """정상 경로 — 엔진 응답이 _compat_fields 평면 필드(complianceScore·finalStatus·findings)로 채워진다."""
    async def _fake_post(dump, deterministic=True, **kw):
        return {
            "run_id": "11111111-1111-1111-1111-111111111111",
            "input_hash": "h", "snapshot_id": "snap-1",
            "findings": [{"check_id": "FAR", "status": "pass"}],
            "report": {"sections": {"CONFIRMED": [1, 2], "NEEDS_REVIEW": [], "BLOCKED": []}},
        }, "ok"

    monkeypatch.setattr(delib, "_engine_post_analyze", _fake_post)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=280.0, total_gfa_sqm=900.0)
    await p._run_design_review(state, {})

    data = state.stages[PipelineStage.DESIGN_REVIEW.value].data
    assert data["status"] == "ok"
    assert data["run_id"] == "11111111-1111-1111-1111-111111111111"
    assert data["complianceScore"] == 100.0
    assert data["finalStatus"] == "CONFIRMED"
    assert data["findings"] == [{"check_id": "FAR", "status": "pass"}]
    # 단계 status는 SKIPPED로 강등되지 않아야 한다(정상 처리).
    assert state.stages[PipelineStage.DESIGN_REVIEW.value].status != PipelineStatus.SKIPPED


async def test_design_review_degrades_gracefully_when_engine_unreachable(monkeypatch):
    """엔진 미연결/오류 → degraded SKIPPED(파이프라인 무파괴). 무음 스킵이 아니라 reason 표면화."""
    async def _fake_post(dump, deterministic=True, **kw):
        return None, "engine_unreachable"

    monkeypatch.setattr(delib, "_engine_post_analyze", _fake_post)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=280.0, total_gfa_sqm=900.0)
    await p._run_design_review(state, {})

    stage = state.stages[PipelineStage.DESIGN_REVIEW.value]
    assert stage.status == PipelineStatus.SKIPPED
    assert stage.data == {"status": "degraded", "reason": "engine_unreachable"}


async def test_design_review_rules_included_when_land_area_and_limits_present(monkeypatch):
    """대지면적·법정한도가 모두 있으면 rules[](BCR_LIMIT/FAR_LIMIT)가 payload에 실린다."""
    captured: dict = {}

    async def _fake_post(dump, deterministic=True, **kw):
        captured["dump"] = dump
        return {"run_id": None, "report": {"sections": {}}}, "ok"

    monkeypatch.setattr(delib, "_engine_post_analyze", _fake_post)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=250.0, total_gfa_sqm=800.0,
                               max_bcr=60.0, max_far=200.0)
    await p._run_design_review(state, {})

    rules = captured["dump"].get("rules")
    assert rules, "대지면적·한도가 있으면 rules가 채워져야 한다"
    by_id = {r["rule"]["rule_id"]: r for r in rules}
    assert by_id["BCR_LIMIT"]["measured"] == 50.0   # 250/500*100
    assert by_id["BCR_LIMIT"]["limit"] == 60.0
    assert by_id["FAR_LIMIT"]["measured"] == 160.0  # 800/500*100
    assert by_id["FAR_LIMIT"]["limit"] == 200.0


async def test_design_review_rules_omitted_when_land_area_zero_no_fabrication(monkeypatch):
    """★무날조 가드: 대지면적 미확보(0)면 measured를 0.0으로 지어내지 않고 rules 자체를 생략한다."""
    captured: dict = {}

    async def _fake_post(dump, deterministic=True, **kw):
        captured["dump"] = dump
        return {"run_id": None, "report": {"sections": {}}}, "ok"

    monkeypatch.setattr(delib, "_engine_post_analyze", _fake_post)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=0.0, building_area_sqm=250.0, total_gfa_sqm=800.0)
    await p._run_design_review(state, {})

    assert not captured["dump"].get("rules")
