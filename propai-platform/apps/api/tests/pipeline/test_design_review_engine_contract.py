"""A1/D3 회귀가드 — `_run_design_review`(project_pipeline.py)가 라우터의 공용 감사경로만 경유하는지 잠근다.

★배경(D3 버그): 과거 `_run_design_review`는 `_engine_post_analyze`를 **직접** 호출해 engine_run_binding
결속·해시체인 감사원장 기록을 건너뛰었다(BFF는 감사 없는 판정 제공을 502로 금지하는데 파이프라인만 무감사
우회). 이제 라우터와 동일한 공용 함수 `run_deliberation_analysis`를 경유해 결속·감사·무결성·테넌트 격리를
동일 계약으로 강제한다. 이 테스트는
(1) 파이프라인이 실제로 `run_deliberation_analysis`를 호출하는지(무감사 `_engine_post_analyze` 직접호출 회귀 차단),
(2) 정상 경로에서 단계 data가 기대 계약(평면 필드)을 채우는지,
(3) 엔진 미연결/무결성 위반 시 degraded SKIPPED로 정직 강등하는지,
(4) rules[] 무날조 가드(대지면적 미확보 시 rule 생략)를 잠근다.

★PR#319 리뷰 반영 — 감사 실패(fail-closed 502)는 엔진 미연결/오류(degraded)와 **구분**되어야 한다(감사
이중잣대가 실패 처리에서 재발하지 않도록). 이 파일은 추가로
(5) 감사 fail-closed(502) → status="audit_failed"(FAILED)로 명시 강등 + 판정 데이터 미저장,
(6) 인증 컨텍스트(user/tenant contextvar) 부재 → 엔진 호출 자체를 하지 않고 동일한 fail-closed 경로(no_auth_context)
를 잠근다.
"""
from __future__ import annotations

from app.core import request_context
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


def test_design_review_routes_through_shared_audited_function():
    """★핵심 회귀가드: 공용 감사경로 `run_deliberation_analysis`가 라우터에 실존·callable이어야 한다.
    과거 무감사 우회 심볼(_post_analyze/_wrap_result)은 부재, 공용 헬퍼(_engine_post_analyze·_compat_fields)는
    시나리오 매트릭스가 여전히 사용하므로 실존 유지."""
    from apps.api.app.routers.deliberation import (
        _compat_fields,
        _engine_post_analyze,
        run_deliberation_analysis,
    )

    assert callable(run_deliberation_analysis)
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


def _with_auth_context(monkeypatch, *, user_id: str = "test-user", tenant_id: str = "test-tenant") -> None:
    """★인증 요청 컨텍스트 시뮬레이션 — `_run_design_review`가 로컬 import로 매 호출 재조회하는
    `app.core.request_context.get_current_user_id/get_current_tenant_id`를 monkeypatch한다(실 ContextVar를
    건드리지 않아 테스트 간 오염 위험 없음). 파이프라인 /run은 인증 게이트이므로 정상 경로에선 항상 채워진다."""
    monkeypatch.setattr(request_context, "get_current_user_id", lambda: user_id)
    monkeypatch.setattr(request_context, "get_current_tenant_id", lambda: tenant_id)


async def test_design_review_populates_compat_fields_on_success(monkeypatch):
    """정상 경로 — 공용 함수가 status ok 봉투(결속·감사 완료)를 돌려주면 단계 data가 평면 필드로 채워진다."""
    _with_auth_context(monkeypatch)

    async def _fake_run(payload, user, *, tenant=None):
        return {
            "degraded": False, "reused": False, "deterministic": True,
            "run_id": "11111111-1111-1111-1111-111111111111",
            "result": {"snapshot_id": "snap-1"},
            "audit_degraded": False, "audit_skipped": [],
            "status": "ok",
            "complianceScore": 100.0, "finalStatus": "CONFIRMED",
            "findings": [{"check_id": "FAR", "status": "pass"}],
            "sections": {"CONFIRMED": [1, 2]},
        }

    monkeypatch.setattr(delib, "run_deliberation_analysis", _fake_run)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=280.0, total_gfa_sqm=900.0)
    await p._run_design_review(state, {})

    data = state.stages[PipelineStage.DESIGN_REVIEW.value].data
    assert data["status"] == "ok"
    assert data["run_id"] == "11111111-1111-1111-1111-111111111111"
    assert data["complianceScore"] == 100.0
    assert data["finalStatus"] == "CONFIRMED"
    assert data["findings"] == [{"check_id": "FAR", "status": "pass"}]
    # 감사 출처가 표면화된다(무감사 우회 회귀 차단 신호).
    assert data["audit_degraded"] is False
    # 단계 status는 SKIPPED/FAILED로 강등되지 않아야 한다(정상 처리).
    assert state.stages[PipelineStage.DESIGN_REVIEW.value].status != PipelineStatus.SKIPPED
    assert state.stages[PipelineStage.DESIGN_REVIEW.value].status != PipelineStatus.FAILED


async def test_design_review_degrades_gracefully_when_engine_unreachable(monkeypatch):
    """엔진 미연결/오류 → degraded SKIPPED(파이프라인 무파괴). 무음 스킵이 아니라 reason 표면화.
    ★PR#319: 감사 fail-closed(FAILED/audit_failed)와 구분되어야 한다 — 이 경로는 감사 자체는 정상 기록되고
    엔진만 미도달인 경우(공용 함수가 200 degrade 봉투를 반환)이므로 여전히 SKIPPED/degraded가 맞다."""
    _with_auth_context(monkeypatch)

    async def _fake_run(payload, user, *, tenant=None):
        # 공용 함수의 degrade 봉투(_degrade) 형태 — status 키 없음·degraded=True·reason 동봉.
        return {"degraded": True, "final_status": "NEEDS_REVIEW", "reason": "engine_unreachable",
                "result": None, "audit_degraded": False, "audit_skipped": []}

    monkeypatch.setattr(delib, "run_deliberation_analysis", _fake_run)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=280.0, total_gfa_sqm=900.0)
    await p._run_design_review(state, {})

    stage = state.stages[PipelineStage.DESIGN_REVIEW.value]
    assert stage.status == PipelineStatus.SKIPPED
    assert stage.data == {"status": "degraded", "reason": "engine_unreachable"}


async def test_design_review_marks_audit_failed_distinctly_from_engine_degraded(monkeypatch):
    """★차단 결함 수정(PR#319 리뷰): 공용 함수가 감사 미기록으로 HTTPException(502)을 던지면(감사 없는
    판정 제공 금지 fail-closed) 엔진 미연결(degraded/SKIPPED)과 **다른** 상태로 강등되어야 한다 — status="audit_failed"
    + PipelineStatus.FAILED. 어떤 판정 데이터(complianceScore·findings 등)도 저장되지 않는다(감사 공백 방지)."""
    from fastapi import HTTPException

    _with_auth_context(monkeypatch)

    async def _fake_run(payload, user, *, tenant=None):
        raise HTTPException(status_code=502, detail="audit_write_failed")

    monkeypatch.setattr(delib, "run_deliberation_analysis", _fake_run)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=280.0, total_gfa_sqm=900.0)
    await p._run_design_review(state, {})

    stage = state.stages[PipelineStage.DESIGN_REVIEW.value]
    # ★engine_unreachable(SKIPPED)과 명확히 다른 status — 이중잣대 재발 차단의 핵심 단언.
    assert stage.status == PipelineStatus.FAILED
    assert stage.status != PipelineStatus.SKIPPED
    assert stage.data["status"] == "audit_failed"
    assert "audit_write_failed" in stage.data["reason"]
    assert stage.error is not None and "audit_write_failed" in stage.error
    # 판정 데이터가 절대 새지 않아야 한다 — data는 status/reason 2키뿐.
    assert set(stage.data.keys()) == {"status", "reason"}
    assert "complianceScore" not in stage.data
    assert "findings" not in stage.data


async def test_design_review_fails_closed_when_no_auth_context(monkeypatch):
    """★비차단 리뷰 반영(PR#319): 인증 요청 컨텍스트 밖(contextvar 공백 — 예: 향후 백그라운드/배치 실행)에서는
    빈 id/tenant로 결속·감사를 시도하지 않고, 엔진 호출 자체를 생략한 채 동일한 fail-closed 경로(audit_failed·
    FAILED·reason="no_auth_context")로 사전 강등해야 한다."""
    monkeypatch.setattr(request_context, "get_current_user_id", lambda: None)
    monkeypatch.setattr(request_context, "get_current_tenant_id", lambda: None)

    called = {"n": 0}

    async def _fake_run(payload, user, *, tenant=None):
        called["n"] += 1
        return {"status": "ok"}  # 호출되면 안 됨(가드가 사전 차단) — 만약 호출되면 아래 assert가 실패로 드러남.

    monkeypatch.setattr(delib, "run_deliberation_analysis", _fake_run)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=280.0, total_gfa_sqm=900.0)
    await p._run_design_review(state, {})

    stage = state.stages[PipelineStage.DESIGN_REVIEW.value]
    assert stage.status == PipelineStatus.FAILED
    assert stage.data == {"status": "audit_failed", "reason": "no_auth_context"}
    # 엔진/공용 함수가 아예 호출되지 않아야 한다(빈 테넌트로 결속·감사 시도 자체를 차단).
    assert called["n"] == 0


async def test_design_review_rules_included_when_land_area_and_limits_present(monkeypatch):
    """대지면적·법정한도가 모두 있으면 rules[](BCR_LIMIT/FAR_LIMIT)가 공용 함수로 넘긴 payload에 실린다."""
    _with_auth_context(monkeypatch)
    captured: dict = {}

    async def _fake_run(payload, user, *, tenant=None):
        captured["payload"] = payload
        return {"status": "ok", "run_id": "11111111-1111-1111-1111-111111111111",
                "complianceScore": None, "finalStatus": "CONFIRMED", "findings": [], "sections": {}}

    monkeypatch.setattr(delib, "run_deliberation_analysis", _fake_run)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=500.0, building_area_sqm=250.0, total_gfa_sqm=800.0,
                               max_bcr=60.0, max_far=200.0)
    await p._run_design_review(state, {})

    rules = captured["payload"].get("rules")
    assert rules, "대지면적·한도가 있으면 rules가 채워져야 한다"
    by_id = {r["rule"]["rule_id"]: r for r in rules}
    assert by_id["BCR_LIMIT"]["measured"] == 50.0   # 250/500*100
    assert by_id["BCR_LIMIT"]["limit"] == 60.0
    assert by_id["FAR_LIMIT"]["measured"] == 160.0  # 800/500*100
    assert by_id["FAR_LIMIT"]["limit"] == 200.0


async def test_design_review_rules_omitted_when_land_area_zero_no_fabrication(monkeypatch):
    """★무날조 가드: 대지면적 미확보(0)면 measured를 0.0으로 지어내지 않고 rules 자체를 생략한다."""
    _with_auth_context(monkeypatch)
    captured: dict = {}

    async def _fake_run(payload, user, *, tenant=None):
        captured["payload"] = payload
        return {"status": "ok", "run_id": "11111111-1111-1111-1111-111111111111",
                "complianceScore": None, "finalStatus": "CONFIRMED", "findings": [], "sections": {}}

    monkeypatch.setattr(delib, "run_deliberation_analysis", _fake_run)

    p = ProjectPipeline()
    state = _state_with_design(land_area_sqm=0.0, building_area_sqm=250.0, total_gfa_sqm=800.0)
    await p._run_design_review(state, {})

    assert not captured["payload"].get("rules")
