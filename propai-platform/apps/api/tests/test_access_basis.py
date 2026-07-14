"""접도·도로 기반(access_basis, WP-A P4) 판정 단위 테스트.

수용 게이트: "법정도로 근거 없는 PASS 0" — 법정 접도 근거(도로접면·도로폭·현황도로 인정)를
데이터로 확정할 수 없으면 종합 게이트가 PASS가 되지 않는다(REQUIRES_AUTHORITY_CONFIRMATION).
전건(15+) 픽스처는 지적도로/현황도로/막다른길(길이별 폭)/맹지/자루형/소방접근을 커버하고,
각 판정에 근거(evidence 트레이스 + verified 법령링크)를 부착함을 확인한다.

★fastapi 미의존(서비스·룰 직접 호출) — 시스템 파이썬으로 실행 가능(라우터 앱 import 없음).
"""
from __future__ import annotations

from app.services.access.access_basis_service import assess_access
from app.services.zoning import special_parcel as sp

# ── 공용 단언 헬퍼 ──────────────────────────────────────────────────────────

def _assert_state_has_evidence(state) -> None:
    """상태(legal/physical/emergency)의 모든 판정에 근거 트레이스가 부착됐는지 확인."""
    assert state.findings, f"{state.state}: 판정 요인 0 (근거 없는 빈 상태 금지)"
    assert state.evidence, f"{state.state}: evidence 트레이스 미부착"
    for item in state.evidence:
        assert item.get("label"), f"{state.state}: evidence label 누락"


def _assert_all_states_evidence(a) -> None:
    for state in (a.legal, a.physical, a.emergency):
        _assert_state_has_evidence(state)


# ── 1) 지적도로(법정 접도 충족/검토) ────────────────────────────────────────

def test_registered_road_sufficient_small_building_passes():
    """중로(12m)·소형 연면적·소방 특이 없음 → 접도요건 충족 → 법정 PASS·종합 PASS·POSSIBLE."""
    a = assess_access({"road_side": "중로", "road_width_m": 12, "planned_gfa_sqm": 800})
    assert a.legal.status == "PASS"
    assert a.gate == "PASS"
    assert a.access_developability == "POSSIBLE"
    # 법정 근거(건축법 §44) verified 링크 부착.
    keys = {r.get("key") for r in a.legal.legal_refs}
    assert "road_relation" in keys
    assert all(r.get("url_status") == "verified" for r in a.legal.legal_refs if r.get("key") == "road_relation")
    _assert_all_states_evidence(a)


def test_registered_road_large_building_meets_6m():
    """대형 연면적(≥2,000㎡)·소로(8m ≥ 요구 6m) → 충족 PASS."""
    a = assess_access({"road_side": "소로", "road_width_m": 8, "planned_gfa_sqm": 5000,
                       "fire_truck_access_width_m": 6})
    assert a.legal.status == "PASS"
    _assert_state_has_evidence(a.legal)


def test_registered_road_large_building_narrow_is_conditional():
    """대형 연면적·세로(가)(4m < 요구 6m) → 접도요건 검토 → CONDITIONAL(확정 PASS 아님)."""
    a = assess_access({"road_side": "세로(가)", "road_width_m": 4, "planned_gfa_sqm": 5000})
    assert a.legal.status in ("CONDITIONAL", "REQUIRES_AUTHORITY_CONFIRMATION")
    assert a.gate != "PASS"
    _assert_state_has_evidence(a.legal)


# ── 2) 맹지(도로 미접) ───────────────────────────────────────────────────────

def test_maengji_by_road_side_is_not_pass():
    """도로접면='맹지' → 법정 접도 미충족 → 종합 PASS 아님 + 맹지 요인 노출."""
    a = assess_access({"road_side": "맹지"})
    assert a.gate != "PASS"
    cats = [f.category for f in a.legal.findings]
    assert any("맹지" in c for c in cats)
    _assert_state_has_evidence(a.legal)


def test_maengji_by_road_contact_false_is_not_pass():
    """road_contact=False(도로 미접) → 물리적 접근 CONDITIONAL·종합 PASS 아님."""
    a = assess_access({"road_contact": False})
    assert a.gate != "PASS"
    assert a.physical.status in ("CONDITIONAL", "BLOCKED")
    _assert_all_states_evidence(a)


def test_zero_width_road_preserved_as_maengji():
    """도로폭 0(0폭 엣지) — falsy로 새지 않고 맹지로 보존 → PASS 아님."""
    a = assess_access({"road_width_m": 0})
    assert a.gate != "PASS"
    cats = [f.category for f in a.legal.findings]
    assert any("맹지" in c for c in cats)


# ── 3) 근거 전무 — "법정도로 근거 없는 PASS 0"의 핵심 ───────────────────────

def test_no_road_basis_never_passes():
    """도로 데이터 전무 → 법정 접도 근거 확정 불가 → REQUIRES_AUTHORITY_CONFIRMATION·TENTATIVE."""
    a = assess_access({})
    assert a.gate != "PASS"
    assert a.gate == "TENTATIVE"
    assert a.legal.status == "REQUIRES_AUTHORITY_CONFIRMATION"
    assert a.access_developability == "REQUIRES_AUTHORITY_CONFIRMATION"
    _assert_all_states_evidence(a)


def test_no_legal_basis_pass_zero_invariant():
    """불변식: 법정 접도 근거가 없는 어떤 입력도 종합 게이트 PASS가 될 수 없다."""
    no_basis_inputs = [
        {},
        {"road_type": "현황도로"},
        {"flag_lot": True},
        {"planned_gfa_sqm": 5000},
        {"road_abutting_zone": True},
    ]
    for data in no_basis_inputs:
        a = assess_access(data)
        assert a.gate != "PASS", f"법정도로 근거 없는 PASS 발생: {data}"


# ── 4) 막다른 도로(길이별 폭 — 건축법 시행령 §3-3) ──────────────────────────

def test_cul_de_sac_under_10m_needs_2m_met():
    """막다른 <10m(8m)·폭 2m → 필요 2m 충족 → CAUTION(사전확인)."""
    a = assess_access({"road_side": "세로(불)", "road_width_m": 2,
                       "dead_end_road": True, "dead_end_length_m": 8})
    cats = [f.category for f in a.legal.findings]
    assert any("막다른" in c for c in cats)
    dead = next(f for f in a.legal.findings if "막다른" in f.category)
    assert dead.developability == "CAUTION"


def test_cul_de_sac_10_to_35m_needs_3m_met():
    """막다른 10~35m(20m)·폭 3m → 필요 3m 충족 → CAUTION."""
    a = assess_access({"road_width_m": 3, "dead_end_road": True, "dead_end_length_m": 20})
    dead = next(f for f in a.legal.findings if "막다른" in f.category)
    assert dead.developability == "CAUTION"


def test_cul_de_sac_over_35m_needs_6m_shortfall():
    """막다른 ≥35m(40m)·폭 3m(<6m) → 미달 CONDITIONAL·종합 PASS 아님 + 시행령 §3-3 링크."""
    a = assess_access({"road_side": "세로(가)", "road_width_m": 3,
                       "dead_end_road": True, "dead_end_length_m": 40})
    dead = next(f for f in a.legal.findings if "막다른" in f.category)
    assert dead.developability == "CONDITIONAL"
    assert a.gate != "PASS"
    keys = {r.get("key") for r in a.legal.legal_refs}
    assert "road_structure_width" in keys  # 건축법 시행령 제3조의3 verified 링크


def test_cul_de_sac_eup_myeon_relaxed_to_4m():
    """막다른 ≥35m·읍·면(비도시)·폭 4m → 완화 기준 4m 충족 → CAUTION."""
    a = assess_access({"road_width_m": 4, "dead_end_road": True, "dead_end_length_m": 40,
                       "is_urban_area": False})
    dead = next(f for f in a.legal.findings if "막다른" in f.category)
    assert dead.developability == "CAUTION"


def test_cul_de_sac_unknown_length_requires_confirmation():
    """막다른 도로이나 길이 미상 → 필요 너비 확정 불가 → REQUIRES_AUTHORITY_CONFIRMATION."""
    r = sp._rule_by_cul_de_sac({"road_width_m": 3, "dead_end_road": True})
    assert r is not None
    assert r["developability"] == "REQUIRES_AUTHORITY_CONFIRMATION"


def test_cul_de_sac_no_signal_returns_none():
    """막다른 도로 신호가 없으면 룰 미발동(과탐 방지)."""
    assert sp._rule_by_cul_de_sac({"road_side": "중로", "road_width_m": 12}) is None


# ── 5) 자루형(旗竿) 대지 통로부 ─────────────────────────────────────────────

def test_flag_lot_narrow_corridor_conditional():
    """자루형 통로 1.5m(<2m 접도의무) → CONDITIONAL·물리 상태 PASS 아님."""
    a = assess_access({"road_side": "소로", "road_width_m": 8,
                       "flag_lot": True, "access_corridor_width_m": 1.5})
    flag = next(f for f in a.physical.findings if "자루" in f.category)
    assert flag.developability == "CONDITIONAL"
    assert a.physical.status != "PASS"
    _assert_state_has_evidence(a.physical)


def test_flag_lot_ok_corridor_still_needs_ordinance():
    """자루형 통로 3m(≥2m) → 접도의무 충족 추정이나 조례 확인 필요(CONDITIONAL)."""
    a = assess_access({"road_side": "소로", "road_width_m": 8,
                       "flag_lot": True, "access_corridor_width_m": 3})
    flag = next(f for f in a.physical.findings if "자루" in f.category)
    assert flag.developability == "CONDITIONAL"


def test_flag_lot_unknown_corridor_requires_confirmation():
    """자루형인데 통로폭 미상 → REQUIRES_AUTHORITY_CONFIRMATION."""
    a = assess_access({"road_side": "소로", "road_width_m": 8, "flag_lot": True})
    assert a.physical.status == "REQUIRES_AUTHORITY_CONFIRMATION"


# ── 6) 현황도로(사실상 도로) 인정 ───────────────────────────────────────────

def test_current_road_needs_recognition():
    """현황도로 → 건축법상 도로 인정 여부 확인 필요(CONDITIONAL) + 근거 부착."""
    a = assess_access({"road_side": "세로(가)", "road_width_m": 4, "is_current_road": True})
    cur = [f for f in a.physical.findings if "현황도로" in f.category]
    assert cur and cur[0].developability == "CONDITIONAL"
    _assert_state_has_evidence(a.physical)


# ── 7) 소방·응급·공사차량 접근 ──────────────────────────────────────────────

def test_emergency_large_building_unknown_width_requires_confirmation():
    """대형·고층(12층)·소방접근폭 미상 → emergency REQUIRES_AUTHORITY_CONFIRMATION·TENTATIVE."""
    a = assess_access({"road_side": "광대", "road_width_m": 25, "floors": 12})
    assert a.emergency.status == "REQUIRES_AUTHORITY_CONFIRMATION"
    assert a.gate == "TENTATIVE"
    _assert_state_has_evidence(a.emergency)


def test_emergency_narrow_fire_access_conditional():
    """소방차 접근폭 3m(<4m) → emergency CONDITIONAL."""
    a = assess_access({"road_side": "중로", "road_width_m": 12,
                       "fire_truck_access_width_m": 3, "planned_gfa_sqm": 800})
    fire = [f for f in a.emergency.findings if "소방" in f.category]
    assert fire and fire[0].developability == "CONDITIONAL"


def test_emergency_wide_fire_access_ok():
    """소방차 접근폭 6m·소형 → emergency 충족(CAUTION 이하)·종합 PASS."""
    a = assess_access({"road_side": "중로", "road_width_m": 12,
                       "fire_truck_access_width_m": 6, "planned_gfa_sqm": 800})
    assert a.emergency.status == "PASS"
    assert a.gate == "PASS"


def test_emergency_small_no_signal_is_possible():
    """소형·소방 신호 없음 → 소방 특이 없음(POSSIBLE — 과탐 방지)."""
    a = assess_access({"road_side": "중로", "road_width_m": 12, "planned_gfa_sqm": 500})
    assert a.emergency.developability == "POSSIBLE"
    # 그래도 정직 고지(근거 트레이스)는 부착.
    _assert_state_has_evidence(a.emergency)


# ── 8) 게이트 정책(REQUIRES_AUTHORITY_CONFIRMATION 잠정화) ───────────────────

def test_gate_policy_rac_maps_to_tentative_not_pass():
    """special_parcel.gate_decision: REQUIRES_AUTHORITY_CONFIRMATION → TENTATIVE(확정 PASS 금지)."""
    assert sp.gate_decision("REQUIRES_AUTHORITY_CONFIRMATION", "YES") == "TENTATIVE"
    assert sp.gate_decision("REQUIRES_AUTHORITY_CONFIRMATION", "CONDITIONAL") == "TENTATIVE"
    # tentative_marker가 전용 사유 문구를 반환(확정 아님).
    marker = sp.tentative_marker("REQUIRES_AUTHORITY_CONFIRMATION", "YES")
    assert "확정" in marker


# ── 9) 종합 계약(3상태·근거·정직 고지) ──────────────────────────────────────

def test_assessment_shape_and_honest_disclosure():
    """AccessAssessment 표준 shape(3상태·게이트·정직 고지·에코) 확인."""
    a = assess_access({"road_side": "중로", "road_width_m": 12, "planned_gfa_sqm": 800,
                       "fire_truck_access_width_m": 6, "address": "서울시 강남구 역삼동 1", "pnu": "1"})
    assert a.is_assessed is True
    assert a.legal.state == "legal" and a.physical.state == "physical" and a.emergency.state == "emergency"
    assert a.honest_disclosure
    assert a.echo.get("address") == "서울시 강남구 역삼동 1"
    assert a.gate in ("PASS", "TENTATIVE", "BLOCK")
