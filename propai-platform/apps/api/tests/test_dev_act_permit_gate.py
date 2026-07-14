"""WP-B: 개발행위허가 절차게이트(국토계획법 §56~58) — 결정적 픽스처 TDD.

핵심 수용 게이트(계획서 §4 WP-B):
  ★"허가대상인데 미고지" False-Negative 0 (P0급) — 개발행위허가 '대상'(applicable=True)인
    필지는 절대 PASS로 반환되지 않는다. 자연녹지 등 비도시·녹지 지역 케이스 중심.
  ★판정 근거 전건 evidence 부착. 조례·데이터 부재 시 정직 강등(REQUIRES_AUTHORITY_CONFIRMATION
    또는 CONDITIONAL+미확정 사유) — 낙관 폴백 금지.

무목업: 라이브 외부 API 호출 없이 결정적 입력으로만 검증한다.
"""
from app.services.permit.dev_act_permit_gate import (
    STATUS_BLOCKED,
    STATUS_CONDITIONAL,
    STATUS_CONFIRM,
    STATUS_PASS,
    assess_dev_act_permit,
    build_dev_act_permit_gate,
)

# 개발행위허가 '대상'인 상위 status(절대 PASS 아님).
_APPLICABLE_STATUSES = {STATUS_CONDITIONAL, STATUS_BLOCKED, STATUS_CONFIRM}


def _assert_has_evidence(gate: dict) -> None:
    """판정에 evidence(근거+법령링크)가 부착됐는지 — 전건 evidence 계약."""
    assert "evidence" in gate, "evidence 블록 부재"
    ev = gate["evidence"]
    assert isinstance(ev.get("evidence"), list) and ev["evidence"], "근거 항목 비어있음"
    refs = ev.get("legal_refs") or []
    keys = {r.get("key") for r in refs}
    # §56 개발행위허가·§58 기준은 항상 부착.
    assert "dev_act_permit" in keys, "국토계획법 §56 법령링크 부재"
    assert "dev_act_criteria" in keys, "국토계획법 §58 법령링크 부재"


# ══════════════════════════════════════════════════════════════════════════
# A. FN 0 — 개발행위허가 대상(녹지·비도시)은 절대 PASS 금지 (P0급)
# ══════════════════════════════════════════════════════════════════════════

def test_fn0_natural_green_zone_not_pass():
    """① 자연녹지 107㎡(메모리상 과대낙관 버그의 근본 케이스) — 대상, PASS 금지."""
    gate = assess_dev_act_permit({"zone_type": "자연녹지지역", "area_sqm": 107})
    assert gate is not None
    assert gate["applicable"] is True
    assert gate["status"] != STATUS_PASS, "★자연녹지가 PASS로 오고지되면 안 됨(FN)"
    assert gate["status"] == STATUS_CONDITIONAL
    _assert_has_evidence(gate)


def test_fn0_production_green_zone_not_pass():
    """② 생산녹지 — 대상 CONDITIONAL."""
    gate = assess_dev_act_permit({"zone_type": "생산녹지지역", "area_sqm": 800})
    assert gate["applicable"] is True
    assert gate["status"] == STATUS_CONDITIONAL


def test_fn0_conservation_green_zone_not_pass():
    """③ 보전녹지 — 대상, 원칙적 제한(PRECONDITION)이나 규모 이내면 CONDITIONAL(강한 사유)."""
    gate = assess_dev_act_permit({"zone_type": "보전녹지지역", "area_sqm": 300})
    assert gate["applicable"] is True
    assert gate["status"] in _APPLICABLE_STATUSES
    assert gate["developability"] == "PRECONDITION"
    assert any("보전" in n for n in gate["honest_notes"]), "보전 성격 정직 고지 부재"


def test_fn0_planning_management_zone_not_pass():
    """④ 계획관리지역(비도시) — 건축 자체가 개발행위허가 대상 → CONDITIONAL, PASS 금지."""
    gate = assess_dev_act_permit({"zone_type": "계획관리지역", "area_sqm": 500})
    assert gate["applicable"] is True
    assert gate["status"] != STATUS_PASS
    assert gate["status"] == STATUS_CONDITIONAL
    assert gate["applicability_basis"] == "zone"


def test_fn0_agro_forest_zone_not_pass():
    """⑤ 농림지역(비도시) — 대상 CONDITIONAL."""
    gate = assess_dev_act_permit({"zone_type": "농림지역", "area_sqm": 2000})
    assert gate["applicable"] is True
    assert gate["status"] != STATUS_PASS


def test_fn0_natural_env_conservation_zone_not_pass():
    """⑥ 자연환경보전지역(비도시) — 보전 성격 PRECONDITION, PASS 금지."""
    gate = assess_dev_act_permit({"zone_type": "자연환경보전지역", "area_sqm": 300})
    assert gate["applicable"] is True
    assert gate["status"] != STATUS_PASS
    assert gate["developability"] == "PRECONDITION"


def test_fn0_all_target_zones_sweep_never_pass():
    """⑦ 대상 용도지역 전수 스윕 — 어느 것도 PASS로 새지 않는다(FN 0 회귀 방어)."""
    target_zones = [
        "자연녹지지역", "생산녹지지역", "보전녹지지역", "녹지지역",
        "계획관리지역", "생산관리지역", "보전관리지역", "관리지역",
        "농림지역", "자연환경보전지역",
    ]
    for z in target_zones:
        gate = assess_dev_act_permit({"zone_type": z, "area_sqm": 1500})
        assert gate is not None, f"{z}: 게이트 미산출"
        assert gate["applicable"] is True, f"{z}: 대상 판정 실패(FN 위험)"
        assert gate["status"] in _APPLICABLE_STATUSES, f"★{z}: PASS로 오고지(FN)"
        _assert_has_evidence(gate)


# ══════════════════════════════════════════════════════════════════════════
# B. PASS — 개발행위허가 비대상(도시지역 대지, 형질변경 없음)은 정직 PASS
# ══════════════════════════════════════════════════════════════════════════

def test_urban_residential_built_land_pass():
    """⑧ 제2종일반주거지역 대지, 형질변경 없음 — 건축허가로 처리(PASS·비대상)."""
    gate = assess_dev_act_permit({"zone_type": "제2종일반주거지역", "land_category": "대"})
    assert gate["applicable"] is False
    assert gate["status"] == STATUS_PASS
    assert gate["applicability_basis"] == "urban_built"


def test_urban_commercial_built_land_pass():
    """⑨ 일반상업지역 대지 — 비대상 PASS."""
    gate = assess_dev_act_permit({"zone_type": "일반상업지역", "land_category": "대"})
    assert gate["status"] == STATUS_PASS


def test_urban_with_land_form_change_is_applicable():
    """⑩ 도시지역이라도 형질변경(절토·성토) 수반 시 개발행위허가 대상 → PASS 금지."""
    gate = assess_dev_act_permit({
        "zone_type": "제2종일반주거지역", "land_category": "대",
        "land_form_change_required": True,
    })
    assert gate["applicable"] is True
    assert gate["status"] == STATUS_CONDITIONAL
    assert gate["applicability_basis"] == "land_form_change"


# ══════════════════════════════════════════════════════════════════════════
# C. 정직 강등 — 조례·데이터 부재 시 REQUIRES_AUTHORITY_CONFIRMATION / 미확정 사유
# ══════════════════════════════════════════════════════════════════════════

def test_unknown_zone_requires_authority_confirmation():
    """⑪ 용도지역 미상(분류 불가)+지목만 — 낙관 폴백 금지, 관할 확인 강등."""
    gate = assess_dev_act_permit({"zone_type": "미분류특수지역", "land_category": "대"})
    assert gate["applicable"] == "UNKNOWN"
    assert gate["status"] == STATUS_CONFIRM
    assert any("미확정" in n or "낙관" in n for n in gate["honest_notes"])


def test_empty_input_returns_none():
    """⑫ 입력 전무(용도지역·지목·형질변경 신호 전무) — 판정 불가 정직 생략(None)."""
    assert assess_dev_act_permit({}) is None


def test_missing_data_criteria_are_unresolved_not_optimistic():
    """⑬ 자연녹지, 면적·경사·하수 미상 — 각 기준이 UNKNOWN/CONFIRM으로 정직 강등(낙관 금지)."""
    gate = assess_dev_act_permit({"zone_type": "자연녹지지역"})
    cr = gate["criteria"]
    assert cr["slope"]["status"] == "UNKNOWN", "경사도 데이터 미상인데 확정 판정됨(낙관)"
    assert cr["infrastructure_sewer"]["status"] == "UNKNOWN"
    # 미확정 기준을 honest_notes에 정직 집계.
    assert any("확정 판정하지 못" in n for n in gate["honest_notes"])


# ══════════════════════════════════════════════════════════════════════════
# D. BLOCKED — 보전 성격 + 규모 국가상한 초과(시행령 §55)는 단일 개발행위허가로 불가
# ══════════════════════════════════════════════════════════════════════════

def test_preservation_zone_over_scale_cap_blocked():
    """⑭ 자연환경보전지역 40,000㎡(국가상한 5천㎡ 초과) — BLOCKED."""
    gate = assess_dev_act_permit({"zone_type": "자연환경보전지역", "area_sqm": 40_000})
    assert gate["status"] == STATUS_BLOCKED
    assert gate["criteria"]["scale"]["status"] == "EXCEEDS"


def test_conservation_green_over_scale_cap_blocked():
    """⑮ 보전녹지 6,000㎡(국가상한 5천㎡ 초과) — BLOCKED."""
    gate = assess_dev_act_permit({"zone_type": "보전녹지지역", "area_sqm": 6_000})
    assert gate["status"] == STATUS_BLOCKED


def test_ordinance_scale_limit_takes_priority():
    """⑯ 조례 규모 상한 주입 시 국가상한보다 우선 — 초과면 EXCEEDS."""
    gate = assess_dev_act_permit(
        {"zone_type": "계획관리지역", "area_sqm": 12_000},
        scale_limit_sqm=10_000,
    )
    assert gate["criteria"]["scale"]["status"] == "EXCEEDS"
    assert gate["criteria"]["scale"]["limit_sqm"] == 10_000


# ══════════════════════════════════════════════════════════════════════════
# E. 기반시설(도로·상하수) 세분 판정
# ══════════════════════════════════════════════════════════════════════════

def test_infra_road_landlocked_not_met():
    """⑰ 맹지(도로 미접) — 접도요건 미충족(NOT_MET)·road_relation 법령링크 부착."""
    gate = assess_dev_act_permit({
        "zone_type": "계획관리지역", "area_sqm": 1000, "road_contact": False,
    })
    assert gate["criteria"]["infrastructure_road"]["status"] == "NOT_MET"
    keys = {r.get("key") for r in gate["evidence"]["legal_refs"]}
    assert "road_relation" in keys


def test_infra_road_width_satisfied():
    """⑱ 6m 도로 접함 — 접도요건 충족(MET)."""
    gate = assess_dev_act_permit({
        "zone_type": "계획관리지역", "area_sqm": 1000, "road_width_m": 6,
    })
    assert gate["criteria"]["infrastructure_road"]["status"] == "MET"


def test_infra_road_narrow_confirm():
    """⑲ 3m 도로(<4m) — 현황도로 인정·확폭 확인 필요(CONFIRM)."""
    gate = assess_dev_act_permit({
        "zone_type": "계획관리지역", "area_sqm": 1000, "road_width_m": 3,
    })
    assert gate["criteria"]["infrastructure_road"]["status"] == "CONFIRM"


def test_infra_sewer_outside_service_area_confirm():
    """⑳ 하수처리구역 밖 — 개인하수처리시설 선행(CONFIRM)."""
    gate = assess_dev_act_permit({
        "zone_type": "계획관리지역", "area_sqm": 1000, "in_sewer_service_area": False,
    })
    assert gate["criteria"]["infrastructure_sewer"]["status"] == "CONFIRM"


# ══════════════════════════════════════════════════════════════════════════
# F. 경사도(예비판정 — 확정 아님, 절대 hard-block 금지) — special_parcel 재사용
# ══════════════════════════════════════════════════════════════════════════

def test_slope_preliminary_never_blocks():
    """㉑ DEM 급경사(예비 초과)라도 상위 status는 hard-block(BLOCKED) 아님 — 예비 참고."""
    gate = assess_dev_act_permit(
        {"zone_type": "자연녹지지역", "area_sqm": 500},
        terrain_facts={"평균경사도_pct": 80.0, "source": "SRTM30_DEM"},
    )
    # 경사 예비판정은 초과여도 BLOCKED로 승격되지 않는다(확정은 공식조사로만).
    assert gate["status"] == STATUS_CONDITIONAL
    slope = gate["criteria"]["slope"]
    assert slope["status"] == "EXCEEDS"
    assert "예비" in slope["basis"], "경사도는 예비판정(확정 아님)으로 정직 표기해야 함"


def test_slope_uses_ordinance_criteria_when_present():
    """㉒ 조례 경사도 기준(T2) 주입 시 그 기준으로 예비판정."""
    gate = assess_dev_act_permit(
        {"zone_type": "계획관리지역", "area_sqm": 500},
        terrain_facts={"평균경사도_pct": 30.0, "source": "SRTM30_DEM"},
        slope_criteria={"slope_deg": 17.5, "ordinance_name": "OO시 도시계획 조례",
                        "verified": "api_parsed"},
    )
    slope = gate["criteria"]["slope"]
    assert slope["preliminary"]["criteria_deg"] == 17.5


# ══════════════════════════════════════════════════════════════════════════
# G. build_dev_act_permit_gate(설계경로 부착 헬퍼) + 재사용 요인 동봉
# ══════════════════════════════════════════════════════════════════════════

def test_build_helper_green_zone():
    """㉓ 설계경로 헬퍼 — 자연녹지 부착 산출(대상·CONDITIONAL·pnu echo)."""
    gate = build_dev_act_permit_gate(zone_type="자연녹지지역", area_sqm=800, pnu="1111")
    assert gate is not None
    assert gate["applicable"] is True
    assert gate["status"] == STATUS_CONDITIONAL
    assert gate["pnu"] == "1111"


def test_build_helper_no_context_returns_none():
    """㉔ 컨텍스트 전무면 None(정직 생략)."""
    assert build_dev_act_permit_gate() is None


def test_build_helper_opaque_zone_code_returns_none():
    """㉔-b 설계경로 노이즈 방어 — 분류 불가 축약코드('2R')만이면 None(관할확인 게이트 미생성)."""
    assert build_dev_act_permit_gate(zone_type="2R", area_sqm=1000) is None
    # 단, 한글 녹지명이면 정상 판정(FN 대상 보존).
    assert build_dev_act_permit_gate(zone_type="자연녹지지역", area_sqm=1000) is not None


def test_reused_base_factor_embedded():
    """㉕ 재사용한 발동 요인(_rule_by_dev_act_permit)이 base_factor로 동봉 — 전역 패리티."""
    gate = assess_dev_act_permit({"zone_type": "자연녹지지역", "area_sqm": 500})
    assert "base_factor" in gate
    bf = gate["base_factor"]
    assert bf["legal_ref_keys"] == ["dev_act_permit", "dev_act_criteria", "land_form_change"]
    assert bf["developability"] == "CONDITIONAL"


# ── 리뷰 반영 회귀: zone/zone_type 키계약 비대칭 → 게이트 누락(FN) 방지 ──────────


def test_zone_key_only_still_gated_fn_regression():
    """★리뷰 적발 FN 재현 고정 — zone 키만 채워진 입력(scenario_simulator comp 폴백 형태)도
    게이트가 반드시 발동해야 한다(zone_type 부재로 조용히 None 반환 금지)."""
    gate = assess_dev_act_permit({"zone": "자연녹지지역", "zone_type": "", "land_category": ""})
    assert gate is not None, "zone 키만 있는 자연녹지 입력에서 게이트 누락(FN)"
    assert gate["applicable"] is True
    assert gate["status"] in _APPLICABLE_STATUSES  # 절대 PASS 아님
    _assert_has_evidence(gate)


def test_zone_type_takes_precedence_over_zone():
    """zone_type이 있으면 zone은 무시(기존 계약 유지) — 관용은 폴백일 뿐 우선순위 불변."""
    gate = assess_dev_act_permit({"zone_type": "제2종일반주거지역", "zone": "자연녹지지역",
                                  "land_category": "대"})
    assert gate is not None
    assert gate["zone_family"] not in ("green", "management")
