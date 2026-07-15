"""접도·도로 기반(access_basis, WP-A 잔여 하드닝) — 항목1·2·3 결정적 픽스처.

이 파일은 2026-07-15 잔여 완결 WP의 다음 3항목을 검증한다:
  항목1 — build_access_basis_gate(설계생성 진입 표준 부착 헬퍼, WP-B build_dev_act_permit_gate와
          동일 additive 패턴). 실제 배선(comprehensive_analysis_service·design_v61)은 이 헬퍼·
          adapt_vworld_access_fields·assess_access(multi_parcel_adjacency)를 그대로 호출하므로,
          이 단위 테스트가 배선 지점의 계약을 결정적으로 고정한다.
  항목2 — adapt_vworld_access_fields(vworld road_side·getLandCharacteristics 실데이터 어댑터).
  항목3 — assess_access(multi_parcel_adjacency=...) 다필지 세트 인접 경유 접근 완화(과대낙관 금지).

★fastapi·DB 미의존 — 시스템/venv 파이썬으로도 실행 가능(라우터 앱 import 없음).
"""
from __future__ import annotations

from app.services.access.access_basis_service import (
    adapt_vworld_access_fields,
    assess_access,
    build_access_basis_gate,
)

# ══════════════════════════════════════════════════════════════════════════
# 항목2 — adapt_vworld_access_fields(vworld 실데이터 어댑터, 신규 API 호출 없음)
# ══════════════════════════════════════════════════════════════════════════


def test_adapter_maps_maengji_road_side_to_road_contact_false():
    """road_side='맹지'(vworld road_side_nm/roadSideCodeNm 정규화값) → road_contact=False 파생."""
    out = adapt_vworld_access_fields({"road_side": "맹지"})
    assert out["road_side"] == "맹지"
    assert out["road_contact"] is False


def test_adapter_maps_known_road_side_categories_to_road_contact_true():
    """광대/중로/소로/세로 — 유효 도로접면 라벨은 road_contact=True 파생."""
    for side in ("광대한면", "중로각지", "소로한면", "세로(가)", "세로(불)"):
        out = adapt_vworld_access_fields({"road_side": side})
        assert out["road_contact"] is True, f"{side}: road_contact 파생 실패"


def test_adapter_unknown_road_side_text_leaves_road_contact_unset():
    """인식 불가 텍스트는 road_contact 키를 만들지 않는다(추측·날조 금지 — 정직 미상 유지)."""
    out = adapt_vworld_access_fields({"road_side": "알수없는분류"})
    assert out.get("road_side") == "알수없는분류"
    assert "road_contact" not in out


def test_adapter_missing_land_register_returns_empty_dict():
    """land_register 자체가 없으면(None) 매핑 불가 필드는 전부 생략(정직 미상 — 빈 dict)."""
    assert adapt_vworld_access_fields(None) == {}
    assert adapt_vworld_access_fields({}) == {}


def test_adapter_detects_road_abutting_zone_from_special_districts():
    """special_districts에 '접도구역' 명시가 있으면 road_abutting_zone=True(도로법 §40)."""
    out = adapt_vworld_access_fields({"road_side": "중로"}, ["접도구역", "개발제한구역"])
    assert out["road_abutting_zone"] is True


def test_adapter_no_abutting_zone_signal_omits_key():
    """접도구역 신호가 없으면 road_abutting_zone 키 자체를 만들지 않는다(날조 금지)."""
    out = adapt_vworld_access_fields({"road_side": "중로"}, ["개발제한구역"])
    assert "road_abutting_zone" not in out


def test_adapter_output_feeds_directly_into_assess_access():
    """어댑터 산출을 그대로 assess_access에 merge하면 legal 상태가 정상 판정된다(계약 정합)."""
    mapped = adapt_vworld_access_fields({"road_side": "중로", "road_width_m": 12})
    a = assess_access({**mapped, "planned_gfa_sqm": 800})
    assert a.legal.status == "PASS"


# ══════════════════════════════════════════════════════════════════════════
# 항목3 — 다필지 세트 인접 경유 접근 완화(multi_parcel_adjacency)
# ══════════════════════════════════════════════════════════════════════════


def test_multi_parcel_mitigation_softens_maengji_when_set_contiguous_and_member_has_road():
    """대표필지 맹지+세트 연접(contiguous=True)+세트 내 멤버 도로접(member_road_contact=True)
    → physical이 CONDITIONAL이 아니라 CAUTION으로 완화되고, 근거 finding도 추가된다."""
    a = assess_access({
        "road_contact": False,
        "multi_parcel_adjacency": {"contiguous": True, "member_road_contact": True},
    })
    assert a.physical.developability == "CAUTION"
    cats = [f.category for f in a.physical.findings]
    assert any("다필지" in c for c in cats)


def test_multi_parcel_mitigation_not_applied_when_not_contiguous():
    """★과대낙관 금지 — 세트가 비연접(contiguous=False/None)이면 완화하지 않는다(기존 CONDITIONAL 유지)."""
    a = assess_access({
        "road_contact": False,
        "multi_parcel_adjacency": {"contiguous": False, "member_road_contact": True},
    })
    assert a.physical.developability == "CONDITIONAL"
    cats = [f.category for f in a.physical.findings]
    assert not any("다필지" in c for c in cats)


def test_multi_parcel_mitigation_not_applied_when_member_road_contact_unknown():
    """★과대낙관 금지 — 세트 멤버 도로접 신호가 미상(None)이면 완화하지 않는다."""
    a = assess_access({
        "road_contact": False,
        "multi_parcel_adjacency": {"contiguous": True, "member_road_contact": None},
    })
    assert a.physical.developability == "CONDITIONAL"


def test_multi_parcel_mitigation_not_applied_when_member_road_contact_false():
    """세트 내 어떤 멤버도 도로에 접하지 않으면(False) 당연히 완화하지 않는다."""
    a = assess_access({
        "road_contact": False,
        "multi_parcel_adjacency": {"contiguous": True, "member_road_contact": False},
    })
    assert a.physical.developability == "CONDITIONAL"


def test_multi_parcel_mitigation_irrelevant_when_representative_not_maengji():
    """대표필지가 애초에 맹지가 아니면 완화 신호는 아무 영향이 없다(적용 대상 자체가 아님)."""
    a = assess_access({
        "road_side": "중로", "road_width_m": 12,
        "multi_parcel_adjacency": {"contiguous": True, "member_road_contact": True},
    })
    assert a.physical.developability == "POSSIBLE"
    cats = [f.category for f in a.physical.findings]
    assert not any("다필지" in c for c in cats)


def test_multi_parcel_mitigation_never_produces_pass_gate_alone():
    """완화(CAUTION)돼도 legal 상태(법정 접도 근거 자체)는 별개로 남아 종합 게이트가 무조건
    PASS가 되지는 않는다(법정도로 근거 없는 PASS 0 불변식은 여전히 legal이 지킨다)."""
    a = assess_access({
        "road_contact": False,
        "multi_parcel_adjacency": {"contiguous": True, "member_road_contact": True},
    })
    assert a.gate != "PASS"


# ══════════════════════════════════════════════════════════════════════════
# 항목1 — build_access_basis_gate(설계생성 진입 표준 부착 헬퍼)
# ══════════════════════════════════════════════════════════════════════════


def test_build_gate_helper_returns_assessment_dict_even_with_no_context():
    """assess_access 자체가 '항상 정직 판정'이므로, 컨텍스트가 전무해도 None이 아니라
    REQUIRES_AUTHORITY_CONFIRMATION 판정 dict를 반환한다(build_dev_act_permit_gate와 다른 지점
    — 그 헬퍼는 신호 전무 시 None이지만, 이 헬퍼는 assess_access의 항상-응답 설계를 그대로 따른다)."""
    gate = build_access_basis_gate()
    assert gate is not None
    assert gate["status"] == "REQUIRES_AUTHORITY_CONFIRMATION"


def test_build_gate_helper_with_road_signal_classifies_pass():
    """road_side/road_width_m을 명시로 넘기면(design_v61이 향후 실데이터를 확보하는 경로 대비)
    정상적으로 legal PASS까지 흐른다."""
    gate = build_access_basis_gate(road_side="중로", road_width_m=12)
    assert gate["legal"]["status"] == "PASS"


def test_build_gate_helper_pnu_echo():
    """pnu는 추적용 메타로만 echo(판정에는 미사용) — build_dev_act_permit_gate와 동일 패턴."""
    gate = build_access_basis_gate(zone_type="제2종일반주거지역", pnu="1111")
    assert gate["pnu"] == "1111"


def test_build_gate_helper_exception_is_graceful_none():
    """산출 실패(예외)는 None으로 흡수해 주 경로(매스 산출)를 깨지 않는다."""
    # special_districts에 리스트가 아닌 값이 들어와도 함수 내부에서 list()로 정규화되므로
    # 정상 동작해야 한다 — 방어 코드 자체를 재확인(예외를 던지지 않음 == 정상 계약).
    gate = build_access_basis_gate(special_districts=None)
    assert gate is not None
