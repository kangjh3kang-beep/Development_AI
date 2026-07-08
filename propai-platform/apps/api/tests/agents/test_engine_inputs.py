"""engine_inputs.py 공용 심의/설계 엔진 입력 빌더 — 순수함수 단위테스트(무 DB/네트워크).

★A2 핵심 계약: 엔진(services/deliberation-review permit_routes.py:39/design_routes.py:39)은
본문 최상위 `use_zone`만 읽는다(zone_type이 아니다). 이 테스트는 그 계약과 무날조(rules
additive-only) 가드를 잠근다.
"""
from __future__ import annotations

from app.services.agents.engine_inputs import (
    build_bcr_far_rules,
    build_deliberation_engine_input,
    build_design_engine_input,
)


def test_build_deliberation_engine_input_uses_use_zone_key():
    out = build_deliberation_engine_input(zone_type="일반상업지역", address="서울 중구")
    assert out["use_zone"] == "일반상업지역"
    assert "zone_type" not in out
    assert out["address"] == "서울 중구"
    assert out["pnu"] == ""  # 미제공 → 빈값(address 지오코딩 폴백)
    assert "dev_type" not in out  # 미제공 시 생략(additive)


def test_build_deliberation_engine_input_dev_type_and_pnu():
    out = build_deliberation_engine_input(
        zone_type="제2종일반주거지역", dev_type="M06", pnu="1168010100101230000")
    assert out["dev_type"] == "M06"
    assert out["pnu"] == "1168010100101230000"


def test_build_deliberation_engine_input_pnu_non_ascii_rejected():
    # 전각/유니코드 숫자 등 비19자리 ASCII는 빈값(엔진 422 대신 address 폴백).
    out = build_deliberation_engine_input(zone_type="z", pnu="１１６８０１０１００１０１２３０００")
    assert out["pnu"] == ""


def test_build_design_engine_input_uses_use_zone_and_calc_targets():
    out = build_design_engine_input(zone_type="일반상업지역", land_area_sqm=500.0)
    assert out["use_zone"] == "일반상업지역"
    assert "zone_type" not in out
    assert out["calc_targets"] == [{"target": "plot_area", "payload": {"parcel_area": 500.0}}]
    assert out["provided"] == {"program": True}


def test_build_design_engine_input_calc_targets_omitted_when_land_area_not_positive():
    """대지면적 미확보(0/None/음수)면 calc_targets 자체를 생략한다(가짜 0㎡ 미공급)."""
    for area in (0.0, None, -10.0):
        out = build_design_engine_input(zone_type="z", land_area_sqm=area)
        assert "calc_targets" not in out


def test_build_design_engine_input_proposed_gfa_and_dev_type():
    out = build_design_engine_input(
        zone_type="제2종일반주거지역", dev_type="M06", land_area_sqm=500.0, proposed_gfa_sqm=1000.0)
    assert out["dev_type"] == "M06"
    assert out["provided"] == {"program": True, "proposed_gfa": 1000.0}


def test_build_design_engine_input_rules_additive_only_when_both_present():
    """rules[]는 measured·limit이 둘 다 있을 때만 additive로 포함(무날조)."""
    out_no_rules = build_design_engine_input(zone_type="z", land_area_sqm=500.0)
    assert "rules" not in out_no_rules

    out_with_rules = build_design_engine_input(
        zone_type="z", land_area_sqm=500.0,
        bcr_measured=50.0, bcr_limit=60.0, far_measured=160.0, far_limit=200.0)
    assert out_with_rules["rules"] == [
        {"rule": {"rule_id": "BCR_LIMIT", "comparator": "<="}, "measured": 50.0, "limit": 60.0},
        {"rule": {"rule_id": "FAR_LIMIT", "comparator": "<="}, "measured": 160.0, "limit": 200.0},
    ]


def test_build_bcr_far_rules_partial_inputs_omit_that_rule():
    # BCR만 measured+limit 갖춰짐 → FAR rule은 생략(둘 다 없어서가 아니라 하나라도 없으면 생략).
    rules = build_bcr_far_rules(bcr_measured=50.0, bcr_limit=60.0, far_measured=None, far_limit=200.0)
    assert len(rules) == 1 and rules[0]["rule"]["rule_id"] == "BCR_LIMIT"

    assert build_bcr_far_rules() == []
