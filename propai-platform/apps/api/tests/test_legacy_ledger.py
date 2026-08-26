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
    build_legacy_ledger,
)
from app.services.feasibility.rough_feasibility_orchestrator import (
    _null_block,
    build_cost_ratio_basis,
    compact_charge_items,
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
        "inputs": {"land_area_sqm": 5_000.0, "gfa_sqm": 45_000.0},
        "land_cost": {"total_won": 60_000_000_000, "per_sqm_won": 12_000_000,
                      "basis": "탁상감정 적정단가 × 면적 + 취득세 등", "evidence": None,
                      "source": "desk_appraisal"},
        "construction_cost": {"total_won": 180_000_000_000, "unit_per_sqm_won": 4_000_000,
                              "basis": "국토부 기본형건축비 SSOT + 간접비 15%",
                              "source": "construction_cost_engine"},
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
_QTY_PCT_FLOOR = 100.0   # ★실측 8/8 — 금융·제경비를 항목화해 66.7 → 100 으로 올렸다
_UNIT_PRICE_PCT_FLOOR = 100.0
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
            {"code": "B03", "name": "상수도 원인자부담금", "amount_won": 45_000_000,
             "base_won": 300, "rate": 150_000, "borne_by": "developer"},
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
    assert out["B03"]["base_won"] == 300
    assert out["B03"]["rate"] == 150_000
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
    assert by_key["charge_b03"]["qty"] == 300, "압축이 과표를 흘렸다"
    assert by_key["charge_b03"]["unit_price"] == 150_000, "압축이 요율을 흘렸다"
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
    assert by["charge_b03"]["qty_unit"] == "세대", "세대수를 「원」이라 불렀다"
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
_UNIT_VOCAB = {"원", "㎡", "세대", "평", "원(과표)"}


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
                # 단위는 짧고, 공백·연산기호를 포함하지 않는다.
                if len(u) > 6 or any(ch in u for ch in " +-/×"):
                    bad.append(f"{i['key']}: qty_unit={u!r}")
                elif u not in _UNIT_VOCAB:
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
