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
from app.services.feasibility.rough_feasibility_orchestrator import _null_block


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
                           "charges_won": developer_sum},
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
_QTY_PCT_FLOOR = 50.0
_UNIT_PRICE_PCT_FLOOR = 50.0
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
