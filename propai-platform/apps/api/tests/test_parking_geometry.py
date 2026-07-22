"""주차 기하 실현 가능성 검증 계약(스펙 P — W3-5) 단위 테스트.

app.services.parking 패키지: StallSpec·AisleSpec(치수 SSOT) · estimate_layout_capacity
(면적→수용력 1차 추정) · check_swept_path(swept path 1차 근사) · verify_parking_plan
(종합 PASS/WARN/FAIL)을 검증한다.

★법정 주차대수 산정(값) 자체는 이 테스트의 대상이 아니다 — 그 SSOT는
app.services.permit.building_code_rules.PARKING_REQUIREMENTS이며, 여기서는
verify_parking_plan이 그 값을 "재사용"하는지(중복 계산 없이 동일 결과를 내는지)만
교차검증한다.

★R1 리뷰 봉합(W3-5 R2): HIGH-1(각도 역전 수용력 과대) 회귀방지 앵커를 이 파일에
추가한다. 기대값은 구현 출력을 복붙한 것이 아니라, 스펙에 정의된 삼각함수 산식을
별도 스크래치 계산(hand calc)으로 독립 도출한 값이다:
  module(θ) = (width/sinθ) × (length·sinθ + width·cosθ + aisle(θ)/2)   [θ≠0]
  module(0) = (length+0.6) × (width + aisle(0)/2)                       [평행 전용]
"""

from __future__ import annotations

import math

import pytest

from app.services.parking import (
    AISLE_SPECS,
    PHYSICAL_MIN_MODULE_AREA_SQM,
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
# 1. StallSpec/AisleSpec — 치수 SSOT(주차장법 시행규칙 §3·제6조제1항) 고정값
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
        """★R1 MEDIUM-1 교정: 평행주차 차로 너비는 3.0m가 아니라 3.3m다."""
        assert AISLE_SPECS[90].aisle_width_m == 6.0
        assert AISLE_SPECS[60].aisle_width_m == 4.5
        assert AISLE_SPECS[45].aisle_width_m == 3.5
        assert AISLE_SPECS[0].aisle_width_m == 3.3  # 평행주차(R1 교정: 3.0→3.3)

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

    def test_default_deduction_total_is_25_pct(self):
        """★R1 MEDIUM-2: 공제율 합계 20%→25%(램프10·기둥8·코어7) 보수화."""
        result = estimate_layout_capacity(gross_area_sqm=1000)
        assert result.deduction_ratio_total == pytest.approx(0.25)

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
# 3b. ★R1 HIGH-1 회귀방지 — 각형 유효기하(각도 역전 버그 봉합)
# ══════════════════════════════════════════════════════════════════

class TestAngleAwareModuleGeometryRegressionLock:
    """리뷰어 실증 버그: 이전 산식은 45°가 90°보다 더 조밀하게(+18.5%) 들어간다고
    계산했다(물리적으로 불가능 — 직각주차가 항상 가장 효율적). 이 클래스는 방향과
    독립 손계산(hand calc) 값을 모두 고정한다.
    """

    def test_90deg_general_module_area_is_exact_20(self):
        """90°는 sin=1·cos=0으로 옛 공식과 대수적으로 완전히 동일 — 부동소수 오차 외 정확히 20.0."""
        result = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=StallType.GENERAL, parking_angle_deg=90,
        )
        assert result.module_area_per_stall_sqm == pytest.approx(20.0, abs=1e-6)

    def test_60deg_general_module_area_hand_calc(self):
        """손계산: pitch=2.5/sin60=2.8868, depth=5*sin60+2.5*cos60=5.5801,
        module=2.8868*(5.5801+4.5/2)=22.60."""
        result = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=StallType.GENERAL, parking_angle_deg=60,
        )
        assert result.module_area_per_stall_sqm == pytest.approx(22.60, abs=0.01)

    def test_45deg_general_module_area_hand_calc(self):
        """손계산: pitch=2.5/sin45=3.5355, depth=5*sin45+2.5*cos45=5.3033,
        module=3.5355*(5.3033+3.5/2)=24.94."""
        result = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=StallType.GENERAL, parking_angle_deg=45,
        )
        assert result.module_area_per_stall_sqm == pytest.approx(24.94, abs=0.01)

    def test_direction_locked_90_lt_60_lt_45_module_area(self):
        """★핵심 방향 고정: 각도가 얕아질수록(90→60→45) 1대당 유효면적은 반드시 증가해야
        한다(=같은 면적에서 수용대수는 감소해야 함) — 역전되면 즉시 실패."""
        m90 = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=StallType.GENERAL, parking_angle_deg=90,
        )
        m60 = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=StallType.GENERAL, parking_angle_deg=60,
        )
        m45 = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=StallType.GENERAL, parking_angle_deg=45,
        )
        assert m90.module_area_per_stall_sqm < m60.module_area_per_stall_sqm < m45.module_area_per_stall_sqm
        assert m90.estimated_capacity > m60.estimated_capacity > m45.estimated_capacity

    def test_parallel_module_area_hand_calc(self):
        """손계산: pitch=6.0+0.6=6.6, depth=2.0, module=6.6*(2.0+3.3/2)=24.09."""
        result = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=StallType.PARALLEL, parking_angle_deg=0,
        )
        assert result.module_area_per_stall_sqm == pytest.approx(24.09, abs=0.01)

    @pytest.mark.parametrize(
        ("stall_type", "angle"),
        [
            (StallType.GENERAL, 90), (StallType.GENERAL, 60), (StallType.GENERAL, 45),
            (StallType.EXPANDED, 90), (StallType.EXPANDED, 60), (StallType.EXPANDED, 45),
            (StallType.DISABLED, 90),
            (StallType.PARALLEL, 0),
        ],
    )
    def test_module_area_never_below_physical_floor(self, stall_type, angle):
        """모든 (구획유형, 각도) 조합에서 1대당 유효면적이 물리 하한(20㎡/대) 아래로
        떨어지면 산식 결함(리뷰어가 발견한 18.76㎡/대 같은 불가능 밀도)이다."""
        result = estimate_layout_capacity(
            gross_area_sqm=100_000, stall_type=stall_type, parking_angle_deg=angle,
        )
        assert result.module_area_per_stall_sqm >= PHYSICAL_MIN_MODULE_AREA_SQM

    def test_stall_angle_mismatch_general_with_parallel_angle_warns(self):
        """구획유형=일반형인데 각도=0(평행)이면 불일치 경고가 limitations에 남아야 한다."""
        result = estimate_layout_capacity(
            gross_area_sqm=3000, stall_type=StallType.GENERAL, parking_angle_deg=0,
        )
        assert any("불일치" in lim for lim in result.limitations)

    def test_stall_angle_mismatch_parallel_with_90_warns(self):
        """구획유형=평행형인데 각도=90(직각)이면 반대방향 불일치도 잡아야 한다."""
        result = estimate_layout_capacity(
            gross_area_sqm=3000, stall_type=StallType.PARALLEL, parking_angle_deg=90,
        )
        assert any("불일치" in lim for lim in result.limitations)

    def test_consistent_combo_has_no_mismatch_warning(self):
        """정합 조합(일반형+90°)은 불일치 경고가 없어야 한다."""
        result = estimate_layout_capacity(
            gross_area_sqm=3000, stall_type=StallType.GENERAL, parking_angle_deg=90,
        )
        assert not any("불일치" in lim for lim in result.limitations)

    def test_unregistered_angle_falls_back_to_90_with_assumption_note(self):
        """미등록 각도(예: 30°)는 90° 기준으로 폴백하고 그 사실을 assumptions에 남긴다."""
        result = estimate_layout_capacity(
            gross_area_sqm=3000, stall_type=StallType.GENERAL, parking_angle_deg=30,
        )
        assert any("미지원 각도" in a and "90" in a for a in result.assumptions)
        # 폴백 후 실제로 90° 차로폭(6.0m)이 적용됐는지도 함께 확인(90° 결과와 module 일치).
        fallback_module = result.module_area_per_stall_sqm
        direct_90_module = estimate_layout_capacity(
            gross_area_sqm=3000, stall_type=StallType.GENERAL, parking_angle_deg=90,
        ).module_area_per_stall_sqm
        assert fallback_module == pytest.approx(direct_90_module)


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

    def test_parallel_angle_uses_updated_required_width(self):
        """★R1 MEDIUM-1: 평행주차 차로 너비 기준은 3.3m(3.0m 아님)."""
        result = check_swept_path(
            parking_angle_deg=0, actual_aisle_width_m=3.5, actual_turn_radius_m=6.5,
        )
        assert result.required_aisle_width_m == 3.3
        assert result.status == "pass"

    def test_parallel_angle_below_new_331_threshold_fails(self):
        """3.0~3.3m 사이 값은 옛 기준(3.0)으로는 pass였지만 새 기준(3.3)으로는 fail이어야 한다."""
        result = check_swept_path(
            parking_angle_deg=0, actual_aisle_width_m=3.1, actual_turn_radius_m=6.5,
        )
        assert result.status == "fail"
        assert result.aisle_width_ok is False


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
        """요구대수 충족 + 면적 충분(여유 밴드 내) + swept path 충족 → PASS."""
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
        # capacity = floor(3000*0.75/20.0) = 112, margin = 10/112 ≈ 0.0893(≤0.85 → PASS 밴드)
        assert result.capacity_margin_ratio == pytest.approx(10 / 112, abs=1e-3)
        assert result.capacity_warn_threshold_ratio == pytest.approx(0.85)

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

    def test_partial_swept_input_yields_warn_not_hard_fail(self):
        """★R1 HIGH-2 회귀방지 핵심: aisle폭만 입력(회전반경 미입력)해도 하드 FAIL로
        접히면 안 된다 — reasons가 '부분 검증만 수행'이라 말해놓고 verdict를 FAIL로
        강제하는 자기 계약 위반을 봉쇄한다. 다른 조건(대수·면적)은 모두 충족 상태로 고정."""
        result = verify_parking_plan(
            building_type="아파트",
            unit_count=10,
            planned_parking_count=10,
            available_layout_area_sqm=3000.0,  # 여유 충분(PASS 밴드)
            actual_aisle_width_m=6.5,          # 차로폭만 입력
            actual_turn_radius_m=None,          # 회전반경 미입력 → swept "warn"
        )
        assert result.swept_path is not None
        assert result.swept_path.status == "warn"
        assert result.verdict == ParkingPlanVerdict.WARN  # FAIL이면 회귀

    def test_radius_only_partial_swept_also_yields_warn(self):
        """대칭 케이스: 회전반경만 입력(차로폭 미입력)해도 동일하게 WARN이어야 한다."""
        result = verify_parking_plan(
            building_type="아파트",
            unit_count=10,
            planned_parking_count=10,
            available_layout_area_sqm=3000.0,
            actual_aisle_width_m=None,
            actual_turn_radius_m=6.5,
        )
        assert result.swept_path is not None
        assert result.swept_path.status == "warn"
        assert result.verdict == ParkingPlanVerdict.WARN

    def test_layout_boundary_band_is_warn_not_fail(self):
        """★R1 MEDIUM-2 회귀방지: 마진비율이 0.85~1.0 경계 구간이면 WARN(정밀 배치도
        필요)이어야 하며 FAIL로 과도하게 엄격 판정하면 안 된다.

        손계산: area=1000, 공제25% → usable=750, module@90(GENERAL)=20.0 →
        capacity=floor(750/20)=37. planned=34 → margin=34/37≈0.9189(0.85~1.0 경계).
        """
        result = verify_parking_plan(
            building_type="아파트",
            unit_count=34,
            planned_parking_count=34,
            available_layout_area_sqm=1000.0,
            actual_aisle_width_m=6.5,
            actual_turn_radius_m=6.5,
        )
        assert result.layout is not None
        assert result.layout.estimated_capacity == 37
        assert result.capacity_margin_ratio == pytest.approx(34 / 37, abs=1e-3)
        assert 0.85 < result.capacity_margin_ratio <= 1.0
        assert result.verdict == ParkingPlanVerdict.WARN  # FAIL이면 회귀(과도 엄격)

    def test_layout_within_pass_band_margin_ratio_exposed(self):
        """마진비율(capacity_margin_ratio)은 결과 필드로 항상 정직 노출되어야 한다."""
        result = verify_parking_plan(
            building_type="아파트",
            unit_count=5,
            planned_parking_count=5,
            available_layout_area_sqm=1000.0,
            actual_aisle_width_m=6.5,
            actual_turn_radius_m=6.5,
        )
        assert result.capacity_margin_ratio is not None
        assert result.capacity_margin_ratio == pytest.approx(5 / 37, abs=1e-3)
