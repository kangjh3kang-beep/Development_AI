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


def test_build_helper_resolvable_zone_code_classifies_correctly():
    """㉔-b(WP-B 항목4 갱신) 축약코드('2R')는 이제 별칭표로 리졸브돼 정확히 판정된다.

    이전엔 '2R'이 분류 불가라 무조건 None(노이즈 회피)만 했으나, 이제 _resolve_zone_code_alias가
    '2R'→'제2종일반주거지역'으로 리졸브해 정확한 PASS(도시지역·형질변경 없음·비대상)를 반환한다
    (None으로 숨기는 대신 더 정확한 정보를 준다 — 노이즈 제거를 더 잘 달성).
    """
    gate = build_dev_act_permit_gate(zone_type="2R", area_sqm=1000)
    assert gate is not None
    assert gate["applicable"] is False
    assert gate["status"] == STATUS_PASS
    # 단, 한글 녹지명이면 그대로 정상 판정(FN 대상 보존).
    assert build_dev_act_permit_gate(zone_type="자연녹지지역", area_sqm=1000) is not None


def test_build_helper_opaque_zone_code_with_built_land_returns_none():
    """㉔-c(WP-B 항목4 신설) 별칭표에 없는 진짜 리졸브 불가 코드+형질변경 없음+지목'대'면
    불필요한 관할확인 게이트를 만들지 않는다(None — docstring 의도와 동작 일치화)."""
    assert build_dev_act_permit_gate(zone_type="ZZ9", land_category="대") is None


def test_build_helper_opaque_zone_code_with_non_built_land_still_confirms():
    """㉔-d(WP-B 항목4 FN0 보호) 리졸브 불가 코드라도 지목이 '대'가 아니면(임야 등 비도시
    가능성 있는 지목) 억제하지 않고 기존처럼 관할확인(CONFIRM) 게이트를 그대로 발동한다."""
    gate = build_dev_act_permit_gate(zone_type="ZZ9", land_category="임야")
    assert gate is not None
    assert gate["applicable"] == "UNKNOWN"
    assert gate["status"] == STATUS_CONFIRM


def test_build_helper_opaque_zone_code_with_form_change_still_gates():
    """㉔-e(WP-B 항목4 FN0 보호) 리졸브 불가 코드+지목'대'라도 형질변경 신호가 있으면
    비도시 가능성을 배제할 수 없어 억제하지 않고 정상 판정(CONDITIONAL)한다."""
    gate = build_dev_act_permit_gate(
        zone_type="ZZ9", land_category="대", land_form_change_required=True,
    )
    assert gate is not None
    assert gate["applicable"] is True
    assert gate["status"] == STATUS_CONDITIONAL
    assert gate["applicability_basis"] == "land_form_change"


def test_build_helper_green_zone_never_suppressed_by_built_land_guard():
    """㉔-f(WP-B 항목4 FN0 회귀 고정) 한글 녹지명이 정확히 오면(가장 흔한 실제 배선 경로),
    지목이 '대'여도 리졸브 자체가 성공(family≠None)하므로 항목4의 억제 분기에 진입하지 않고
    그대로 개발행위허가 대상(FN0 불변식)으로 판정된다."""
    gate = build_dev_act_permit_gate(zone_type="자연녹지지역", land_category="대", area_sqm=1000)
    assert gate is not None
    assert gate["applicable"] is True
    assert gate["status"] != STATUS_PASS


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
    # ★실효 단언(R2 지적 반영): zone(자연녹지)이 이겼다면 family="녹지"·CONDITIONAL이 됐을 것.
    assert gate["zone_family"] == "주거"
    assert gate["applicable"] is False
    assert gate["status"] == STATUS_PASS


# ── PR#282 리뷰 패스트팔로우: 프론트 실발행 코드(GC/QI) 리졸브 정합 ──────────


def test_build_helper_resolves_frontend_gc_code():
    """★리뷰 적발 회귀 고정 — 프론트 zoningToCode가 실제 발행하는 일반상업 코드는 'GC'다.
    (별칭표가 과거 'CC'만 알아 GC 리졸브가 무음 no-op이었음) 리졸브 후 도시 상업+대지는
    개발행위허가 비대상(PASS)으로 정확 판정돼야 한다."""
    gate = build_dev_act_permit_gate(zone_type="GC", land_category="대")
    assert gate is not None
    assert gate["applicable"] is False
    assert gate["status"] == STATUS_PASS


def test_build_helper_resolves_frontend_qi_code():
    """준공업 실발행 코드 'QI' 동일 회귀 고정(과거 'SI'만 인식)."""
    gate = build_dev_act_permit_gate(zone_type="QI", land_category="대")
    assert gate is not None
    assert gate["applicable"] is False
    assert gate["status"] == STATUS_PASS


# ══════════════════════════════════════════════════════════════════════════
# G. 접도 도로폭 출처(provenance) 표면화 — 표기사기 방지
#
# ★배경: road_width_m은 두 경로에서 나온다 — 지적 실측(land_info_service의 도로필지 MRR)과
#   '도로접면' 범주 대표값 환산(auto_zoning_service의 estimate_road_width_m: 광대로→40m 등).
#   종전엔 근거 문구가 "접도 도로폭 40m(≥4m)"로 동일해 **범주 추정이 실측으로 읽혔다**.
# ★★판정 오차는 **잔존**한다 — 이 꼬리표는 완화지 해결이 아니다(아래 회귀 핀으로 고정).
#   '세로(가)'는 기능 기준("차량통행 가능")이라 4m 하회 가능한데 대표값은 6.0이다.
# ══════════════════════════════════════════════════════════════════════════

def _road_basis(result: dict) -> str:
    """접도 기준 판정의 basis 문구만 뽑는다."""
    from app.services.permit.dev_act_permit_gate import _eval_infra_road

    return str(_eval_infra_road(result).get("basis") or "")


def test_road_width_estimate_source_is_disclosed_in_basis():
    """★범주 추정은 근거에 '도로접면 범주 추정'으로 명시된다(실측으로 오독 금지)."""
    basis = _road_basis({
        "road_contact": True, "road_width_m": 40.0,
        "road_width_source": "road_side_estimate",
    })
    assert "도로접면 범주 추정" in basis
    assert "40m" in basis
    # 꼬리표는 폭 값을 수식해야 한다 — 임계(≥4m)가 아니라.
    assert "40m(도로접면 범주 추정, ≥4m)" in basis


def test_sero_ga_estimate_can_overstate_met_known_residual_defect():
    """★★잔존 결함 고정 — '세로(가)' 추정(6.0)은 4m 하회 실도로를 MET로 과대판정한다.

    '세로(가)'는 치수가 아니라 기능 기준("차량통행 가능 소도로")이다 —
    tojieum_supplement._ROAD_WIDTH_BY_SIDE는 광대(25m↑)·중로(12~25m)·소로(8~12m)엔
    명시 범위를 주면서 세로(가)엔 범위 없이 "폭 약 4m"라고만 한다. 그런데
    land_info_service는 세로(가)를 6.0으로 환산하므로 폭 3.5m 골목이 MET가 된다.

    ★이 테스트는 '올바른 동작'이 아니라 **현행 결함을 명시적으로 고정**한다 —
      근본 수정(세로(가) CONFIRM 강등 또는 두 표 SSOT 통합) 시 여기서 실패해야 한다.
      최소한 근거에 '추정'이 드러나 하류가 실측으로 오독하지 않는 것이 현재 방어선이다.
    """
    basis = _road_basis({
        "road_contact": True, "road_width_m": 6.0,  # 세로(가) 대표값 — 실도로는 3.5m일 수 있다
        "road_width_source": "road_side_estimate",
    })
    assert "충족 추정" in basis          # 현행: MET (과대판정 잔존)
    assert "도로접면 범주 추정" in basis  # 방어선: 추정임이 근거에 드러남


def test_road_width_cadastral_source_is_disclosed_in_basis():
    """지적 실측은 '지적 실측'으로 명시 — 같은 폭이라도 신뢰도가 다르다."""
    basis = _road_basis({
        "road_contact": True, "road_width_m": 6.0,
        "road_width_source": "cadastral_road_parcel",
    })
    assert "지적 실측" in basis


def test_road_width_source_absent_keeps_legacy_basis():
    """출처 미상이면 꼬리표 없이 현행 문구 동일 — additive(무회귀)."""
    basis = _road_basis({"road_contact": True, "road_width_m": 6.0})
    assert basis == "접도 도로폭 6m(≥4m) — 건축법 제44조 접도요건 충족 추정"


def test_road_width_source_disclosed_on_narrow_road_too():
    """<4m(CONFIRM) 경로에도 출처가 붙는다 — MET만 고치면 반쪽."""
    basis = _road_basis({
        "road_contact": True, "road_width_m": 3.0,
        "road_width_source": "road_side_estimate",
    })
    assert "도로접면 범주 추정" in basis
    assert "<4m" in basis


def test_road_width_unknown_source_is_ignored_not_leaked():
    """미등록 출처 문자열은 꼬리표 없이 무시 — 원문 노출 금지(계약 밖 값 방어)."""
    basis = _road_basis({
        "road_contact": True, "road_width_m": 6.0,
        "road_width_source": "somethingelse",
    })
    assert "somethingelse" not in basis
    assert basis == "접도 도로폭 6m(≥4m) — 건축법 제44조 접도요건 충족 추정"


def test_build_helper_carries_road_width_source():
    """★build 헬퍼도 출처를 함께 싣는다 — 폭만 실으면 하류에서 무음 소실(R1 m2).

    현재 유일 호출자(design_v61)는 폭을 넘기지 않아 라이브 갭은 아니나,
    나중에 road_width_m=만 넘기면 근거가 추정을 실측처럼 표기하게 된다.
    """
    gate = build_dev_act_permit_gate(
        zone_type="자연녹지지역", land_category="임야",
        road_contact=True, road_width_m=40.0,
        road_width_source="road_side_estimate",
    )
    assert gate is not None
    road = gate["criteria"]["infrastructure_road"]
    assert "도로접면 범주 추정" in str(road.get("basis") or "")


def test_road_width_source_label_contract_is_closed():
    """★출처 어휘 계약 고정 — 생산자 2곳이 싣는 값과 1:1이어야 한다.

    생산자: land_info_service='cadastral_road_parcel'(지적 실측) /
            auto_zoning_service='road_side_estimate'(도로접면 범주 추정).
    새 출처를 추가하면서 라벨을 빠뜨리면 꼬리표가 조용히 사라지므로(무음 회귀)
    어휘를 여기서 닫아 동반 갱신을 강제한다.
    """
    from app.services.permit.dev_act_permit_gate import _ROAD_WIDTH_SOURCE_LABEL

    assert set(_ROAD_WIDTH_SOURCE_LABEL) == {"cadastral_road_parcel", "road_side_estimate"}
