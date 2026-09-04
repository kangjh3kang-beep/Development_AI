"""간략 수지 원장(실무 양식) — **검산이 진짜 위반을 지목하는가**.

## 왜 이 축들인가

락을 세 축으로 나눈다 — **탐지 · 특이도 · 배선**. 탐지만 잠그면 *"항상 ERROR 를 반환"* 하는
검산기가 **만점**을 받는다(그리고 전부 빨간 검사는 곧 꺼진다). 그래서 특이도 쪽의 핵심 단언은
*"위반을 내는가"* 가 아니라 **"고치면 사라지는가"** 로 쓴다.

## 픽스처가 계약보다 좁아지지 않게

손으로 만든 시나리오 dict 는 **실제 계약보다 좁아지기 쉽고**, 그러면 그 필드를 쓰는 코드가
테스트에서만 통과한다. 그래서 블록의 키를 오케스트레이터의 `_null_block` 에서 **파생**시켜
대조한다 — 엔진이 블록 모양을 바꾸면 여기가 먼저 빨개진다.
"""

from __future__ import annotations

import copy

import pytest

from app.services.feasibility.legacy_ledger import (
    CHECK_TOLERANCE_WON,
    HEADER_SPECS,
    build_header,
    build_legacy_ledger,
)
from app.services.feasibility.rough_feasibility_orchestrator import (
    _null_block,
    build_cost_ratio_basis,
    compact_charge_items,
    construction_breakdown,
)


# ── 픽스처 ───────────────────────────────────────────────────────────────
def _charge(code: str, name: str, amount: int, base: int | None, rate: float | None, **kw):
    d = {"code": code, "name": name, "amount_won": amount, "borne_by": "developer",
         "base_won": base, "rate": rate, "reason": None, "confidence": None}
    d.update(kw)
    return d


def _scenario() -> dict:
    """완전 시나리오 — 모든 축이 값을 가진 정상 사례."""
    charge_items = [
        _charge("B02", "학교용지부담금", 400_000_000, 100_000_000_000, 0.004),
        _charge("B03", "상수도 원인자부담금", 45_000_000, 300, 150_000),
        _charge("C07", "기반시설부담금", 0, 0, 0,
                reason="기반시설부담구역 미지정 — 미부과 (국토계획법 §67~69)"),
        # 수분양자 부담분 — 총사업비에 안 들어가므로 원장에서 **제외**돼야 한다.
        _charge("C01", "부가가치세", 9_000_000_000, 90_000_000_000, 0.1, borne_by="buyer"),
    ]
    developer_sum = 400_000_000 + 45_000_000 + 0
    return {
        # ★라이브 응답과 **같은 폭**으로 채운다(2026-08-26 실측 필드 기준).
        #   종전 픽스처는 두 필드뿐이라 제원 락이 대상 없이 통과할 뻔했다 — 오류 #111 과 같은
        #   형태(**픽스처가 현실보다 좁으면 그 필드를 쓰는 코드가 검사되지 않는다**).
        "inputs": {"land_area_sqm": 5_000.0, "gfa_sqm": 45_000.0,
                   "parcel_count": 1, "zone_type": "일반상업지역",
                   "effective_far_pct": 1300.0, "dev_type_name": "주상복합",
                   "total_households": 64, "project_months": 42,
                   "saleable_area_pyeong": 10_000.0},
        "land_cost": {"total_won": 60_000_000_000, "per_sqm_won": 12_000_000,
                      "basis": "탁상감정 적정단가 × 면적 + 취득세 등", "evidence": None,
                      "source": "desk_appraisal"},
        # ★단가는 **직접단가**다(`cc["direct"]["unit_cost_per_sqm"]`). 종전 픽스처는
        #   `45,000㎡ × 4,000,000 = 180억`(=총액)이라 **현실과 달랐고**, 그래서
        #   `수량 × 단가 = 금액` 단언이 통과했다 — **라이브에서는 재현되지 않았다**
        #   (실측: `6,573㎡ × 2.4e6 = 157.7억` vs 금액 `181.4억`).
        #   분해 후에는 직접 행이 **직접단가 × 연면적 = 직접공사비**로 정확히 맞는다.
        "construction_cost": {"total_won": 180_000_000_000, "unit_per_sqm_won": 3_000_000,
                              "basis": "국토부 기본형건축비 SSOT + 간접비 15%",
                              "source": "construction_cost_engine",
                              # ★직접/간접 분해 — 엔진이 total = direct + indirect 로 합산한다.
                              "direct_won": 135_000_000_000,   # 45,000㎡ × 3,000,000
                              "indirect": {
                                  "total_won": 45_000_000_000,
                                  "items": {"design_fee_won": 5_400_000_000,
                                            "supervision_fee_won": 4_050_000_000,
                                            "contingency_won": 10_800_000_000,
                                            "general_expense_won": 24_750_000_000},
                                  "ratios": {"design_fee": 0.04, "supervision_fee": 0.03,
                                             "contingency": 0.08, "general_expense": 0.05},
                                  "base_won": 135_000_000_000}},
        "revenue": {"total_won": 300_000_000_000, "sale_price_per_pyeong": 30_000_000,
                    "saleable_area_pyeong": 10_000.0,
                    "basis": "실거래 × 분양가능면적", "source": "molit"},
        "charges": {"total_won": developer_sum, "construction_stage_won": 445_000_000,
                    "sale_stage_won": 0, "buyer_borne_total_won": 9_000_000_000,
                    "items": charge_items, "basis": "B+C 단계", "source": "통합 세금엔진"},
        "cost_breakdown": {"land_won": 60_000_000_000, "construction_won": 180_000_000_000,
                           "finance_won": 12_000_000_000, "other_won": 8_000_000_000,
                           "charges_won": developer_sum,
                           # ★금융·제경비의 과표·비율 — 원장이 「수량 × 단가」를 재현하는 재료.
                           "ratio_basis": {"base_won": 240_000_000_000,
                                           "base_label": "토지비 + 공사비",
                                           "finance_rate": 0.05, "other_rate": 0.0333,
                                           "source": "engine", "note": None}},
        "summary": {"total_cost_won": 60_000_000_000 + 180_000_000_000 + 12_000_000_000
                    + 8_000_000_000 + developer_sum,
                    "total_revenue_won": 300_000_000_000,
                    "net_profit_won": 300_000_000_000
                    - (60_000_000_000 + 180_000_000_000 + 12_000_000_000
                       + 8_000_000_000 + developer_sum)},
    }


def _verdicts(led: dict) -> dict[str, str]:
    return {c["key"]: c["verdict"] for c in led["checks"]}


# ── 축 ⓪ 전제 — 픽스처가 실제 계약과 같은 모양인가 ──────────────────────────
@pytest.mark.parametrize(
    "kind,scenario_key",
    [("land", "land_cost"), ("construction", "construction_cost"),
     ("revenue", "revenue"), ("charges", "charges")],
)
def test_fixture_matches_engine_block_contract(kind: str, scenario_key: str):
    """★픽스처의 블록 키가 엔진의 표준 블록 키를 **전부** 담는다(스텁이 계약보다 좁으면 안 된다)."""
    contract = set(_null_block(kind).keys())
    assert contract, f"{kind}: 계약이 비었다 — 조회기가 죽었다"
    got = set(_scenario()[scenario_key].keys())
    missing = contract - got
    assert not missing, f"{scenario_key} 픽스처가 계약보다 좁다: {sorted(missing)}"


# ── 축 ① 탐지 — 검산이 진짜 위반을 지목하는가 ────────────────────────────────
def test_normal_scenario_all_checks_ok():
    """전제: 정상 시나리오에서 **모든 검산이 OK**(공허한 초록 방지 — 개수 하한도 본다)."""
    led = build_legacy_ledger(_scenario())
    assert len(led["checks"]) >= 4, "검산 항목이 줄었다"
    assert _verdicts(led) == {
        "revenue_total": "OK", "cost_total": "OK",
        "pretax_profit": "OK", "charges_items_vs_total": "OK",
    }


def test_dropped_charge_item_is_caught_and_restoring_it_clears():
    """★핵심 — 부담금 항목을 하나 흘리면 ERROR, **되돌리면 OK 로 돌아온다.**

    *"항상 ERROR"* 인 검산기는 이 두 번째 단언에서 죽는다. 그리고 이 검산은 **비자명**하다 —
    항목은 단계별 엔진에서, 총계는 통합 집계에서 와서 **서로 다른 경로**다.
    """
    broken = copy.deepcopy(_scenario())
    dropped = broken["charges"]["items"].pop(0)          # B02 400,000,000 을 흘린다
    assert dropped["amount_won"] > CHECK_TOLERANCE_WON, "흘린 항목이 0원이면 검산이 못 잡는 게 맞다"
    v = _verdicts(build_legacy_ledger(broken))
    assert v["charges_items_vs_total"] == "ERROR"

    broken["charges"]["items"].insert(0, dropped)        # 되돌린다
    assert _verdicts(build_legacy_ledger(broken))["charges_items_vs_total"] == "OK"


def test_engine_summary_drift_is_caught():
    """엔진 합계가 원장 합산과 어긋나면 ERROR — 원장이 **독립 합산**하기 때문에 잡힌다."""
    drifted = copy.deepcopy(_scenario())
    drifted["summary"]["total_cost_won"] += 1_000_000
    v = _verdicts(build_legacy_ledger(drifted))
    assert v["cost_total"] == "ERROR"
    assert v["revenue_total"] == "OK", "무관한 검산까지 빨개지면 특이도가 없다"


def test_buyer_borne_charge_is_excluded_from_ledger():
    """★수분양자 부담분(C01)은 원장에 실리지 않는다 — 실으면 지출 합계가 엔진과 갈린다."""
    led = build_legacy_ledger(_scenario())
    labels = [i["key"] for s in led["sections"] for g in s["groups"] for i in g["items"]]
    assert "charge_c01" not in labels
    assert "charge_b02" in labels, "대조군 — 시행사 부담분은 실려야 한다"


# ── 축 ② 특이도 — 무목업·판정불가 ────────────────────────────────────────────
def test_missing_value_is_none_not_zero():
    """★없는 값은 `None` 이고 `0` 이 아니다. `0` 은 「영 원」이라는 **주장**이다."""
    empty = build_legacy_ledger({})
    items = [i for s in empty["sections"] for g in s["groups"] for i in g["items"]]
    assert items, "빈 시나리오에서도 행 골격은 나와야 한다"
    assert all(i["amount_won"] is None for i in items), "미확보를 0 으로 만들었다"
    assert all(i["qty"] is None and i["unit_price"] is None for i in items)


def test_unknown_is_not_ok():
    """★판정 불가를 OK 로 접지 않는다 — 강등 시나리오가 「괜찮다」로 보이면 안 된다."""
    v = _verdicts(build_legacy_ledger({}))
    assert set(v.values()) == {"UNKNOWN"}, f"판정 불가가 OK 로 접혔다: {v}"


def test_none_input_does_not_raise():
    """부분 강등은 정상 입력이다 — 터지지 않고 UNKNOWN 을 낸다."""
    assert build_legacy_ledger(None)["coverage"]["items"] > 0


# ── 축 ③ 두 모집단 — 커버리지가 상수면 배선을 끊어도 통과한다 ─────────────────
def test_coverage_splits_two_populations():
    """★완전 시나리오와 강등 시나리오가 **다른 커버리지**를 낸다.

    두 값이 같으면 커버리지 배선을 통째로 끊어도 초록이다.
    """
    full = build_legacy_ledger(_scenario())["coverage"]
    degraded = build_legacy_ledger({})["coverage"]
    # ★행 수 자체가 다르다 — 부담금이 없으면 **부담금 행을 만들지 않는다**(빈 행은 0원으로 읽힌다).
    #   이 부등호가 그 설계를 잠근다: 빈 행을 만들기 시작하면 두 값이 같아져 빨개진다.
    assert full["items"] > degraded["items"], "부담금 없는 시나리오가 같은 행 수를 냈다 — 빈 행을 만들고 있다"
    assert full["with_qty"] > 0
    assert degraded["with_qty"] == 0, "값이 없는데 수량이 잡혔다"
    assert full["qty_pct"] != degraded["qty_pct"], "커버리지가 상수다 — 배선을 끊어도 통과한다"
    assert degraded["qty_pct"] == 0.0


def test_coverage_is_derived_from_items_not_hardcoded():
    """★래칫은 **산출에서 파생**한다 — 목록형이면 목록을 줄여 락을 끌 수 있다(#859 실증)."""
    led = build_legacy_ledger(_scenario())
    items = [i for s in led["sections"] for g in s["groups"] for i in g["items"]]
    cov = led["coverage"]
    assert cov["items"] == len(items)
    assert cov["with_qty"] == sum(1 for i in items if i["qty"] is not None)
    assert cov["with_unit_price"] == sum(1 for i in items if i["unit_price"] is not None)
    assert cov["with_basis"] == sum(1 for i in items if i["basis"])


def test_qty_and_unit_price_reproduce_the_amount():
    """★수량 × 단가 ≈ 금액 — 장식이 아니라 **실제 재료**임을 확인한다."""
    led = build_legacy_ledger(_scenario())
    by_key = {i["key"]: i for s in led["sections"] for g in s["groups"] for i in g["items"]}
    # ★`construction_direct` 는 **분해 후 직접공사비**다 — 직접단가 × 연면적으로 정확히 맞는다.
    #   분해 전(한 행)일 때는 단가가 직접단가인데 금액이 총액이라 **원리적으로 안 맞았다**.
    for key in ("sale_revenue", "land_acquisition", "construction_direct"):
        it = by_key[key]
        assert it["qty"] and it["unit_price"], f"{key}: 수량·단가가 비었다"
        assert abs(it["qty"] * it["unit_price"] - it["amount_won"]) < 1_000, (
            f"{key}: 수량×단가가 금액을 재현하지 못한다 — 표기가 장식이다"
        )


# ── 축 ④ 구성비 ─────────────────────────────────────────────────────────────
def test_share_pct_uses_revenue_and_is_absent_without_it():
    """구성비 분모는 매출 합계. 매출이 없으면 **0% 가 아니라 None** 이다."""
    led = build_legacy_ledger(_scenario())
    by_key = {i["key"]: i for s in led["sections"] for g in s["groups"] for i in g["items"]}
    assert by_key["sale_revenue"]["share_pct"] == 100.0
    assert by_key["land_acquisition"]["share_pct"] == pytest.approx(20.0, abs=0.01)
    assert all(
        i["share_pct"] is None
        for s in build_legacy_ledger({})["sections"] for g in s["groups"] for i in g["items"]
    )


# ── 축 ⑤ 래칫 — **우리가 지금 어디까지 답할 수 있는가**를 못 박는다 ──────────────
#   09_LEGACY(실무 원본)는 수량 91% · 단가 79% · 근거 100% 다. 우리는 그보다 항목이 적고
#   커버리지도 다르다. **숫자를 지어내 따라가지 않는다** — 대신 현재 수준을 하한으로 박아
#   흘리면 빨개지게 한다. 이 수치를 올리는 것이 다음 작업의 정의다.
# ★2026-08-27 하한 조정 100.0 → 91.7. **커버리지가 떨어진 것이 아니라, 셀 수 없는 것을
#   셀 수 있다고 하던 것을 그만둔 것**이다. B03 상수도는 과표 축이 **실비(원가계산)** 라
#   `과표 × 요율` 구조가 아니다(수도법 시행령 §65③) — 종전에는 **세대수를 과표로 실어**
#   커버리지 100% 를 만들고 있었다. 그 세대수는 **법정 과표가 아니었다.**
#   ★이 하한을 다시 올리려면 **그 항목의 과표를 실제로 관측**해야 한다(추측으로 채우지 말 것).
_QTY_PCT_FLOOR = 91.7
# ★2026-08-27 하한 조정 — B03 상수도는 **요율 축이 없다**(실비·원가계산, 수도법 시행령 §65③).
#   종전에는 출처 0건의 `원/세대` 단가를 실어 100% 를 만들고 있었다. 셀 수 없는 것을
#   셀 수 있다고 하던 것을 그만둔 것이지 커버리지가 나빠진 것이 아니다.
_UNIT_PRICE_PCT_FLOOR = 91.7
_BASIS_PCT_FLOOR = 100.0


def test_coverage_floor_is_a_ratchet():
    """★완전 시나리오의 커버리지가 하한 아래로 내려가면 실패한다.

    ★상한을 걸지 않는다 — 올라가는 것은 목표다. 다만 **근거는 100% 가 상한이자 하한**이다:
      모든 행이 *"왜 이 값인가"* 를 답해야 한다(못 답하면 그 행을 만들지 말아야 한다).
    """
    cov = build_legacy_ledger(_scenario())["coverage"]
    assert cov["items"] >= 7, f"행 수가 줄었다: {cov['items']}"
    assert cov["qty_pct"] >= _QTY_PCT_FLOOR, f"수량 커버리지 하락: {cov['qty_pct']}%"
    assert cov["unit_price_pct"] >= _UNIT_PRICE_PCT_FLOOR, f"단가 커버리지 하락: {cov['unit_price_pct']}%"
    assert cov["basis_pct"] == _BASIS_PCT_FLOOR, (
        f"근거 없는 행이 생겼다: {cov['basis_pct']}% — 근거를 못 대면 그 행을 만들지 말 것"
    )


def test_every_item_has_a_basis_even_when_degraded():
    """★강등 시나리오에서도 **근거는 남는다** — 금액이 없다고 이유까지 잃지 않는다.

    유료·비가역 산출물 규율 §4 — *"사유를 버리지 마라. 진단 불가는 그 자체로 장애다."*
    """
    for sc in ({}, _scenario()):
        led = build_legacy_ledger(sc)
        no_basis = [
            i["key"] for s in led["sections"] for g in s["groups"] for i in g["items"]
            if not i["basis"]
        ]
        assert not no_basis, f"근거 없는 행: {no_basis}"


def test_basis_kind_splits_data_from_structural():
    """★★「근거 100%」가 **폴백만으로** 채워지지 않게 — 두 모집단을 가른다.

    구조근거(`structural`)는 *"이 행이 무엇인가"* 만 답한다. 데이터근거(`data`)는
    *"이 값이 어디서 왔는가"* 를 답한다. 둘을 안 가르면 **엔진이 근거를 전혀 안 줘도**
    커버리지 100% 가 나와 래칫이 장식이 된다.
    """
    full = build_legacy_ledger(_scenario())
    degraded = build_legacy_ledger({})

    kinds = lambda led: [  # noqa: E731
        i["basis_kind"] for s in led["sections"] for g in s["groups"] for i in g["items"]
    ]
    full_data = sum(1 for k in kinds(full) if k == "data")
    degraded_data = sum(1 for k in kinds(degraded) if k == "data")

    assert full_data > 0, "완전 시나리오인데 데이터근거가 하나도 없다"
    assert degraded_data == 0, "엔진이 근거를 안 줬는데 데이터근거로 표기됐다"
    assert full_data != degraded_data, "근거 종류가 상수다 — 배선을 끊어도 통과한다"

    # 핵심 세 축은 완전 시나리오에서 **데이터근거**여야 한다(구조 폴백으로 때우면 안 된다).
    by_key = {i["key"]: i for s in full["sections"] for g in s["groups"] for i in g["items"]}
    for key in ("sale_revenue", "land_acquisition", "construction_direct"):
        assert by_key[key]["basis_kind"] == "data", f"{key}: 구조 폴백으로 때웠다"


# ── 축 ⑥ 상류 — **엔진이 준 과표·요율·사유를 압축이 버리지 않는가** ───────────────
#   ★변이 실증(2026-08-26): 이 축이 없을 때 `_compact` 가 `base_won` 을 다시 버리는 변이가
#     **SURVIVED** 했다. 원장 테스트의 픽스처가 그 값을 **이미 갖고** 있어서, 압축 층을
#     한 번도 태우지 않았기 때문이다 — 테스트가 스스로 생산자 역할을 한 형태다.
def _charges_result() -> dict:
    """단계별 세금엔진 산출 모양(과표·요율·사유·신뢰도를 **엔진이 준다**)."""
    return {
        "construction": {"items": [
            # ★B04(하수도)를 쓴다 — 이 축은 **법정 차원이 확정**돼 있다(오수발생량 ㎥/일 ×
            #   단위단가 원/㎥/일 · 하수도법 §61+시행령 §35 · 울산 조례 §24①4호).
            #   종전에는 B03 을 `base_won=300, rate=150_000`(=옛 `원/세대` 날조 형태)로 썼는데,
            #   B03 은 **축 자체가 미상**이라(실비·원가계산) 원장이 수량·단가를 싣지 않는다 —
            #   즉 이 테스트의 목적(**압축이 엔진의 과표·요율을 버리지 않는가**)을 태울 수 없다.
            {"code": "B04", "name": "하수도 원인자부담금", "amount_won": 60_000_000,
             "base_won": 30, "rate": 2_000_000, "borne_by": "developer"},
            {"code": "B01", "name": "광역교통시설부담금", "amount_won": None,
             "base_won": None, "rate": None, "confidence": "unavailable",
             "detail": {"reason": "표준건축비 미설정 — 산정 불가"}},
        ]},
        "sale": {"items": [
            {"code": "C01", "name": "부가가치세", "amount_won": 9_000_000_000,
             "base_won": 90_000_000_000, "rate": 0.1, "borne_by": "buyer"},
        ]},
    }


def test_compact_preserves_base_rate_and_reason():
    """★과표·요율·사유가 **살아서** 나온다 — 버리면 원장의 「수량×단가」가 통째로 죽는다."""
    out = {i["code"]: i for i in compact_charge_items(_charges_result())}
    assert out["B04"]["base_won"] == 30
    # ★압축은 엔진이 준 값을 만들지도 지우지도 않는다.
    assert out["B04"]["rate"] == 2_000_000
    assert out["B01"]["reason"] == "표준건축비 미설정 — 산정 불가"
    assert out["B01"]["confidence"] == "unavailable"


def test_compact_does_not_fabricate_missing_values():
    """★엔진이 안 준 것은 `None` 이다 — 0 이나 빈 문자열로 채우지 않는다(무목업)."""
    out = {i["code"]: i for i in compact_charge_items(_charges_result())}
    assert out["B01"]["base_won"] is None and out["B01"]["rate"] is None
    assert out["B01"]["amount_won"] is None
    # 대조군 — 준 것은 그대로 산다(전부 None 으로 만드는 구현이 통과하지 않게).
    assert out["C01"]["base_won"] == 90_000_000_000


def test_compact_output_feeds_the_ledger_end_to_end():
    """★★상류(압축) → 하류(원장)가 **실제로 이어진다** — 픽스처가 아니라 압축 산출로 원장을 만든다."""
    items = compact_charge_items(_charges_result())
    led = build_legacy_ledger({"charges": {"total_won": 45_000_000, "items": items}})
    by_key = {i["key"]: i for s in led["sections"] for g in s["groups"] for i in g["items"]}
    assert by_key["charge_b04"]["qty"] == 30, "압축이 과표를 흘렸다"
    assert by_key["charge_b04"]["qty_unit"] == "㎥/일"
    assert by_key["charge_b04"]["unit_price"] == 2_000_000, "압축이 요율을 흘렸다"
    assert "표준건축비 미설정" in (by_key["charge_b01"]["note"] or ""), "압축이 사유를 흘렸다"
    assert "charge_c01" not in by_key, "수분양자 부담분이 원장에 실렸다"


# ── 축 ⑦ **부분 결측** — 차단 1(적대 리뷰) ────────────────────────────────────
#   ★첫 구현은 `None` 부분합을 **필터로 버리고** 남은 것만 더했다. 공사비·부담금·금융비·
#     제경비가 전부 미확보인데 택지비만 있는 강등 시나리오에서 **세전이익 2,400억**이라는
#     완전한 허구가 나왔다(엔진은 `None`). 화면은 같은 카드에서 엔진의 `순이익 —` 과
#     원장의 `2,400억` 을 나란히 보이고 **큰 쪽이 더 권위 있어 보인다.**
#   ★기존 락은 `build_legacy_ledger({})`(**전부** 결측)만 태웠다 — 처방과 결함의 **범위가
#     달랐다**(§D20). 그래서 여기서 **세 모집단**을 가른다.
def _partial() -> dict:
    """오케스트레이터의 실제 강등 경로 재현 — 토지비·매출만 확보, 공사비 산출 실패."""
    return {
        "inputs": {"land_area_sqm": 5_000.0},
        "land_cost": {"total_won": 60_000_000_000, "per_sqm_won": 12_000_000,
                      "basis": "탁상감정", "evidence": None, "source": "desk"},
        "construction_cost": {},          # ← 산출 실패
        "revenue": {"total_won": 300_000_000_000, "sale_price_per_pyeong": 30_000_000,
                    "saleable_area_pyeong": 10_000.0, "basis": "실거래", "source": "molit"},
        "charges": {}, "cost_breakdown": {}, "summary": {},
    }


def test_partial_missing_does_not_fabricate_a_total():
    """★★하나라도 모르면 **합계도 모른다** — 택지비만 있는데 지출 합계를 내지 않는다."""
    led = build_legacy_ledger(_partial())
    by = {s["key"]: s for s in led["sections"]}
    assert by["cost"]["total_won"] is None, "축 4개가 미확보인데 지출 합계를 확정 숫자로 냈다"
    assert by["profit"]["total_won"] is None, "★세전이익을 지어냈다(적대 리뷰 차단 1)"
    prof = by["profit"]["groups"][0]["items"][0]
    assert prof["amount_won"] is None
    assert prof["share_pct"] is None, "허구 금액으로 구성비까지 그렸다"


def test_three_populations_split():
    """★세 모집단이 **서로 다른 결과**를 낸다 — 둘만 보면 부분 결측이 통과한다.

    전부 결측(None) · **부분 결측(None)** · 완전(숫자). 가운데가 이번에 뚫린 자리다.
    """
    empty = build_legacy_ledger({})
    partial = build_legacy_ledger(_partial())
    full = build_legacy_ledger(_scenario())
    cost = lambda led: next(s for s in led["sections"] if s["key"] == "cost")["total_won"]  # noqa: E731
    assert cost(empty) is None
    assert cost(partial) is None
    assert isinstance(cost(full), (int, float)) and cost(full) > 0, "완전 시나리오까지 None 이면 과잉이다"


def test_partial_missing_revenue_check_is_not_ok():
    """★부분 결측에서 **「검산 통과」로 보이지 않는다** — 옆의 허구를 신뢰하게 만든다."""
    v = {c["key"]: c["verdict"] for c in build_legacy_ledger(_partial())["checks"]}
    assert v["cost_total"] != "OK"
    assert v["pretax_profit"] != "OK"


def test_charges_zero_is_distinguished_from_charges_unknown():
    """★부담금 **0건(계산됨)** 과 **부담금 축 미확보**가 갈린다 — 중4.

    행이 있는데 금액이 전부 미산정이면 소계는 「모름」이고, 검산이 **0원으로 일치 OK** 라는
    거짓 초록을 내면 안 된다(한 응답 안에서 소계와 검산이 서로 다른 말을 하게 된다).
    """
    computed_zero = build_legacy_ledger({"charges": {"total_won": 0, "items": []}})
    g = next(g for s in computed_zero["sections"] for g in s["groups"] if g["key"] == "charges")
    assert g["subtotal_won"] == 0, "계산된 0 을 「모름」으로 강등했다"

    not_computed = build_legacy_ledger({})
    g2 = next(g for s in not_computed["sections"] for g in s["groups"] if g["key"] == "charges")
    assert g2["subtotal_won"] is None, "미확보를 0 으로 만들었다"

    # 행은 있는데 금액이 전부 None — 소계도 검산도 「모름」이어야 한다.
    unknown_rows = build_legacy_ledger({"charges": {"total_won": 0, "items": [
        {"code": "B03", "name": "상수도", "amount_won": None, "borne_by": "developer",
         "base_won": 300, "rate": None},
    ]}})
    g3 = next(g for s in unknown_rows["sections"] for g in s["groups"] if g["key"] == "charges")
    assert g3["subtotal_won"] is None
    v = {c["key"]: c["verdict"] for c in unknown_rows["checks"]}
    assert v["charges_items_vs_total"] == "UNKNOWN", "미산정 행을 0 으로 세어 거짓 OK 를 냈다"


# ── 축 ⑧ 부담금 단위 — 차단 2 ────────────────────────────────────────────────
def test_charge_units_are_not_all_won():
    """★★과표 단위가 코드마다 다르다 — 전부 「원」이라 쓰면 **없는 주장**이 화면에 나간다.

    실측: `base_won` 은 `int(total_gfa_sqm)`(㎡) · `total_households`(세대) ·
    `total_sale_amount_won`(원) 세 가지다. 「300원 과표 × 140,000 요율」은 존재하지 않는다.
    """
    led = build_legacy_ledger({"charges": {"total_won": 1, "items": [
        {"code": "B03", "name": "상수도", "amount_won": 45_000_000, "borne_by": "developer",
         "base_won": 300, "rate": 150_000},
        {"code": "B02", "name": "학교용지", "amount_won": 4_000_000, "borne_by": "developer",
         "base_won": 100_000_000_000, "rate": 0.004},
        {"code": "B01", "name": "광역교통", "amount_won": 1, "borne_by": "developer",
         "base_won": 45_000, "rate": 0.02},
    ]}})
    by = {i["key"]: i for s in led["sections"] for g in s["groups"] for i in g["items"]}
    # ★B03 은 축 미상이라 단위가 없다. **B04(하수도)** 가 법정 차원을 갖는 쪽이다.
    assert by["charge_b03"]["qty_unit"] is None, "축 미상인데 단위를 붙였다"
    assert by["charge_b02"]["qty_unit"] == "원"
    assert by["charge_b01"]["qty_unit"] == "㎡"
    # ★두 모집단 — 셋이 같은 라벨이면 파생을 끊어도 통과한다.
    units = {by[k]["qty_unit"] for k in ("charge_b01", "charge_b02", "charge_b03")}
    assert len(units) == 3, f"단위가 갈리지 않는다: {units}"


def test_unknown_charge_code_carries_no_qty_at_all():
    """★단위를 모르면 **수량·단가를 아예 싣지 않는다** — 거짓 라벨보다 공백이 낫다."""
    led = build_legacy_ledger({"charges": {"total_won": 1, "items": [
        {"code": "ZZ99", "name": "미지의 부담금", "amount_won": 1, "borne_by": "developer",
         "base_won": 999, "rate": 0.5},
    ]}})
    it = next(i for s in led["sections"] for g in s["groups"] for i in g["items"]
              if i["key"] == "charge_zz99")
    assert it["qty"] is None and it["qty_unit"] is None
    assert it["unit_price"] is None and it["unit_price_unit"] is None
    assert it["amount_won"] == 1, "금액까지 버리면 과잉이다(대조군)"


def test_qty_times_price_reproduces_amount_for_every_charge_row():
    """★수량×단가 재현을 **부담금 전수**로 확대 — 종전엔 세 행만 봤다(통과하는 모집단만 골랐다).

    비율형(`원 × 요율`)만 대상이다 — 단위형(세대·㎡)은 곱이 금액이 되는 것이 맞지만
    반올림·상한이 끼므로 여유를 둔다.
    """
    led = build_legacy_ledger({"charges": {"total_won": 1, "items": [
        {"code": "B02", "name": "학교용지", "amount_won": 400_000_000, "borne_by": "developer",
         "base_won": 100_000_000_000, "rate": 0.004},
        {"code": "B03", "name": "상수도", "amount_won": 45_000_000, "borne_by": "developer",
         "base_won": 300, "rate": 150_000},
    ]}})
    rows = [i for s in led["sections"] for g in s["groups"] for i in g["items"]
            if i["key"].startswith("charge_")]
    assert rows, "부담금 행이 없다 — 검사 전제가 깨졌다"
    for it in rows:
        if it["qty"] is None or it["unit_price"] is None:
            continue
        assert abs(it["qty"] * it["unit_price"] - it["amount_won"]) <= max(1, abs(it["amount_won"]) * 0.01), (
            f"{it['key']}: 수량×단가가 금액을 재현하지 못한다 — 표기가 장식이다"
        )


# ── 축 ⑨ 래칫의 **분모** — 적대 리뷰 중7 ─────────────────────────────────────
def test_coverage_denominator_excludes_rows_with_no_possible_qty():
    """★「수량이 원리적으로 없는 행」을 분모에서 뺀다 — 안 그러면 **정직한 행을 벌한다**.

    세전이익은 차액이라 수량·단가가 원래 없다. 그런 행이 분모에 있으면 계획서가 선언한
    다음 작업(「못 채우는 행을 채운다」)을 할수록 %가 내려가 래칫이 **반대 신호**를 준다.
    """
    led = build_legacy_ledger(_scenario())
    items = [i for s in led["sections"] for g in s["groups"] for i in g["items"]]
    cov = led["coverage"]
    na = [i for i in items if i["qty_applicable"]]
    assert cov["qty_applicable_items"] == len(na)
    assert cov["items"] > cov["qty_applicable_items"], (
        "분모가 전체 행과 같다 — 「수량이 원리적으로 없는 행」이 하나도 표시되지 않았다"
    )
    prof = next(i for i in items if i["key"] == "pretax_profit")
    assert prof["qty_applicable"] is False, "세전이익은 차액이라 수량이 원리적으로 없다"
    # ★근거는 **모든 행**이 대상이다(분모를 좁히면 근거 100% 가 헐거워진다).
    assert cov["basis_pct"] == 100.0


def test_finance_and_other_now_carry_qty_and_rate():
    """★★금융비·제경비가 **수량 × 단가**를 싣는다 — 「부재」가 아니라 안 실어 보낸 것이었다.

    과표 = 토지비+공사비, 단가 = 엔진 추출 비율. 재현되는지까지 본다.
    """
    by = {i["key"]: i for s in build_legacy_ledger(_scenario())["sections"]
          for g in s["groups"] for i in g["items"]}
    for key, rate in (("finance_cost", 0.05), ("other_cost", 0.0333)):
        it = by[key]
        assert it["qty"] == 240_000_000_000, f"{key}: 과표가 없다"
        assert it["unit_price"] == rate
        # ★단위는 「원」, 라벨은 별도 필드(2026-08-26 라이브 실측으로 갈랐다 — 종전엔
        #   라벨이 단위 자리에 있어 화면에 `19,027,218,768토지비 + 공사비` 로 나갔다).
        assert it["qty_unit"] == "원"
        assert it["qty_label"] == "토지비 + 공사비"
        assert abs(it["qty"] * it["unit_price"] - it["amount_won"]) <= abs(it["amount_won"]) * 0.02


def test_fallback_ratio_is_labelled_differently_from_engine_ratio():
    """★엔진 추출 비율과 **표준 폴백**을 화면이 구별한다 — 폴백이면 참고용이다(두 모집단)."""
    import copy
    fb = copy.deepcopy(_scenario())
    fb["cost_breakdown"]["ratio_basis"].update(
        {"source": "fallback", "note": "엔진 비율 추출 실패 — 표준 폴백비율 적용(참고용)"})
    eng = {i["key"]: i for s in build_legacy_ledger(_scenario())["sections"]
           for g in s["groups"] for i in g["items"]}["finance_cost"]
    fbi = {i["key"]: i for s in build_legacy_ledger(fb)["sections"]
           for g in s["groups"] for i in g["items"]}["finance_cost"]
    assert eng["basis_kind"] == "data", "엔진 추출인데 구조 폴백으로 표기됐다"
    assert fbi["basis_kind"] == "structural", "폴백 비율을 데이터근거처럼 표기했다"
    assert "폴백" in (fbi["note"] or ""), "폴백 사실이 화면에 안 실린다"
    assert eng["basis_kind"] != fbi["basis_kind"], "두 경우가 같게 보인다 — 배선을 끊어도 통과한다"


def test_no_ratio_basis_means_no_fabricated_qty():
    """★`ratio_basis` 가 없으면 수량·단가를 **만들지 않는다**(대조군: 금액은 그대로 산다)."""
    import copy
    no_rb = copy.deepcopy(_scenario())
    no_rb["cost_breakdown"].pop("ratio_basis")
    it = {i["key"]: i for s in build_legacy_ledger(no_rb)["sections"]
          for g in s["groups"] for i in g["items"]}["finance_cost"]
    assert it["qty"] is None and it["unit_price"] is None
    assert it["amount_won"] == 12_000_000_000


# ── 축 ⑩ 상류 — **오케스트레이터가 실제로 실어 보내는가** ─────────────────────
#   ★변이 실증: 이 축이 없을 때 `"ratio_basis": None` 변이가 **SURVIVED** 했다.
#     원장 픽스처가 그 dict 를 **이미 갖고** 있어서 상류를 한 번도 안 태웠기 때문이다 —
#     이 세션에서 **다섯 번째** 같은 형태다(테스트가 스스로 생산자).
def test_cost_ratio_basis_carries_source_and_rates():
    """★엔진 추출과 표준 폴백이 **다른 `source`** 를 낸다(두 모집단)."""
    eng = build_cost_ratio_basis(240_000_000_000, 0.05, 0.033, None)
    fb = build_cost_ratio_basis(240_000_000_000, 0.08, 0.04, "엔진 비율 추출 실패 — 표준 폴백")
    assert eng["source"] == "engine" and fb["source"] == "fallback"
    assert eng["source"] != fb["source"], "출처가 상수다 — 배선을 끊어도 통과한다"
    assert eng["base_won"] == 240_000_000_000 and eng["finance_rate"] == 0.05
    assert fb["note"], "폴백인데 사유가 없다 — 사용자가 참고용임을 알 길이 없다"
    assert eng["note"] is None


def test_cost_ratio_basis_feeds_the_ledger_end_to_end():
    """★★상류 산출을 **그대로** 원장에 먹여 「수량 × 단가」가 재현되는지 본다(픽스처 아님)."""
    rb = build_cost_ratio_basis(240_000_000_000, 0.05, 0.0333, None)
    led = build_legacy_ledger({"cost_breakdown": {
        "finance_won": 12_000_000_000, "other_won": 7_992_000_000, "ratio_basis": rb}})
    by = {i["key"]: i for s in led["sections"] for g in s["groups"] for i in g["items"]}
    fin = by["finance_cost"]
    assert fin["qty"] == 240_000_000_000, "상류가 과표를 흘렸다"
    assert fin["unit_price"] == 0.05, "상류가 비율을 흘렸다"
    assert abs(fin["qty"] * fin["unit_price"] - fin["amount_won"]) < 1_000
    assert fin["basis_kind"] == "data", "엔진 추출인데 구조 폴백으로 표기됐다"


# ── 축 ⑪ 단위 ≠ 라벨 — **라이브가 아니면 못 잡았다**(2026-08-26) ──────────────
#   실측: 화면에 **`19,027,218,768토지비 + 공사비 × 0.06737`** 이 나갔다.
#   `base_label`("토지비 + 공사비")을 `qty_unit` 으로 써서 **숫자에 라벨이 단위처럼 붙었다.**
#   단위는 `원`·`㎡`·`세대` 처럼 **수를 세는 말**이고, 라벨은 *"무엇의 수량인가"* 라
#   **다른 자리**에 있어야 한다.
#   ★합성 픽스처는 이 결함을 못 잡는다 — 값이 그럴듯해 보이기 때문이다. **표기 규약을 단언**한다.
# ★`㎥/일` 은 **복합 단위**다(체적/시간) — 라벨이 아니다.
#   하수도법 §61·시행령 §35 의 오수발생량 과표가 그 차원이다(2026-08-27 차원 교정).
_UNIT_VOCAB = {"원", "㎡", "세대", "평", "원(과표)", "㎥/일"}


def test_qty_unit_is_a_unit_not_a_label():
    """★★`qty_unit` 은 **수를 세는 말**이어야 한다 — 문장이 오면 화면이 깨진다."""
    led = build_legacy_ledger(_scenario())
    bad = []
    for sec in led["sections"]:
        for g in sec["groups"]:
            for i in g["items"]:
                u = i["qty_unit"]
                if u is None:
                    continue
                # ★**선언된 어휘를 먼저 본다.** 종전에는 연산기호 휴리스틱이 먼저라
                #   `㎥/일` 같은 **정당한 복합 단위**를 라벨로 오인해 막았다
                #   (가드의 위양성도 결함이다 — 정상 코드를 막으면 그 가드는 곧 꺼진다).
                if u in _UNIT_VOCAB:
                    continue
                # 어휘에 없는 것만 「라벨 냄새」로 판정한다 — 문장·연산식은 여전히 걸린다.
                if len(u) > 6 or any(ch in u for ch in " +-/×"):
                    bad.append(f"{i['key']}: qty_unit={u!r}")
                else:
                    bad.append(f"{i['key']}: 어휘에 없는 단위 {u!r} — 의도한 것이면 _UNIT_VOCAB 에 추가하라")
    assert not bad, "단위 자리에 라벨이 들어갔다(화면에 숫자와 붙어 나간다):\n" + "\n".join(bad)


def test_qty_label_carries_what_the_quantity_is():
    """★라벨은 **버리지 않고** 별도 필드로 산다 — 「무엇의 수량인가」는 읽는 사람에게 필요하다."""
    by = {i["key"]: i for s in build_legacy_ledger(_scenario())["sections"]
          for g in s["groups"] for i in g["items"]}
    fin = by["finance_cost"]
    assert fin["qty_unit"] == "원", f"단위가 원이 아니다: {fin['qty_unit']!r}"
    assert fin["qty_label"] == "토지비 + 공사비", "라벨을 잃었다"
    # ★두 모집단 — 라벨이 있는 행과 없는 행이 갈린다(전부 같은 값이면 배선을 끊어도 통과).
    land = by["land_acquisition"]
    assert land["qty_unit"] == "㎡" and land["qty_label"] is None
    assert fin["qty_label"] != land["qty_label"]


def test_qty_label_is_absent_when_qty_is():
    """★수량이 없으면 라벨도 없다 — 값 없는 자리에 설명만 남기지 않는다."""
    by = {i["key"]: i for s in build_legacy_ledger({})["sections"]
          for g in s["groups"] for i in g["items"]}
    assert all(i["qty"] is None and i["qty_label"] is None for i in by.values())


# ── 축 ⑫ 공사비 **분해** — 추가가 아니라 쪼갬(2026-08-26) ─────────────────────
#   ★`construction_cost_engine` 은 이미 `{design_fee_won, supervision_fee_won, contingency_won,
#     general_expense_won}` 를 **비율과 함께** 돌려주는데, 오케스트레이터가 총액과 ㎡단가
#     **두 숫자만** 남겼다. 원장이 「설계비·감리비·예비비」를 못 그린 이유가
#     *"엔진에 없어서"* 가 아니라 **경계에서 버려서**였다(형태 ① — 계산해 놓고 안 실어 보냄).
def test_construction_splits_into_direct_and_indirect():
    """★직접 + 간접 4항목으로 쪼개진다 — 실무 양식 이름으로."""
    by = {i["key"]: i for s in build_legacy_ledger(_scenario())["sections"]
          for g in s["groups"] for i in g["items"]}
    assert by["construction_direct"]["label"] == "직접공사비(본체)"
    for key, label in (("construction_design_fee", "설 계 비"),
                       ("construction_supervision_fee", "감 리 비"),
                       ("construction_contingency", "예비비"),
                       ("construction_general_expense", "일반관리비")):
        assert key in by, f"{label} 행이 없다"
        assert by[key]["label"] == label, f"{key}: 엔진 키가 그대로 화면에 나갔다"


def test_split_does_not_change_the_total():
    """★★**분해지 추가가 아니다** — 쪼개도 지출 합계가 변하지 않는다(검산이 확인한다).

    이 단언이 없으면 분해가 **이중계상**을 만들어도 초록이다.
    """
    led = build_legacy_ledger(_scenario())
    g = next(g for s in led["sections"] for g in s["groups"] if g["key"] == "construction")
    rows = [i["amount_won"] for i in g["items"]]
    assert g["subtotal_won"] == sum(rows)
    assert g["subtotal_won"] == 180_000_000_000, "공사비 소계가 엔진 총액과 달라졌다(이중계상)"
    assert {c["key"]: c["verdict"] for c in led["checks"]}["cost_total"] == "OK"


def test_indirect_rows_carry_rate_and_reproduce_the_amount():
    """★간접비 각 행이 **직접공사비 × 요율 = 금액**을 재현한다(표기가 장식이 아니다)."""
    by = {i["key"]: i for s in build_legacy_ledger(_scenario())["sections"]
          for g in s["groups"] for i in g["items"]}
    for key, rate in (("construction_design_fee", 0.04), ("construction_supervision_fee", 0.03)):
        it = by[key]
        assert it["unit_price"] == rate and it["qty"] == 135_000_000_000
        assert it["qty_unit"] == "원" and it["qty_label"] == "직접공사비"
        assert abs(it["qty"] * it["unit_price"] - it["amount_won"]) < 1_000


def test_two_populations_split_vs_unsplit():
    """★★분해가 없으면 **종전대로 한 행** — 무회귀(구버전 응답·강등 시나리오).

    두 경우가 같은 행 수를 내면 분기를 지워도 통과한다.
    """
    import copy
    no_split = copy.deepcopy(_scenario())
    no_split["construction_cost"].pop("direct_won")
    no_split["construction_cost"].pop("indirect")
    split_g = next(g for s in build_legacy_ledger(_scenario())["sections"]
                   for g in s["groups"] if g["key"] == "construction")
    plain_g = next(g for s in build_legacy_ledger(no_split)["sections"]
                   for g in s["groups"] if g["key"] == "construction")
    assert len(split_g["items"]) == 5
    assert len(plain_g["items"]) == 1, "분해가 없는데 쪼갰다"
    # ★합계는 **둘 다 같아야** 한다 — 분해가 값을 바꾸면 안 된다.
    assert split_g["subtotal_won"] == plain_g["subtotal_won"]


def test_unknown_indirect_key_is_not_dropped():
    """★표에 없는 간접비 항목도 **버리지 않는다** — 새 항목이 조용히 사라지지 않게."""
    import copy
    sc = copy.deepcopy(_scenario())
    sc["construction_cost"]["indirect"]["items"]["새로운항목_won"] = 1_000_000
    keys = [i["key"] for s in build_legacy_ledger(sc)["sections"]
            for g in s["groups"] for i in g["items"]]
    assert any("새로운항목" in k for k in keys), "모르는 간접비 항목을 버렸다"


def test_construction_breakdown_projects_the_engine_shape():
    """★★상류가 **엔진 산출을 그대로** 옮긴다 — 픽스처가 아니라 엔진 모양으로 태운다.

    ★변이 실증: 이 축이 없을 때 `"direct_won": None` 변이가 **SURVIVED** 했다.
      원장 픽스처가 분해를 **이미 갖고** 있어 상류를 한 번도 안 태웠기 때문이다 —
      이 세션 **일곱 번째** 같은 형태이고, 원인은 **세 번 연속** 인라인 dict 리터럴이다.
    """
    cc = {
        "direct": {"total_direct_cost_won": 135_000_000_000, "unit_cost_per_sqm": 3_000_000},
        "indirect": {"design_fee_won": 5_400_000_000, "supervision_fee_won": 4_050_000_000,
                     "total_indirect_cost_won": 9_450_000_000,
                     "ratios": {"design_fee": 0.04, "supervision_fee": 0.03}},
        "total_construction_cost_won": 144_450_000_000,
    }
    out = construction_breakdown(cc)
    assert out["direct_won"] == 135_000_000_000
    assert out["indirect"]["base_won"] == 135_000_000_000, "요율의 과표가 직접공사비가 아니다"
    assert set(out["indirect"]["items"]) == {"design_fee_won", "supervision_fee_won"}
    assert "total_indirect_cost_won" not in out["indirect"]["items"], "합계를 항목으로 실었다"
    assert out["indirect"]["ratios"]["design_fee"] == 0.04


def test_construction_breakdown_returns_nothing_when_absent():
    """★분해가 없으면 **키를 만들지 않는다** — 소비처가 종전대로 한 행을 그린다(무회귀).

    ★두 모집단 — 있음/없음이 **다른 결과**를 내야 한다(항상 dict 를 만드는 구현 배제).
    """
    assert construction_breakdown({}) == {}
    assert construction_breakdown({"direct": {"unit_cost_per_sqm": 1}}) == {}
    assert construction_breakdown({"direct": {"total_direct_cost_won": 1}}) == {}, "간접이 없는데 만들었다"


def test_construction_breakdown_keeps_unknown_items():
    """★엔진이 새 간접비를 내면 **골라내지 않고 옮긴다**(조용히 사라지지 않게)."""
    out = construction_breakdown({
        "direct": {"total_direct_cost_won": 100},
        "indirect": {"design_fee_won": 4, "미래항목_won": 7, "total_indirect_cost_won": 11},
    })
    assert "미래항목_won" in out["indirect"]["items"], "모르는 항목을 버렸다"


def test_breakdown_feeds_the_ledger_end_to_end():
    """★★상류 산출을 **그대로** 원장에 먹여 행이 나오는지 본다(픽스처 아님)."""
    cc = {
        "direct": {"total_direct_cost_won": 135_000_000_000, "unit_cost_per_sqm": 3_000_000},
        "indirect": {"design_fee_won": 5_400_000_000, "total_indirect_cost_won": 5_400_000_000,
                     "ratios": {"design_fee": 0.04}},
    }
    led = build_legacy_ledger({
        "inputs": {"gfa_sqm": 45_000.0},
        "construction_cost": {"total_won": 140_400_000_000, "unit_per_sqm_won": 3_000_000,
                              "basis": "국토부", "source": "engine", **construction_breakdown(cc)},
    })
    by = {i["key"]: i for s in led["sections"] for g in s["groups"] for i in g["items"]}
    assert by["construction_direct"]["amount_won"] == 135_000_000_000, "상류가 직접비를 흘렸다"
    assert by["construction_design_fee"]["label"] == "설 계 비"
    assert by["construction_design_fee"]["unit_price"] == 0.04, "상류가 요율을 흘렸다"


# ── 축 ⑬ 제원 블록 — 원본 양식의 **상단 절반**(2026-08-26) ────────────────────
#   ★표만 만들고 제원을 안 만들면 「구성」이 절반이다. 원본 상단은 사업명·면적·용도지역·
#     세대수·용적률·공사기간·단가·세전이익을 한눈에 보인다.
def _hdr(sc) -> dict:
    return {h["label"]: h for h in build_header(sc)}


def test_header_is_derived_from_specs_not_hand_listed():
    """★모집단이 `HEADER_SPECS` 에서 **파생**된다 — 손 목록이면 새 항목이 조용히 빠진다."""
    assert len(HEADER_SPECS) >= 10, "제원 명세가 줄었다"
    labels = {label for label, _, _ in HEADER_SPECS}
    got = set(_hdr(_scenario()))
    assert got <= labels, f"명세에 없는 라벨이 나왔다: {got - labels}"
    assert len(got) >= 8, f"완전 시나리오인데 제원이 너무 적다: {sorted(got)}"


def test_header_omits_rows_it_cannot_fill():
    """★★값이 없으면 **행을 만들지 않는다** — 빈 행은 화면에서 「0」이나 「미정」으로 읽힌다."""
    empty = build_header({})
    assert empty == [], f"빈 시나리오인데 제원 행을 만들었다: {empty}"
    # ★두 모집단 — 완전 시나리오는 여러 행이 나온다(항상 빈 목록을 내는 구현 배제).
    assert len(build_header(_scenario())) > 0


def test_header_carries_unit_and_numeric_flag():
    """★단위와 수치여부를 함께 싣는다 — 화면이 정렬·포맷을 결정할 수 있게."""
    h = _hdr(_scenario())
    assert h["사업면적"]["unit"] == "㎡" and h["사업면적"]["is_numeric"] is True
    assert h["용도지역"]["unit"] is None and h["용도지역"]["is_numeric"] is False
    # ★두 모집단 — 수치/문자가 갈린다(전부 True 인 구현 배제).
    assert h["사업면적"]["is_numeric"] != h["용도지역"]["is_numeric"]


def test_header_does_not_fabricate_zero():
    """★`0` 은 값이다 — 그 자체로는 빼지 않는다(무목업의 반대 방향도 지킨다)."""
    h = _hdr({"summary": {"net_profit_won": 0}})
    assert "세전이익" in h and h["세전이익"]["value"] == 0, "0 을 「없음」으로 취급했다"
    # 빈 문자열·None 은 뺀다.
    assert "사업지" not in _hdr({"address": "   "})


def test_header_is_in_the_ledger_response():
    """★배선 — 원장 응답에 실제로 실린다."""
    led = build_legacy_ledger(_scenario())
    assert led["header"], "제원이 응답에 없다"
    assert any(h["label"] == "용도지역" for h in led["header"])
