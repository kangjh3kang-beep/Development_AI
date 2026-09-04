"""부담금 과표·요율 **단위표**가 엔진과 어긋나지 않는가.

## 왜 (2026-08-26 적대 리뷰 차단)

항목 dict 의 키가 `base_won` 이라 **전부 「원」처럼 읽힌다.** 실제로는 셋이다 —
`int(total_gfa_sqm)`(㎡) · `total_households`(세대) · `total_sale_amount_won`(원).
표시층이 전부 `"원(과표)"` 로 라벨링해 **「300원 과표 × 140,000 요율」** 이라는
**존재하지 않는 주장**을 화면에 냈다(22 대입 중 11 이 거짓).

## 이 테스트가 잠그는 것

★**목록을 손으로 유지하면 반드시 갈린다.** 그래서 모집단을 **엔진이 실제로 내는 코드**에서
파생시켜, 표에 **빠진 코드**를 실패로 신고한다. 그리고 단위가 맞는지는 **엔진을 두 번
서로 다른 입력으로 태워** 과표가 무엇을 따라 움직이는지로 판정한다 — 소스 문자열이 아니라
**행위**로 본다.
"""

from __future__ import annotations

from app.services.feasibility.legacy_ledger import build_legacy_ledger
from app.services.feasibility.rough_feasibility_orchestrator import compact_charge_items
from app.services.tax.charge_base_units import CHARGE_BASE_UNITS, base_units_for
from app.services.tax.sale_stage_engine import calculate_all_sale_stage
from app.services.tax.utility_stage_engine import calculate_all_utility_stage

_BASE = dict(total_sale_amount_won=100_000_000_000, total_units=300, total_gfa_sqm=45_000)


def _items(**over) -> dict[str, dict]:
    kw = {**_BASE, **over}
    out: dict[str, dict] = {}
    for it in calculate_all_utility_stage(
        sido_name="서울특별시", sigungu_name="강남구",
        total_sale_amount_won=kw["total_sale_amount_won"],
        total_households=kw["total_units"], total_gfa_sqm=kw["total_gfa_sqm"],
    )["items"]:
        out[it["code"]] = it
    for it in calculate_all_sale_stage(
        total_sale_amount_won=kw["total_sale_amount_won"],
        total_units=kw["total_units"], total_gfa_sqm=kw["total_gfa_sqm"],
    )["items"]:
        out[it["code"]] = it
    return out


def test_engine_emits_codes_and_probe_is_alive():
    """★전제 — 엔진이 실제로 항목을 낸다(대조군 없는 「전부 일치」를 막는다)."""
    items = _items()
    assert len(items) >= 10, f"엔진 산출이 너무 적다 — 조회기가 죽었다: {sorted(items)}"
    assert "B03" in items and "C01" in items


def test_every_emitted_code_has_a_unit_entry():
    """★파생형 — 엔진이 내는 코드 중 **표에 없는 것**을 실패로 신고한다.

    새 부담금을 추가하면 이 테스트가 먼저 빨개진다. 손 목록이면 조용히 빠진다.
    """
    missing = sorted(c for c in _items() if c not in CHARGE_BASE_UNITS)
    assert not missing, (
        f"단위표에 없는 부담금 코드: {missing} — "
        "app/services/tax/charge_base_units.py 에 추가하거나, 모르면 넣지 말고 "
        "표시층이 수량·단가를 비우게 두십시오."
    )


def test_no_dead_entries_in_the_table():
    """★죽은 항목도 실패다 — 엔진이 더 이상 안 내는 코드가 표에 남으면 잘못된 안심을 준다."""
    dead = sorted(c for c in CHARGE_BASE_UNITS if c not in _items())
    assert not dead, f"엔진이 내지 않는 코드가 표에 남아 있다: {dead}"


def test_qty_unit_matches_what_the_base_actually_tracks():
    """★★단위를 **행위로** 판정한다 — 입력 하나만 바꿔 과표가 따라 움직이는지 본다.

    소스 문자열 대조가 아니다. `base_won` 이 세대수를 두 배로 했을 때 두 배가 되면
    그 과표의 단위는 **세대**다. 라벨이 그것과 다르면 화면이 거짓을 말한다.
    """
    base = _items()
    doubled = {
        "세대": _items(total_units=600),
        "㎡": _items(total_gfa_sqm=90_000),
        "원": _items(total_sale_amount_won=200_000_000_000),
    }
    mismatched: list[str] = []
    for code, it in base.items():
        b0 = it.get("base_won")
        if not b0:  # 0·None 은 판별 불가 — 이 케이스로는 말하지 않는다
            continue
        label = base_units_for(code)[0]
        moved = [u for u, m in doubled.items() if (m.get(code) or {}).get("base_won") != b0]
        if label not in moved:
            mismatched.append(f"{code}: 라벨 '{label}' 인데 실제로 움직인 축 {moved or '없음'}")
    assert not mismatched, "과표 단위 라벨이 실제와 다르다:\n" + "\n".join(mismatched)


def test_unknown_code_returns_none_not_a_guess():
    """★모르는 코드는 `(None, None)` — 추측해서 라벨을 붙이지 않는다."""
    assert base_units_for("ZZ99") == (None, None)
    assert base_units_for(None) == (None, None)
    # 대조군 — 아는 코드는 값을 준다(전부 None 을 돌려주는 구현이 통과하지 않게).
    # ★2026-08-27 차원 교정 — 하수도법 §61+시행령 §35(㎥/일)·수도법 시행령 §65①(사용량).
    #   법·시행령·조례에서 「세대」 출현 0회(원문 실측). 종전 ("세대","원/세대")는 법정 차원이 아니었다.
    # ★B03 상수도는 **축을 모른다고 선언**한다 — 실비(원가계산)라 과표×요율 구조가 아니다
    #   (수도법 시행령 §65③). 「빼기」가 아니라 「(None, None) 로 선언」이 정답이다 —
    #   빼면 「미등록」과 「모름 판정」이 구별되지 않는다.
    assert base_units_for("B03") == (None, None)
    assert "B03" in CHARGE_BASE_UNITS


# ── 실엔진 → 압축 → 원장 **한 줄로 태운다** ───────────────────────────────────
#   ★적대 리뷰 중5: `confidence` 를 압축이 **최상위**에서 읽어 프로덕션에서 **항상 None** 이었다
#     (엔진 16종 전수: 최상위 non-None 0/16 · 실제로는 전부 `detail` 안). 강등 표기가 한 번도
#     발화하지 않았는데 **테스트는 초록**이었다 — 픽스처가 최상위에 그 필드를 **발명**했기
#     때문이다. 「테스트가 생산자」의 다른 얼굴이다.
#   → 픽스처를 쓰지 않고 **실엔진 산출**을 그대로 먹인다. 계약을 발명할 수 없다.
def _real_charges_result() -> dict:
    kw = dict(total_sale_amount_won=100_000_000_000, total_units=300, total_gfa_sqm=45_000)
    return {
        "construction": calculate_all_utility_stage(
            sido_name="서울특별시", sigungu_name="강남구",
            total_sale_amount_won=kw["total_sale_amount_won"],
            total_households=kw["total_units"], total_gfa_sqm=kw["total_gfa_sqm"],
        ),
        "sale": calculate_all_sale_stage(**kw),
    }


def test_confidence_survives_the_real_engine_shape():
    """★★강등 신뢰도가 **실엔진에서** 압축을 통과한다 — 픽스처가 아니라 엔진이 준 모양으로."""
    raw = _real_charges_result()
    engine_conf = {
        it["code"]: (it.get("detail") or {}).get("confidence") or it.get("confidence")
        for stage in (raw["construction"], raw["sale"]) for it in stage["items"]
    }
    have = {c: v for c, v in engine_conf.items() if v}
    assert have, "엔진이 신뢰도를 하나도 안 준다 — 검사 전제가 깨졌다(조회기 사망)"

    compacted = {i["code"]: i for i in compact_charge_items(raw)}
    lost = sorted(c for c, v in have.items() if compacted[c]["confidence"] != v)
    assert not lost, (
        f"압축이 신뢰도를 흘렸다: {lost} — 엔진은 `detail` 안에 싣는다"
        f"(형제 project_charges.py 가 처음부터 그렇게 읽는다)"
    )


def test_degraded_reason_reaches_the_ledger_row():
    """★강등 사유가 **원장 행의 비고까지** 닿는다 — 사유를 버리면 진단 불가가 장애가 된다."""
    raw = _real_charges_result()
    items = compact_charge_items(raw)
    degraded = [i for i in items if i.get("confidence") and i["confidence"] != "confirmed"]
    assert degraded, "강등 항목이 하나도 없다 — 이 검사가 태울 대상이 없다(공허한 초록)"

    led = build_legacy_ledger({"charges": {"total_won": 0, "items": items}})
    rows = {i["key"]: i for s in led["sections"] for g in s["groups"] for i in g["items"]}
    for d in degraded:
        row = rows.get(f"charge_{d['code'].lower()}")
        if row is None:      # 수분양자 부담분은 원장에 안 실린다(설계)
            continue
        assert row["note"] and "신뢰도" in row["note"], (
            f"{d['code']}: 강등 신뢰도가 화면 비고에 안 실렸다 — 사용자가 원인을 물을 곳이 없다"
        )
