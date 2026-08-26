"""광역교통시설부담금 **부과율이 법령 원문과 일치하는가**.

## 왜 (2026-08-27 · 법제처 DRF 원문 직접 조회)

종전 구현은 **전용 85㎡ 이하 1% · 초과 2%** 였다. **법령에 그런 분기가 없다.**

    법 §11조의3①2호(§11①4·5호 사업)·3호(§11①6호 사업)
        = 1㎡당 **표준건축비** × 부과율 × **건축연면적** − 공제액   ← 이 모듈의 산식
    시행령 §16조의2⑧2호
        = 「법 제11조의3제1항제2호 및 제3호의 부과율 : **100분의 2**.
           다만, 별표 1의 대도시권중 **수도권인 경우에는 100분의 4**」

★**대조군으로 문서가 맞는지 먼저 확인했다** — 시행령 원문에 `부담금` 63회 · `제16조의2` 22회 ·
  `부과율` 5회. 그런데 **`전용면적` 은 법·시행령 양쪽에서 0회**다. 85㎡ 분기는 근거가 없다.
  (감면 규정 법 §11의2·령 §16 은 *국민주택규모 이하 임대주택 **사업***에 대한 **사업유형 면제**이지
   요율 분기가 아니다.)

★그래서 **수도권은 종전 1~2% → 4% 로 2~4배 교정**된다.

## 이 파일이 잠그는 것

| 축 | 검사 |
|---|---|
| **법령 값 결속** | 수도권 `0.04` · 그 외 `0.02` 를 상수와 대조 |
| **두 모집단** | 수도권 시도와 비수도권 시도가 **같은 실행에서 갈린다** |
| **85㎡ 분기 부활 방지** | 전용면적이 무엇이든 요율이 **같다** |
| **파생형** | 수도권/대도시권 집합을 **소스에서 파생** — 손 목록 금지 |
| **부채 가시화** | 조례 요율 조정(법 §11의3③) 미반영을 `xfail` 로 초록 안에 |
"""

from __future__ import annotations

import pytest

from app.services.tax.regional_tax_data import (
    CAPITAL_AREA_SIDO,
    METRO_AREA_SIDO,
    METRO_TRANSPORT_RATE_CAPITAL,
    METRO_TRANSPORT_RATE_NON_CAPITAL,
    get_metro_transport_charge,
    is_capital_area_sido,
    metro_transport_charge_rate,
)


def _rate(sido: str, area: float | None = None) -> float:
    return metro_transport_charge_rate(
        is_housing=True, exclusive_area_sqm=area, sido_name=sido,
    )


# ── ① 법령 값 결속 ──────────────────────────────────────────────────────────
def test_statutory_rates_are_two_and_four_percent():
    """시행령 §16조의2⑧2호의 **원문 값**과 상수가 일치하는가."""
    assert METRO_TRANSPORT_RATE_NON_CAPITAL == 0.02, "시행령 §16조의2⑧2호 본문 = 100분의 2"
    assert METRO_TRANSPORT_RATE_CAPITAL == 0.04, "같은 호 단서 = 수도권 100분의 4"
    # ★1호(15%/30%)를 잘못 가져오면 이 단언이 잡는다 — 그건 **다른 산식**의 요율이다.
    assert METRO_TRANSPORT_RATE_CAPITAL < 0.10, (
        "부과율이 10%를 넘는다 — 법 §11의3①1호(표준개발비 산식·15%/30%)를 "
        "2·3호(표준건축비 산식) 자리에 가져왔을 수 있다"
    )


# ── ② 두 모집단이 **같은 실행에서** 갈리는가 ────────────────────────────────
def test_capital_and_non_capital_actually_differ():
    """★한 값만 확인하면 *"전부 같은 값을 내는"* 구현도 통과한다."""
    capital = sorted(CAPITAL_AREA_SIDO)
    non_capital = sorted(METRO_AREA_SIDO - CAPITAL_AREA_SIDO)
    assert len(capital) >= 3, f"수도권 모집단 {len(capital)} — 공허하다"
    assert len(non_capital) >= 5, f"비수도권 대도시권 {len(non_capital)} — 공허하다"

    for s in capital:
        assert _rate(s) == METRO_TRANSPORT_RATE_CAPITAL, f"{s}: 수도권인데 4%가 아니다"
    for s in non_capital:
        assert _rate(s) == METRO_TRANSPORT_RATE_NON_CAPITAL, f"{s}: 비수도권인데 2%가 아니다"

    # ★대조군 — 두 집합이 실제로 **다른 값**을 낸다(같으면 게이트가 죽은 것이다).
    assert _rate(capital[0]) != _rate(non_capital[0])


def test_capital_area_is_a_strict_subset_of_metro_area():
    """수도권 ⊂ 대도시권. 두 집합을 뒤섞으면 요율이 전국에서 틀린다."""
    assert CAPITAL_AREA_SIDO < METRO_AREA_SIDO, "수도권이 대도시권의 진부분집합이 아니다"
    assert {"서울", "인천", "경기"} == CAPITAL_AREA_SIDO


@pytest.mark.parametrize("full,short", [("서울특별시", "서울"), ("울산광역시", "울산"),
                                        ("경기도", "경기"), ("부산광역시", "부산")])
def test_full_and_short_sido_names_agree(full: str, short: str):
    """완전명·축약형이 **같은 요율**을 내는가 — 정규화가 요율 판정 앞에 있는가."""
    assert _rate(full) == _rate(short), f"{full} 과 {short} 의 요율이 다르다"
    assert is_capital_area_sido(full) == is_capital_area_sido(short)


# ── ③ 85㎡ 분기 부활 방지 ───────────────────────────────────────────────────
@pytest.mark.parametrize("sido", ["서울", "울산"])
def test_exclusive_area_no_longer_changes_the_rate(sido: str):
    """전용면적이 무엇이든 요율은 **같다** — 법령에 그 분기가 없다.

    ★85㎡ **경계 양쪽**을 같은 실행에서 본다. 한쪽만 보면 종전 구현도 통과한다.
    """
    rates = {_rate(sido, a) for a in (0.0, 39.9, 84.9, 85.0, 85.1, 200.0, None)}
    assert len(rates) == 1, (
        f"{sido}: 전용면적에 따라 요율이 갈린다 {rates} — "
        "법·시행령 원문에 `전용면적` 은 0회 등장한다(85㎡ 분기는 근거 없음)"
    )


def test_non_housing_uses_the_same_statutory_rate():
    """주택 외 시설도 같은 호(2·3호)의 요율을 쓴다 — 종전 `is_housing` 분기는 죽었다."""
    for sido in ("서울", "울산"):
        assert metro_transport_charge_rate(
            is_housing=False, exclusive_area_sqm=None, sido_name=sido,
        ) == _rate(sido)


# ── ④ 배선 — 요율이 **금액 산출까지** 도달하는가 ────────────────────────────
def test_the_rate_reaches_the_charge_calculation():
    """★요율만 잠그면 *"계산이 그것을 안 쓰는"* 상태를 못 잡는다.

    `get_metro_transport_charge` 가 실제로 지역별로 **다른 `rate` 를 싣는지** 본다.
    (금액 자체는 표준건축비 미주입 환경에서 `None`/`0` 일 수 있으므로 `rate` 로 판정한다.)
    """
    seoul = get_metro_transport_charge(sido_name="서울특별시", gfa_sqm=6572.0, building_type="apartment")
    ulsan = get_metro_transport_charge(sido_name="울산광역시", gfa_sqm=6572.0, building_type="apartment")
    assert seoul.get("rate") == METRO_TRANSPORT_RATE_CAPITAL, f"서울 rate={seoul.get('rate')}"
    assert ulsan.get("rate") == METRO_TRANSPORT_RATE_NON_CAPITAL, f"울산 rate={ulsan.get('rate')}"
    assert seoul.get("rate") != ulsan.get("rate"), "지역이 요율에 도달하지 않는다"

    # ★음성 대조군 — 대도시권이 아니면 애초에 부과 대상이 아니다.
    gangwon = get_metro_transport_charge(sido_name="강원특별자치도", gfa_sqm=6572.0, building_type="apartment")
    assert gangwon.get("applicable") is False, "비대도시권인데 부과 대상으로 판정된다"


# ── ⑤ 부채를 **초록 안에** 드러낸다 ─────────────────────────────────────────
@pytest.mark.xfail(
    reason="★미반영 부채 — 법 §11조의3③ 은 시·도지사가 **조례로 100분의 50 범위에서** "
           "부과율을 조정할 수 있게 한다. 이 함수는 조례를 보지 않는다. "
           "조정한 시·도가 실재하는지는 **미측정**이며, 조례 요율은 상하수도 단가와 달리 "
           "본문에 숫자로 있을 가능성이 있어 「지자체별 실시간 조사」가 값을 할 자리다.",
    strict=True,
)
def test_local_ordinance_rate_adjustment_is_reflected():
    """조례로 조정한 요율이 반영되는가 — **아직 아니다.**"""
    from app.services.tax.regional_tax_data import metro_transport_charge_rate_with_ordinance  # noqa: PLC0415

    assert metro_transport_charge_rate_with_ordinance is not None
