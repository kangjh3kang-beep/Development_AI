"""다필지 합필(land_assembly) 시니어 평가기 단위테스트 — S5(C-senior).

시나리오 3종(정상 합필/차단 혼재/미수렴 포함) + 규칙별 임계 경계 + 결측 생략(무목업).
"""

from app.services.senior_agents.evaluators.base import BLOCK, PASS, WARN
from app.services.senior_agents.evaluators.land_assembly import (
    BLOCKED_SHARE_BLOCK_PCT,
    BLOCKED_SHARE_WARN_PCT,
    CONDITIONAL_DEPENDENCY_WARN_PCT,
    evaluate_land_assembly,
)


def _by_id(evals):
    return {e.rule_id: e for e in evals}


# ── 시나리오 1: 정상 합필(차단 없음·검증 수렴·조건부 미미·단일 용도지역) ──

def test_scenario_clean_assembly_all_pass():
    evals = evaluate_land_assembly({
        "gross_sqm": 1000.0,
        "usable_confirmed_sqm": 900.0,
        "usable_conditional_sqm": 100.0,
        "excluded_sqm": 0.0,
        "blocked_sqm": 0.0,
        "unverified_parcel_count": 0,
        "zone_straddle": False,
    })
    by = _by_id(evals)
    assert by["assembly.blocked_share"].verdict == PASS
    assert by["assembly.area_verification"].verdict == PASS
    assert by["assembly.conditional_dependency"].verdict == PASS
    assert by["assembly.zone_straddle"].verdict == PASS
    # 모든 평가에 근거(basis)·임계(threshold) 동반 + 내부 기준임을 정직 명시
    for e in evals:
        assert e.basis and e.threshold
    assert "법정 기준 아님" in by["assembly.blocked_share"].basis


# ── 규칙 ①: 차단면적 비중 >30% WARN · >50% BLOCK ──

def test_blocked_share_thresholds():
    base = {"gross_sqm": 1000.0}
    # 30% 정확히 → PASS(초과만 WARN)
    assert _by_id(evaluate_land_assembly({**base, "blocked_sqm": 300.0}))[
        "assembly.blocked_share"].verdict == PASS
    # 31% → WARN
    warn = _by_id(evaluate_land_assembly({**base, "blocked_sqm": 310.0}))["assembly.blocked_share"]
    assert warn.verdict == WARN and warn.value == 31.0 and warn.unit == "%"
    # 50% 정확히 → WARN(초과만 BLOCK)
    assert _by_id(evaluate_land_assembly({**base, "blocked_sqm": 500.0}))[
        "assembly.blocked_share"].verdict == WARN
    # 51% → BLOCK
    assert _by_id(evaluate_land_assembly({**base, "blocked_sqm": 510.0}))[
        "assembly.blocked_share"].verdict == BLOCK
    # 임계 상수 = 문서화된 값
    assert BLOCKED_SHARE_WARN_PCT == 30.0 and BLOCKED_SHARE_BLOCK_PCT == 50.0


def test_blocked_share_falls_back_to_excluded():
    # blocked_sqm 결측 시 excluded_sqm(BLOCKED+건축불가 지목)로 보수 평가 + detail에 출처 명시
    e = _by_id(evaluate_land_assembly({"gross_sqm": 1000.0, "excluded_sqm": 600.0}))[
        "assembly.blocked_share"]
    assert e.verdict == BLOCK and "excluded_sqm" in e.detail


# ── 규칙 ②: 미수렴 필지 존재 → WARN(확정 전 지적측량 확인) ──

def test_unverified_parcels_warn():
    e = _by_id(evaluate_land_assembly({"unverified_parcel_count": 2}))["assembly.area_verification"]
    assert e.verdict == WARN and e.value == 2 and "측량" in e.detail
    assert _by_id(evaluate_land_assembly({"unverified_parcel_count": 0}))[
        "assembly.area_verification"].verdict == PASS


# ── 규칙 ③: 조건부 의존도 >50% → WARN ──

def test_conditional_dependency_threshold():
    # 조건부 300 / (확정 300 + 조건부 300) = 50% 정확히 → PASS(초과만 WARN)
    ok = _by_id(evaluate_land_assembly(
        {"usable_confirmed_sqm": 300.0, "usable_conditional_sqm": 300.0}))
    assert ok["assembly.conditional_dependency"].verdict == PASS
    # 조건부 301/600.. → >50% WARN
    warn = _by_id(evaluate_land_assembly(
        {"usable_confirmed_sqm": 299.0, "usable_conditional_sqm": 301.0}))
    e = warn["assembly.conditional_dependency"]
    assert e.verdict == WARN and e.unit == "%"
    assert CONDITIONAL_DEPENDENCY_WARN_PCT == 50.0
    # 분모 0(확정+조건부=0) → 생략(무목업)
    assert "assembly.conditional_dependency" not in _by_id(evaluate_land_assembly(
        {"usable_confirmed_sqm": 0, "usable_conditional_sqm": 0}))


# ── 규칙 ④: 용도지역 혼재 초과형(부분별각각) → WARN ──

def test_zone_straddle_verdicts():
    # 초과형(부분별각각) → WARN
    e = _by_id(evaluate_land_assembly(
        {"zone_straddle": True, "straddle_applied_rule": "부분별각각"}))["assembly.zone_straddle"]
    assert e.verdict == WARN and "부분별" in e.detail
    # 소규모 걸침(가중평균+과반) → PASS
    assert _by_id(evaluate_land_assembly(
        {"zone_straddle": True, "straddle_applied_rule": "가중평균+과반"}))[
        "assembly.zone_straddle"].verdict == PASS
    # 걸침인데 적용규정 미상 → 보수적으로 WARN(무날조 — 유리한 가정 금지)
    assert _by_id(evaluate_land_assembly({"zone_straddle": True}))[
        "assembly.zone_straddle"].verdict == WARN
    # 단일 용도지역(명시적 False) → PASS
    assert _by_id(evaluate_land_assembly({"zone_straddle": False}))[
        "assembly.zone_straddle"].verdict == PASS


# ── 시나리오 2: 차단 혼재(차단 55%·혼재 초과형) → BLOCK 포함 ──

def test_scenario_blocked_mixed():
    evals = evaluate_land_assembly({
        "gross_sqm": 2000.0,
        "usable_confirmed_sqm": 700.0,
        "usable_conditional_sqm": 200.0,
        "blocked_sqm": 1100.0,
        "unverified_parcel_count": 0,
        "zone_straddle": True,
        "straddle_applied_rule": "부분별각각",
    })
    by = _by_id(evals)
    assert by["assembly.blocked_share"].verdict == BLOCK  # 55% > 50%
    assert by["assembly.zone_straddle"].verdict == WARN
    assert by["assembly.area_verification"].verdict == PASS


# ── 시나리오 3: 미수렴 포함(검증 WARN·조건부 과다 WARN) ──

def test_scenario_unverified_and_conditional():
    evals = evaluate_land_assembly({
        "gross_sqm": 1000.0,
        "usable_confirmed_sqm": 200.0,
        "usable_conditional_sqm": 500.0,
        "blocked_sqm": 100.0,  # 10% → PASS
        "unverified_parcel_count": 3,
    })
    by = _by_id(evals)
    assert by["assembly.blocked_share"].verdict == PASS
    assert by["assembly.area_verification"].verdict == WARN
    assert by["assembly.conditional_dependency"].verdict == WARN  # 500/700 ≈ 71%


# ── 결측·방어적 파싱(무목업) ──

def test_missing_inputs_skip_no_mockup():
    assert evaluate_land_assembly({}) == []
    # gross 0/음수 → 차단 비중 생략
    assert "assembly.blocked_share" not in _by_id(
        evaluate_land_assembly({"gross_sqm": 0, "blocked_sqm": 10}))
    # 비수치 → 생략
    assert "assembly.area_verification" not in _by_id(
        evaluate_land_assembly({"unverified_parcel_count": "abc"}))
    # 음수 미수렴 수(비정상 입력) → 생략
    assert "assembly.area_verification" not in _by_id(
        evaluate_land_assembly({"unverified_parcel_count": -1}))
