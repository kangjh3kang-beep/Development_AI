"""B03/B04 상하수도 원인자부담금 — **지어낸 단가를 계상하지 않는다**.

## 이 파일의 역사 (두 번의 같은 결함)

1. **2026-07-11 `14e6abe9`** — `get_utility_charge` 가 미등록 지역에 임의 폴백
   **120,000원/세대**를 돌려주던 것을 제거했다. 그 커밋의 근거:
   *"수도법 §71·하수도법 §61 은 산정을 조례에 위임하므로 **전국 단일 표준값이 존재하지 않는다.**
   '전국 기본값 120,000'은 지어낸 값."*

2. **2026-08-27 (이번)** — ★그런데 그 커밋은 **표 자체는 건드리지 않았다.**
   *"등록 지역은 confidence='regional'로 정상 부과(무회귀)"* 라고 **전제**하고 넘어갔다.
   재보니 그 표(20키)도 같은 산물이었다:

   · **제거된 `120_000` 이 표에 그대로 있었다**(`대구`·`경기_오산시`) — 같은 값·같은 단위
   · 출처 인용 **0건**(`git log -S` → 대량 생성 커밋 1건, 주석은 `# 시군구 → 원/세대` 뿐)
   · 값 분포가 **5,000원 계단**(상수도 고유값 10개·하수도 11개) — 독립 조례 20건이 낼 분포가 아니다
   · ★**차원이 법과 다르다** — 아래

## 법정 차원 (법제처 원문 · 대조군으로 파서 생존 증명)

    하수도법 §61① + 시행령 §35①  "오수가 하루 10세제곱미터 이상 증가"      → ㎥/일
    울산시 하수도 사용 조례 §24①4호 "오수발생량(㎥/일) × 단위단가(원/㎥/일)"  → ㎥/일
    수도법 §71② → 시행령 §65③     신설·증설 실비(원가계산) 합산              → 원가
    수도법 시행령 §65①            협의 불성립 시 "수돗물 사용량에 따라"       → 체적

★**법 2 + 시행령 2 = 4개 문서에서 `'세대'`·`'가구'` 출현 0회**(대조군 `'수도'` 1,108회·`'하수'` 847회).
      ★**조례는 다르다** — 울산시 하수도 사용 조례 **§9②** 는 *"…세대별, 건축 단위면적별 또는
        배수관경별 공사비를 **정액으로 결정 고시**할 수 있다"* 고 한다(공사비 산출방법).
        즉 *"원/세대는 **어떤 단가로도** 법정 산식이 될 수 없다"* 는 **과잉일반화**였다(독립 리뷰 지적).
        확정된 것은 **원인자부담금 산정식**(§24①4호)이 오수발생량×단위단가라는 것이다. `원/세대`는 **어떤 단가로도**
법정 산식이 될 수 없다 — 단가만 고치는 봉합은 차원 오류를 남긴다.

★**격차 실측(울산)**: 시 공고 단위단가 2,356,000원/㎥/일로 재계산 시 **8,100만~1억 1,100만원**
(환경부 오수발생량 고시 별표, 1호당 거실수 2~4). 종전 코드값 **992만원** = **8~11배 과소**.
과소계상은 총사업비를 낮춰 **수익성을 과대**하게 만든다.
"""

from __future__ import annotations

import pytest

from app.services.tax.regional_tax_data import (
    SEWAGE_CHARGES_WON,
    OrdinanceUnitRate,
    get_utility_charge,
)
from app.services.tax.utility_stage_engine import (
    calculate_b03_water_supply,
    calculate_b04_sewage,
)


def test_get_utility_charge_returns_none_for_unregistered():
    """★조례 미등록 지역 → None (임의 전국폴백 금지)."""
    assert get_utility_charge(SEWAGE_CHARGES_WON, "강원", "정선군") is None


@pytest.mark.parametrize("table", [SEWAGE_CHARGES_WON])
def test_tables_hold_no_unsourced_rates(table):
    """★표에 값이 있다면 **전부 출처를 갖고 있어야** 한다.

    지금은 비어 있다(1차 출처 미확보). 나중에 채우더라도 `OrdinanceUnitRate` 가
    `basis`·`source_url`·`as_of` 를 **문법적으로 요구**하므로 출처 없는 값은 넣을 수 없다.
    """
    for key, rate in table.items():
        assert isinstance(rate, OrdinanceUnitRate), f"{key}: 출처 없는 원시 정수 금지"
        assert rate.basis.strip(), f"{key}: 조례·공고 인용이 비었다"
        assert rate.source_url.strip(), f"{key}: 1차 출처 URL 이 비었다"
        assert rate.as_of.strip(), f"{key}: 시행일이 비었다"


@pytest.mark.parametrize("fn", [calculate_b03_water_supply, calculate_b04_sewage])
def test_b03_b04_are_withheld_not_fabricated(fn):
    """단가 미확보 → **0 + unavailable + 사유**. 세대수를 곱해 값을 만들지 않는다."""
    r = fn(sido_name="강원", sigungu_name="정선군", total_households=300)
    assert r["amount_won"] == 0
    assert r["rate"] is None
    assert r["detail"]["confidence"] == "unavailable"
    assert r["detail"]["surveyed"] is False, "정직 기계(AWAITING_INPUT)가 읽는 신호"
    assert r["detail"]["reason"].strip(), "사유 없는 0 은 「없음」과 구별되지 않는다"


@pytest.mark.parametrize(
    ("fn", "must_name"),
    [
        (calculate_b03_water_supply, "수도법"),
        (calculate_b04_sewage, "㎥/일"),
    ],
)
def test_reason_names_the_legal_dimension(fn, must_name):
    """★사유가 **법정 차원**을 말해야 한다 — 종전 사유는 '조례 확인 필요'로 뭉뚱그렸다."""
    r = fn(sido_name="강원", sigungu_name="정선군", total_households=300)
    assert must_name in r["detail"]["reason"]


def test_household_count_does_not_move_the_amount():
    """★차원 락 — 세대수를 10배로 해도 **금액이 움직이면 안 된다**.

    이것이 이 파일의 핵심 단언이다. 종전 구현은 `원/세대 × 세대수` 라 세대수에 **비례**했다.
    법정 산식은 **오수발생량(㎥/일)** 의 함수이고 세대수는 그 대리변수가 아니다.
    ★반대 방향(과잉 억제) 탐지: 아래 `test_..._withheld_not_fabricated` 가 0/unavailable 을
      따로 단언하므로, "항상 0을 낸다"는 구현도 여기서는 통과하지만 **사유·플래그로 갈린다.**
    """
    for fn in (calculate_b03_water_supply, calculate_b04_sewage):
        small = fn(sido_name="서울", sigungu_name="강남구", total_households=50)
        large = fn(sido_name="서울", sigungu_name="강남구", total_households=500)
        assert small["amount_won"] == large["amount_won"], (
            f"{fn.__name__}: 세대수에 비례하면 차원 오류가 되살아난 것이다"
        )


def test_the_old_fabricated_value_cannot_return():
    """★음성 대조군 — 제거된 `120,000원/세대` 계열이 되살아나지 않는다."""
    r = calculate_b03_water_supply(sido_name="대구", sigungu_name="", total_households=100)
    assert r["amount_won"] != 120_000 * 100
    assert r["amount_won"] == 0


# ── ★단가를 **확보한 상태**를 합성해 태운다 ────────────────────────────────────
#
# 독립 리뷰가 잡은 CRITICAL: 표가 비어 있으면 「단가 확보」 분기가 **도달 0** 이라
# 그 안의 어떤 변이도 자동 생존한다. 실측 — 그 분기를 `원/세대 × 세대수` 로 되돌리는
# 변이가 **SURVIVED(208 passed)**. 「세대수 10배에도 금액 불변」 락은 두 값이 모두 0 이라
# **원리적으로 실패할 수 없었다**(공허한 참).
# → 합성 `OrdinanceUnitRate` 를 주입해 그 분기를 **실제로 태운다.**

_SYNTH = OrdinanceUnitRate(
    won_per_cbm_day=2_356_000,          # 울산 공고 형태(실측값 형태 — 표에 넣지 않는다)
    basis="합성 픽스처(울산 §24①4호 형태)",
    source_url="test://synthetic",
    as_of="2026-01-01",
)


@pytest.fixture()
def sewage_rate_registered(monkeypatch):
    """`SEWAGE_CHARGES_WON` 에 합성 단가를 넣어 **확보 분기**를 도달 가능하게 한다."""
    monkeypatch.setitem(SEWAGE_CHARGES_WON, "울산", _SYNTH)
    return _SYNTH


def test_rate_acquired_branch_is_reachable(sewage_rate_registered):
    """★대조군 — 이 픽스처가 **실제로 분기를 바꾸는지** 먼저 증명한다.

    이게 없으면 아래 단언들이 여전히 `rate is None` 분기를 태우면서 초록일 수 있다.
    """
    r = calculate_b04_sewage(sido_name="울산", sigungu_name="", total_households=64)
    assert r["rate"] == sewage_rate_registered.won_per_cbm_day, "확보 분기에 도달하지 못했다"
    assert r["detail"].get("basis") == sewage_rate_registered.basis


def test_rate_acquired_still_does_not_charge(sewage_rate_registered):
    """단가를 확보해도 **금액은 0** — 법정 산식이 요구하는 ㎥/일 입력이 없다."""
    r = calculate_b04_sewage(sido_name="울산", sigungu_name="", total_households=64)
    assert r["amount_won"] == 0
    assert r["detail"]["confidence"] == "unavailable"
    assert r["detail"]["surveyed"] is False
    assert "㎥/일" in r["detail"]["reason"]


def test_rate_acquired_amount_is_not_a_function_of_households(sewage_rate_registered):
    """★**진짜 차원 락** — 단가가 있는 상태에서 세대수를 10배로 해도 금액이 움직이면 안 된다.

    종전 구현(`per_hh × 세대수`)을 이 분기에 되살리는 변이는 여기서 죽는다.
    표가 비어 있을 때의 같은 이름 단언은 **공허**했다(둘 다 0).
    """
    small = calculate_b04_sewage(sido_name="울산", sigungu_name="", total_households=50)
    large = calculate_b04_sewage(sido_name="울산", sigungu_name="", total_households=500)
    assert small["amount_won"] == large["amount_won"] == 0
    assert small["rate"] == large["rate"], "단가는 세대수와 무관하다"


def test_full_name_input_still_matches_after_normalization(sewage_rate_registered):
    """★#3 대체 계약 — 삭제한 `"서울특별시" == 150_000` 단언이 잠그던 **완전명 정규화**.

    합성 단가를 축약키 `"울산"` 에 넣고 **완전명**으로 조회한다.
    `normalize_sido_short` 를 제거하는 변이가 여기서 죽는다.
    """
    assert get_utility_charge(SEWAGE_CHARGES_WON, "울산광역시", "").won_per_cbm_day == _SYNTH.won_per_cbm_day
    assert get_utility_charge(SEWAGE_CHARGES_WON, "울산", "").won_per_cbm_day == _SYNTH.won_per_cbm_day
