"""Required Data Matrix 계약 테스트 (W2-4, v4.0 [원본자료 충족도]·[단계별 Data Readiness Review]
실용 1차).

검증 축:
 (a) 4등급(required/conditionally_required/recommended/reference_only) × 상태 판정표
     (PRESENT_VALID/PRESENT_INVALID/MISSING/STALE/CONFLICT/NOT_APPLICABLE).
 (b) critical required가 MISSING/PRESENT_INVALID/CONFLICT → BLOCKED(STALE은 제외).
 (c) 비critical 결측(required 포함) → CONDITIONAL, reference_only는 종합판정에서 제외.
 (d) conditionally_required의 is_applicable predicate(적용/미적용 → NOT_APPLICABLE).
 (e) "0.0=미산정 센티널" 관례(is_sentinel_missing) — bool은 예외.
 (f) 계약 위반(critical+비required, conditionally_required+is_applicable 없음) 거부.
 (g) 기존 국소 게이트 동작 동일성 — site_basis_state.aggregate_p0()와의 등가성(위임 리팩토링
     증명, site_basis_state.py 자체는 변경하지 않음).
 (h) 대표 1단계 배선(project_pipeline._run_design) — 결측 시나리오 + 무회귀(BLOCKED 미발생).
"""
from __future__ import annotations

import pytest

from app.services.provenance.fact_status import FactStatus
from app.services.provenance.handoff_bundle import HandoffDecision
from app.services.provenance.required_data import (
    VALID_DATA_STATUSES,
    VALID_REQUIREMENT_LEVELS,
    DataRequirement,
    DataStatus,
    data_status_from_fact_status,
    evaluate_item,
    evaluate_matrix,
    is_sentinel_missing,
)

# ══════════════════════════════════════════════════════════════════════════
# (a) 4등급 × 상태 판정표
# ══════════════════════════════════════════════════════════════════════════


def test_requirement_levels_are_exactly_4():
    assert {
        "required", "conditionally_required", "recommended", "reference_only",
    } == VALID_REQUIREMENT_LEVELS


def test_data_statuses_are_exactly_6():
    assert {
        "PRESENT_VALID", "PRESENT_INVALID", "MISSING", "STALE", "CONFLICT", "NOT_APPLICABLE",
    } == VALID_DATA_STATUSES


@pytest.mark.parametrize(
    ("level", "kwargs", "value", "expected_status"),
    [
        ("required", {}, None, DataStatus.MISSING.value),
        ("required", {}, "값있음", DataStatus.PRESENT_VALID.value),
        ("required", {"is_invalid": lambda v, d: True}, "값있음", DataStatus.PRESENT_INVALID.value),
        ("required", {"is_stale": lambda v, d: True}, "값있음", DataStatus.STALE.value),
        ("required", {"is_conflict": lambda v, d: True}, "값있음", DataStatus.CONFLICT.value),
        ("recommended", {}, None, DataStatus.MISSING.value),
        ("recommended", {}, "값있음", DataStatus.PRESENT_VALID.value),
        ("reference_only", {}, None, DataStatus.MISSING.value),
        ("reference_only", {}, "값있음", DataStatus.PRESENT_VALID.value),
        ("conditionally_required", {"is_applicable": lambda d: True}, None, DataStatus.MISSING.value),
        ("conditionally_required", {"is_applicable": lambda d: True}, "값있음", DataStatus.PRESENT_VALID.value),
        ("conditionally_required", {"is_applicable": lambda d: False}, "값있음", DataStatus.NOT_APPLICABLE.value),
        ("conditionally_required", {"is_applicable": lambda d: False}, None, DataStatus.NOT_APPLICABLE.value),
    ],
)
def test_evaluate_item_level_status_table(level, kwargs, value, expected_status):
    req = DataRequirement(field="f", requirement_level=level, **kwargs)
    result = evaluate_item(req, {"f": value})
    assert result.status == expected_status
    assert result.requirement_level == level
    assert result.field == "f"


# ══════════════════════════════════════════════════════════════════════════
# (b)/(c) 종합판정(decision) — critical required → BLOCKED, 그 외 → CONDITIONAL/PASS
# ══════════════════════════════════════════════════════════════════════════


def test_critical_required_missing_blocks():
    req = DataRequirement(field="x", requirement_level="required", critical=True)
    result = evaluate_matrix([req], {"x": None})
    assert result.decision == HandoffDecision.BLOCKED.value
    assert result.blocking_fields == ["x"]


def test_critical_required_present_invalid_blocks():
    req = DataRequirement(
        field="x", requirement_level="required", critical=True,
        is_invalid=lambda v, d: v == "bad",
    )
    result = evaluate_matrix([req], {"x": "bad"})
    assert result.decision == HandoffDecision.BLOCKED.value


def test_critical_required_conflict_blocks():
    req = DataRequirement(
        field="x", requirement_level="required", critical=True,
        is_conflict=lambda v, d: True,
    )
    result = evaluate_matrix([req], {"x": "v"})
    assert result.decision == HandoffDecision.BLOCKED.value


def test_critical_required_stale_does_not_block_only_conditional():
    """★STALE은 BLOCKED 유발 부류에서 제외된다(모듈독스트링 _BLOCKING_STATUSES 참고)."""
    req = DataRequirement(
        field="x", requirement_level="required", critical=True,
        is_stale=lambda v, d: True,
    )
    result = evaluate_matrix([req], {"x": "v"})
    assert result.decision == HandoffDecision.CONDITIONAL.value
    assert result.blocking_fields == []


def test_noncritical_required_missing_is_conditional_not_blocked():
    req = DataRequirement(field="x", requirement_level="required", critical=False)
    result = evaluate_matrix([req], {"x": None})
    assert result.decision == HandoffDecision.CONDITIONAL.value
    assert result.blocking_fields == []
    assert result.conditional_reasons


def test_all_satisfied_is_pass():
    reqs = [
        DataRequirement(field="a", requirement_level="required", critical=True),
        DataRequirement(field="b", requirement_level="recommended"),
    ]
    result = evaluate_matrix(reqs, {"a": 1, "b": 2})
    assert result.decision == HandoffDecision.PASS.value
    assert result.conditional_reasons == []


def test_reference_only_missing_excluded_from_decision():
    """참고용(reference_only) 결측은 종합판정에 영향을 주지 않는다(items에는 여전히 기록됨)."""
    reqs = [
        DataRequirement(field="required_field", requirement_level="required", critical=True),
        DataRequirement(field="ref_field", requirement_level="reference_only"),
    ]
    result = evaluate_matrix(reqs, {"required_field": "ok", "ref_field": None})
    assert result.decision == HandoffDecision.PASS.value
    ref_item = next(i for i in result.items if i.field == "ref_field")
    assert ref_item.status == DataStatus.MISSING.value  # 기록은 되지만
    assert result.conditional_reasons == []  # 판정에는 영향 없음


def test_mixed_critical_and_noncritical_blocking_wins_over_conditional():
    reqs = [
        DataRequirement(field="critical_missing", requirement_level="required", critical=True),
        DataRequirement(field="soft_missing", requirement_level="recommended"),
    ]
    result = evaluate_matrix(reqs, {"critical_missing": None, "soft_missing": None})
    assert result.decision == HandoffDecision.BLOCKED.value
    assert result.blocking_fields == ["critical_missing"]


# ══════════════════════════════════════════════════════════════════════════
# (d) conditionally_required predicate
# ══════════════════════════════════════════════════════════════════════════


def test_conditionally_required_not_applicable_never_blocks_even_if_critical():
    req = DataRequirement(
        field="slope_survey", requirement_level="conditionally_required", critical=True,
        applicability="자연녹지지역이고 land_category가 임야일 때만 요구",
        is_applicable=lambda d: d.get("zone_type") == "자연녹지지역",
    )
    result = evaluate_matrix([req], {"zone_type": "제2종일반주거지역", "slope_survey": None})
    assert result.decision == HandoffDecision.PASS.value
    assert result.items[0].status == DataStatus.NOT_APPLICABLE.value


def test_conditionally_required_applicable_and_missing_blocks_when_critical():
    req = DataRequirement(
        field="slope_survey", requirement_level="conditionally_required", critical=True,
        applicability="자연녹지지역이고 land_category가 임야일 때만 요구",
        is_applicable=lambda d: d.get("zone_type") == "자연녹지지역",
    )
    result = evaluate_matrix([req], {"zone_type": "자연녹지지역", "slope_survey": None})
    assert result.decision == HandoffDecision.BLOCKED.value


def test_conditionally_required_without_is_applicable_rejected():
    with pytest.raises(ValueError, match="is_applicable"):
        DataRequirement(field="x", requirement_level="conditionally_required")


# ══════════════════════════════════════════════════════════════════════════
# (e) "0.0=미산정 센티널" 관례
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        (0, True),
        (0.0, True),
        ("", True),
        ([], True),
        ({}, True),
        (5, False),
        (5.0, False),
        ("값", False),
        ([1], False),
        (True, False),   # ★bool 예외 — 명시적 True는 값 있음
        (False, False),  # ★bool 예외 — 명시적 False도 "값 없음"이 아니라 "값이 False임"
    ],
)
def test_is_sentinel_missing(value, expected):
    assert is_sentinel_missing(value) is expected


def test_evaluate_item_uses_sentinel_zero_as_missing_by_default():
    req = DataRequirement(field="max_far", requirement_level="required")
    result = evaluate_item(req, {"max_far": 0.0})
    assert result.status == DataStatus.MISSING.value


def test_evaluate_item_bool_false_requires_custom_missing_predicate():
    """bool 필드(예: rights_confirmed)는 기본 판정자로는 False가 MISSING이 아니다 — 커스텀
    is_missing을 명시적으로 주입해야 한다(모듈독스트링 예외 근거)."""
    req = DataRequirement(field="rights_confirmed", requirement_level="required")
    result = evaluate_item(req, {"rights_confirmed": False})
    assert result.status == DataStatus.PRESENT_VALID.value  # 기본 판정자 기준으로는 값 있음

    req_custom = DataRequirement(
        field="rights_confirmed", requirement_level="required",
        is_missing=lambda v: v is not True,
    )
    result_custom = evaluate_item(req_custom, {"rights_confirmed": False})
    assert result_custom.status == DataStatus.MISSING.value


# ══════════════════════════════════════════════════════════════════════════
# (f) 계약 위반 거부
# ══════════════════════════════════════════════════════════════════════════


def test_critical_on_non_required_level_rejected():
    with pytest.raises(ValueError, match="required"):
        DataRequirement(field="x", requirement_level="recommended", critical=True)


def test_invalid_requirement_level_rejected():
    with pytest.raises(ValueError, match="requirement_level"):
        DataRequirement(field="x", requirement_level="mandatory")


# ══════════════════════════════════════════════════════════════════════════
# FactStatus 연결점(CONFLICT/STALE)
# ══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("fact_status", "expected"),
    [
        (None, DataStatus.MISSING.value),
        (FactStatus.UNKNOWN.value, DataStatus.MISSING.value),
        (FactStatus.CONFLICT.value, DataStatus.CONFLICT.value),
        (FactStatus.STALE.value, DataStatus.STALE.value),
        (FactStatus.OBSERVED.value, DataStatus.PRESENT_VALID.value),
        (FactStatus.DERIVED.value, DataStatus.PRESENT_VALID.value),
        (FactStatus.ASSUMED.value, DataStatus.PRESENT_VALID.value),
        (FactStatus.INFERRED.value, DataStatus.PRESENT_VALID.value),
    ],
)
def test_data_status_from_fact_status(fact_status, expected):
    assert data_status_from_fact_status(fact_status) == expected


# ══════════════════════════════════════════════════════════════════════════
# (g) 기존 국소 게이트 동작 동일성 — site_basis_state.aggregate_p0() 등가성
#
# ★site_basis_state.py 자체는 변경하지 않는다(즉시 이관 금지 — 모듈독스트링 참고). 이 테스트는
# 그 모듈이 이미 강제하는 "P0 3게이트 중 하나라도 미충족이면 전체 미충족"을 이 공용 계약
# (access/dev_act_permit/rights 3개 필드를 requirement_level=required+critical=True로 선언한
# 매트릭스)으로 표현했을 때 동일한 결론(충족/미충족)에 도달함을 증명한다.
# ══════════════════════════════════════════════════════════════════════════


def _p0_status_requirement(field: str) -> DataRequirement:
    """P2/P4 공용 어휘(PASS/CONDITIONAL=충족, BLOCKED/REQUIRES_AUTHORITY_CONFIRMATION/None=
    미충족)를 이 계약으로 표현하는 어댑터(테스트 전용 — site_basis_state.py는 변경 없음)."""
    return DataRequirement(
        field=field, requirement_level="required", critical=True,
        is_missing=lambda v: v is None,
        is_invalid=lambda v, d: str(v).strip().upper() not in {"PASS", "CONDITIONAL"},
    )


def _rights_requirement() -> DataRequirement:
    return DataRequirement(
        field="rights", requirement_level="required", critical=True,
        is_missing=lambda v: v is None,
        is_invalid=lambda v, d: v is not True,
    )


_P0_EQUIVALENCE_CASES = [
    ("PASS", "PASS", True),
    ("CONDITIONAL", "PASS", True),
    ("PASS", "CONDITIONAL", True),
    ("BLOCKED", "PASS", True),
    (None, "PASS", True),
    ("PASS", "REQUIRES_AUTHORITY_CONFIRMATION", True),
    ("PASS", "PASS", False),
    ("PASS", "PASS", None),
    ("BLOCKED", "BLOCKED", False),
]


@pytest.mark.parametrize(("access_status", "dev_act_status", "rights_confirmed"), _P0_EQUIVALENCE_CASES)
def test_matrix_decision_matches_site_basis_aggregate_p0_for_representative_cases(
    access_status, dev_act_status, rights_confirmed,
):
    from app.services.basis.site_basis_state import aggregate_p0

    all_clear, _gates = aggregate_p0(
        access_status=access_status, dev_act_status=dev_act_status,
        rights_confirmed=rights_confirmed,
    )

    requirements = [
        _p0_status_requirement("access"), _p0_status_requirement("dev_act_permit"), _rights_requirement(),
    ]
    data = {"access": access_status, "dev_act_permit": dev_act_status, "rights": rights_confirmed}
    result = evaluate_matrix(requirements, data)

    assert (result.decision != HandoffDecision.BLOCKED.value) == all_clear


# ══════════════════════════════════════════════════════════════════════════
# (h) 대표 1단계 배선(project_pipeline._run_design) — 결측 시나리오 + 무회귀
#
# ★오프라인·결정적 원칙(test_handoff_bundle.py 선례 동형) — _run_design을 직접 호출해
# DB/네트워크 없이 검증한다.
# ══════════════════════════════════════════════════════════════════════════


def _fresh_state(project_id: str = "t-w2-4"):
    from app.services.pipeline.project_pipeline import PipelineStage, PipelineState, StageResult

    state = PipelineState(project_id=project_id, address="서울특별시 강남구 역삼동 736")
    for stage in PipelineStage:
        state.stages[stage.value] = StageResult(stage=stage)
    return state


async def test_run_design_all_fields_present_yields_pass_and_no_assumed_fields():
    from app.services.pipeline.project_pipeline import ProjectPipeline, SiteToDesignPayload

    pipeline = ProjectPipeline()
    state = _fresh_state()
    state.site_to_design = SiteToDesignPayload(
        zone_type="제2종일반주거지역", max_bcr=60.0, max_far=200.0, land_area_sqm=500.0,
    )
    await pipeline._run_design(state, {})

    design_data = state.stages["design"].data
    assert "assumed_fields" not in design_data
    assert "data_quality" not in design_data
    assert design_data["data_readiness"]["decision"] == HandoffDecision.PASS.value
    assert design_data["data_readiness"]["blocking_fields"] == []


async def test_run_design_missing_land_area_only_matches_legacy_assumed_fields_label():
    """★동작 동일성 — 옛 ad hoc `if not site.land_area_sqm: append("land_area_sqm(500㎡ 가정)")`
    이 만들던 것과 정확히 같은 문자열을 새 매트릭스 배선이 재생산한다."""
    from app.services.pipeline.project_pipeline import ProjectPipeline, SiteToDesignPayload

    pipeline = ProjectPipeline()
    state = _fresh_state()
    state.site_to_design = SiteToDesignPayload(
        zone_type="제2종일반주거지역", max_bcr=60.0, max_far=200.0, land_area_sqm=0.0,
    )
    await pipeline._run_design(state, {})

    design_data = state.stages["design"].data
    assert design_data["assumed_fields"] == ["land_area_sqm(500㎡ 가정)"]
    assert design_data["data_quality"] == "assumed_defaults"
    # 폴백 수치 자체는 리팩토링 전후 불변 — 500㎡ 그대로 사용.
    assert design_data["total_gfa_sqm"] == pytest.approx(500.0 * (200.0 / 100))
    # ★무회귀 — 새 매트릭스가 이 지점을 절대 BLOCKED로 만들지 않는다(critical=False 선언).
    assert design_data["data_readiness"]["decision"] == HandoffDecision.CONDITIONAL.value
    assert design_data["data_readiness"]["blocking_fields"] == []


async def test_run_design_all_three_core_fields_missing_still_never_blocks():
    """★무회귀(핵심) — 대지면적·건폐율·용적률이 전부 결측이어도(오늘까지 그래왔듯) 파이프라인은
    계속 진행하고, 새 매트릭스도 BLOCKED가 아니라 CONDITIONAL을 방출한다."""
    from app.services.pipeline.project_pipeline import ProjectPipeline, SiteToDesignPayload

    pipeline = ProjectPipeline()
    state = _fresh_state()
    state.site_to_design = SiteToDesignPayload(zone_type="", max_bcr=0.0, max_far=0.0, land_area_sqm=0.0)

    await pipeline._run_design(state, {})  # 예외 없이 통과(무회귀)

    design_data = state.stages["design"].data
    assert set(design_data["assumed_fields"]) == {
        "land_area_sqm(500㎡ 가정)", "max_bcr(60% 가정)", "max_far(200% 가정)",
    }
    assert design_data["data_readiness"]["decision"] == HandoffDecision.CONDITIONAL.value
    assert design_data["data_readiness"]["blocking_fields"] == []
    # 폴백 수치 적용 결과(500㎡/60%/200%)도 리팩토링 전후 동일.
    assert design_data["total_gfa_sqm"] == pytest.approx(500.0 * (200.0 / 100))
    assert design_data["bcr_used_pct"] == 60.0
    assert design_data["far_used_pct"] == 200.0


async def test_run_design_data_readiness_items_include_all_declared_fields():
    from app.services.pipeline.project_pipeline import ProjectPipeline, SiteToDesignPayload

    pipeline = ProjectPipeline()
    state = _fresh_state()
    state.site_to_design = SiteToDesignPayload(
        zone_type="", max_bcr=60.0, max_far=200.0, land_area_sqm=500.0,
    )
    await pipeline._run_design(state, {})

    fields = {item["field"] for item in state.stages["design"].data["data_readiness"]["items"]}
    assert fields == {"land_area_sqm", "max_bcr", "max_far", "zone_type"}
