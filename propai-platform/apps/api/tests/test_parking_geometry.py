"""주차 기하 실현 가능성 검증 계약(스펙 P — W3-5) 단위 테스트.

app.services.parking 패키지: StallSpec·AisleSpec(치수 SSOT) · estimate_layout_capacity
(면적→수용력 1차 추정) · check_swept_path(swept path 1차 근사) · verify_parking_plan
(종합 PASS/WARN/FAIL)을 검증한다.

★법정 주차대수 산정(값) 자체는 이 테스트의 대상이 아니다 — 그 SSOT는
app.services.permit.building_code_rules.PARKING_REQUIREMENTS이며, 여기서는
verify_parking_plan이 그 값을 "재사용"하는지(중복 계산 없이 동일 결과를 내는지)만
교차검증한다.
"""

from __future__ import annotations

import math

from app.services.parking import (
    AISLE_SPECS,
    STALL_SPECS,
    ParkingPlanVerdict,
    StallType,
    check_swept_path,
    estimate_layout_capacity,
    required_legal_parking_count,
    verify_parking_plan,
)
from app.services.permit.building_code_rules import PARKING_REQUIREMENTS

# ══════════════════════════════════════════════════════════════════
# 1. StallSpec/AisleSpec — 치수 SSOT(주차장법 시행규칙 §3·§11) 고정값
# ══════════════════════════════════════════════════════════════════

class TestStallAndAisleSpecs:
    def test_general_stall_dimensions(self):
        s = STALL_SPECS[StallType.GENERAL]
        assert (s.width_m, s.length_m) == (2.5, 5.0)
        assert s.verified is True
        assert "시행규칙" in s.basis

    def test_expanded_stall_dimensions(self):
        s = STALL_SPECS[StallType.EXPANDED]
        assert (s.width_m, s.length_m) == (2.6, 5.2)

    def test_parallel_stall_dimensions(self):
        s = STALL_SPECS[StallType.PARALLEL]
        assert (s.width_m, s.length_m) == (2.0, 6.0)

    def test_disabled_stall_dimensions(self):
        s = STALL_SPECS[StallType.DISABLED]
        assert (s.width_m, s.length_m) == (3.3, 5.0)

    def test_all_stall_specs_have_basis_assumptions_limitations(self):
        """모든 판정에 근거·가정·한계 3필드 — 구획 스펙도 예외 없음."""
        for spec in STALL_SPECS.values():
            assert spec.basis
            assert isinstance(spec.assumptions, list)
            assert isinstance(spec.limitations, list)

    def test_aisle_widths_by_angle(self):
        assert AISLE_SPECS[90].aisle_width_m == 6.0
        assert AISLE_SPECS[60].aisle_width_m == 4.5
        assert AISLE_SPECS[45].aisle_width_m == 3.5
        assert AISLE_SPECS[0].aisle_width_m == 3.0  # 평행주차

    def test_all_aisle_specs_have_basis(self):
        for spec in AISLE_SPECS.values():
            assert spec.basis
            assert "시행규칙" in spec.basis


# ══════════════════════════════════════════════════════════════════
# 2. required_legal_parking_count — PARKING_REQUIREMENTS(SSOT) 재사용 교차검증
# ══════════════════════════════════════════════════════════════════

class TestRequiredLegalParkingCountReusesSSOT:
    def test_apartment_per_unit_matches_ssot_formula(self):
        """PARKING_REQUIREMENTS["아파트"]["per_unit"]와 동일 산식으로 계산되어야 함(이중화 금지)."""
        per_unit = PARKING_REQUIREMENTS["아파트"]["per_unit"]
        required, basis = required_legal_parking_count(building_type="아파트", unit_count=100)
        assert required == math.ceil(100 * per_unit)
        assert "세대" in basis

    def test_officetel_per_sqm_matches_ssot_formula(self):
        per_sqm = PARKING_REQUIREMENTS["오피스텔"]["additional_per_sqm"]
        required, basis = required_legal_parking_count(building_type="오피스텔", total_gfa_sqm=3000.0)
        assert required == math.ceil(3000.0 / per_sqm)
        assert "연면적" in basis

    def test_unknown_building_type_falls_back_to_apartment_rule(self):
        """미등록 건물유형은 PARKING_REQUIREMENTS의 아파트 폴백과 동일해야 함(엔진 fallback과 대칭)."""
        required, _ = required_legal_parking_count(building_type="미상유형", unit_count=50)
        apt_per_unit = PARKING_REQUIREMENTS["아파트"]["per_unit"]
        assert required == math.ceil(50 * apt_per_unit)


# ══════════════════════════════════════════════════════════════════
# 3. estimate_layout_capacity — 면적→수용력 1차 추정(모듈법 + 공제)
# ══════════════════════════════════════════════════════════════════

class TestEstimateLayoutCapacity:
    def test_zero_area_is_dishonest_zero_not_crash(self):
        result = estimate_layout_capacity(gross_area_sqm=0)
        assert result.estimated_capacity == 0
        assert result.verified is False
        assert result.limitations  # 사유 명시

    def test_larger_area_yields_more_capacity(self):
        small = estimate_layout_capacity(gross_area_sqm=500)
        large = estimate_layout_capacity(gross_area_sqm=5000)
        assert large.estimated_capacity > small.estimated_capacity

    def test_deduction_reduces_usable_area(self):
        result = estimate_layout_capacity(gross_area_sqm=1000)
        assert result.usable_area_sqm < result.gross_area_sqm
        assert 0 < result.deduction_ratio_total < 1

    def test_expanded_stall_has_larger_module_than_general(self):
        """확장형 구획이 일반형보다 모듈면적이 커야 함(같은 면적에서 수용력이 같거나 적음)."""
        general = estimate_layout_capacity(gross_area_sqm=2000, stall_type=StallType.GENERAL)
        expanded = estimate_layout_capacity(gross_area_sqm=2000, stall_type=StallType.EXPANDED)
        assert expanded.module_area_per_stall_sqm > general.module_area_per_stall_sqm
        assert expanded.estimated_capacity <= general.estimated_capacity

    def test_result_always_marked_unverified_first_pass_estimate(self):
        """1차 근사임을 verified=False로 항상 정직 표기(완전 최적화 배치 주장 금지)."""
        result = estimate_layout_capacity(gross_area_sqm=3000)
        assert result.verified is False
        assert result.basis
        assert result.assumptions
        assert result.limitations

    def test_custom_deduction_ratios_are_honored(self):
        default_result = estimate_layout_capacity(gross_area_sqm=2000)
        custom_result = estimate_layout_capacity(
            gross_area_sqm=2000, deduction_ratios={"ramp": 0.5}
        )
        assert custom_result.deduction_ratio_total == 0.5
        assert custom_result.usable_area_sqm < default_result.usable_area_sqm


# ══════════════════════════════════════════════════════════════════
# 4. check_swept_path — 최소회전반경 기반 1차 근사(완전 궤적 시뮬 아님)
# ══════════════════════════════════════════════════════════════════

class TestCheckSweptPath:
    def test_no_input_is_unavailable_not_fake_pass(self):
        """입력이 전혀 없으면 무조건 unavailable — 거짓 pass 금지."""
        result = check_swept_path()
        assert result.status == "unavailable"
        assert result.aisle_width_ok is None
        assert result.turn_radius_ok is None

    def test_sufficient_aisle_and_radius_passes(self):
        result = check_swept_path(
            parking_angle_deg=90, actual_aisle_width_m=6.5, actual_turn_radius_m=6.5,
        )
        assert result.status == "pass"
        assert result.aisle_width_ok is True
        assert result.turn_radius_ok is True

    def test_insufficient_turn_radius_fails(self):
        result = check_swept_path(
            parking_angle_deg=90, actual_aisle_width_m=6.5, actual_turn_radius_m=4.0,
        )
        assert result.status == "fail"
        assert result.turn_radius_ok is False

    def test_insufficient_aisle_width_fails(self):
        result = check_swept_path(
            parking_angle_deg=90, actual_aisle_width_m=4.0, actual_turn_radius_m=6.5,
        )
        assert result.status == "fail"
        assert result.aisle_width_ok is False

    def test_partial_input_is_warn(self):
        result = check_swept_path(parking_angle_deg=90, actual_aisle_width_m=6.5)
        assert result.status == "warn"

    def test_method_and_limitations_disclose_first_pass_nature(self):
        """★핵심 정직 표기: 완전 궤적 시뮬레이션이 아님을 항상 명시해야 한다."""
        result = check_swept_path(actual_aisle_width_m=6.0, actual_turn_radius_m=6.0)
        assert result.method == "simplified_turn_radius_v1"
        assert any("오프트래킹" in lim or "시뮬레이션" in lim for lim in result.limitations)
        assert result.verified is False

    def test_parallel_angle_uses_lower_required_width(self):
        result = check_swept_path(parking_angle_deg=0, actual_aisle_width_m=3.2, actual_turn_radius_m=6.5)
        assert result.required_aisle_width_m == 3.0
        assert result.status == "pass"


# ══════════════════════════════════════════════════════════════════
# 5. verify_parking_plan — 종합 PASS/WARN/FAIL 판정
# ══════════════════════════════════════════════════════════════════

class TestVerifyParkingPlan:
    def test_all_missing_inputs_yields_warn_not_pass(self):
        """수용력·swept path 입력이 전혀 없으면 PASS를 주장하면 안 된다(가짜 pass 금지)."""
        result = verify_parking_plan(building_type="아파트", unit_count=10, planned_parking_count=10)
        assert result.verdict in (ParkingPlanVerdict.WARN, ParkingPlanVerdict.FAIL)
        assert result.limitations

    def test_full_pass_scenario(self):
        """요구대수 충족 + 면적 충분 + swept path 충족 → PASS."""
        result = verify_parking_plan(
            building_type="아파트",
            unit_count=10,
            planned_parking_count=10,
            available_layout_area_sqm=3000.0,
            actual_aisle_width_m=6.5,
            actual_turn_radius_m=6.5,
        )
        assert result.required_count == 10  # 10세대 × 1.0대/세대
        assert result.verdict == ParkingPlanVerdict.PASS

    def test_insufficient_planned_count_fails(self):
        result = verify_parking_plan(
            building_type="아파트",
            unit_count=100,
            planned_parking_count=10,  # 법정 요구(100대) 대비 크게 부족
            available_layout_area_sqm=3000.0,
            actual_aisle_width_m=6.5,
            actual_turn_radius_m=6.5,
        )
        assert result.verdict == ParkingPlanVerdict.FAIL
        assert any("법정 요구" in r for r in result.reasons)

    def test_area_too_small_for_planned_count_fails(self):
        """계획 대수가 법정은 충족해도, 주어진 면적에 물리적으로 안 들어가면 FAIL."""
        result = verify_parking_plan(
            building_type="아파트",
            unit_count=10,
            planned_parking_count=10,
            available_layout_area_sqm=50.0,  # 명백히 부족한 면적
            actual_aisle_width_m=6.5,
            actual_turn_radius_m=6.5,
        )
        assert result.verdict == ParkingPlanVerdict.FAIL
        assert result.layout is not None
        assert result.layout.estimated_capacity < 10

    def test_response_always_carries_basis_and_verified_false(self):
        """종합판정도 근거·가정·한계 3필드 + verified=False(1차 근사) 원칙 준수."""
        result = verify_parking_plan(
            building_type="아파트", unit_count=5, planned_parking_count=5,
        )
        assert result.basis
        assert result.verified is False
