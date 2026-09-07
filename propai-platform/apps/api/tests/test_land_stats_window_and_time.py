"""토지 시장통계 — **읍·면 동 매칭**과 시점수정.

## 왜 (2026-09-07 사용자 신고 · 라이브 실측)

> *"시세분석이 실무적으로 시장가를 못 잡아낸다"*
> *"실거래 기준일은 6개월 이내여야 실효성이 있을 것 같은데?"*

라이브(남양주 화도읍 마석우리 265-1 · 일반상업지역):

    선택된 층  sigungu_jimok(시군구·지목=답) → 표본에 **개발제한구역 40.2%** 혼입
    같은 용도지역 실거래 중앙(12개월)  4,038,261원/㎡
    채택가 3,057,000 → 실거래 대비 **−24%**

## ★기각한 가설 — 「창이 좁아서」

24개월 창을 **실제로 만들어 라이브로 쟀고 기각**했다:

    6개월   층=sigungu_jimok n=85   786,502원/㎡
    24개월  층=sigungu_jimok n=601  **631,272원/㎡**   ← 층 그대로, 값만 −20%

창이 아니었다. 그리고 사용자 판단도 같다 — *"6개월 이내여야 실효성이 있다"*.

## ★★진짜 원인 — 읍·면 주소에서 동 매칭이 **원리적으로 0건**

MOLIT `umdNm` 은 `"화도읍 마석우리"`, 타깃은 `"마석우리"`. `==` 비교라 **정확일치 0건**
(포함일치 16건). 동 계열 **네 층이 전부 실패**했다.
★실해 범위: 남양주 3개월 표본에서 `umdNm` 의 **81.5%가 읍·면 접두**를 갖는다.
"""

from __future__ import annotations

from app.services.market.land_dong_stats import MIN_SAMPLE, _dong_eq, dong_land_stats


def _rows(n: int, *, dong: str, land_use: str, jimok: str, ym: str, price_10k: int) -> list[dict]:
    return [{
        "dong": dong, "land_use": land_use, "jimok": jimok,
        "area_m2": 100.0, "price_10k_won": price_10k,
        "deal_date": f"{ym[:4]}년 {int(ym[4:]):d}월 1일", "share_dealing_type": "",
    } for _ in range(n)]


# ── 읍·면 매칭 ────────────────────────────────────────────────────────────────

def test_읍면_접두가_붙어도_동이_일치한다() -> None:
    """★핵심 봉합 — 이게 없으면 읍·면 지역의 동 층이 전부 죽는다."""
    assert _dong_eq("화도읍 마석우리", "마석우리") is True
    assert _dong_eq("조안면 삼봉리", "삼봉리") is True
    assert _dong_eq("논현동", "논현동") is True, "시(동) 지역 기존 동작이 깨졌다"


def test_부분문자열은_일치가_아니다() -> None:
    """★위양성 축 — `in` 으로 고치면 다른 동을 오염시킨다.

    이 축이 없으면 «전부 True» 를 돌려주는 구현이 위 테스트를 통과한다.
    """
    assert _dong_eq("화도읍 마석우리", "석우리") is False, "부분문자열이 일치로 샌다"
    assert _dong_eq("화도읍 마석우리", "화도읍") is False
    assert _dong_eq("마석우리로 123", "마석우리") is False
    assert _dong_eq("", "마석우리") is False
    assert _dong_eq("화도읍 마석우리", "") is False


def test_읍면_봉합이_층_선택을_실제로_바꾼다() -> None:
    """★두 모집단 — 봉합 전이라면 시군구 층으로 떨어졌을 입력.

    동 표본(읍 접두)만 있고 시군구 표본이 더 많은 상황에서, 동 층이 서는지 본다.
    """
    rows = (
        _rows(MIN_SAMPLE + 1, dong="화도읍 마석우리", land_use="일반상업지역",
              jimok="대", ym="202606", price_10k=40_000)
        + _rows(50, dong="진건읍 용정리", land_use="개발제한구역",
                jimok="대", ym="202606", price_10k=3_000)
    )
    r = dong_land_stats(rows, target_dong="마석우리",
                        target_land_use="일반상업지역", target_jimok="대")
    assert r is not None
    assert r["layer"].startswith("dong"), (
        f"읍 접두 때문에 동 층이 서지 못했다 — layer={r['layer']}")
    assert r["sample_count"] == MIN_SAMPLE + 1, "시군구 표본이 섞였다"


def test_읍면_흡수는_동_축에만_적용된다() -> None:
    """★축 락 — 지목·용도지역에 읍·면 흡수를 쓰면 다른 조건이 섞인다.

    ★실제 MOLIT 지목 값에는 공백이 없어(대·답·임야·도로) 두 구현이 **등가라서**
      변이가 생존했다(실측). 등가여도 **축은 틀린 것**이므로, 공백이 든 합성 입력으로
      계약을 못 박는다 — 원천이 표기를 바꾸면 그때 조용히 새기 때문이다.
    """
    from app.services.market.land_dong_stats import _matches

    row = {"dong": "화도읍 마석우리", "jimok": "잡종지 대", "land_use": "일반 상업지역"}
    # 동은 흡수한다.
    assert _matches(row, ("dong",), {"dong": "마석우리"}) is True
    # 지목·용도지역은 **정확일치**여야 한다(흡수하면 아래가 True 가 된다).
    assert _matches(row, ("jimok",), {"jimok": "대"}) is False, (
        "지목에 읍·면 흡수가 적용됐다 — 「잡종지 대」가 「대」로 매칭된다")
    assert _matches(row, ("land_use",), {"land_use": "상업지역"}) is False, (
        "용도지역에 읍·면 흡수가 적용됐다")


# ── 시점수정 ──────────────────────────────────────────────────────────────────

def test_시점수정이_값을_실제로_바꾼다() -> None:
    """★두 모집단 — 같은 표본에 시계열만 주고/안 주고."""
    rows = _rows(MIN_SAMPLE + 2, dong="화도읍 마석우리", land_use="일반상업지역",
                 jimok="대", ym="202501", price_10k=10_000)
    tgt = dict(target_dong="마석우리", target_land_use="일반상업지역", target_jimok="대")

    off = dong_land_stats(rows, **tgt)
    series = [(f"20{25 + (i // 12)}{(i % 12) + 1:02d}", 1.0) for i in range(24)]
    on = dong_land_stats(rows, **tgt, rate_series=series, now_ym="202612")

    assert off and on
    assert off["time_adjusted"] is False
    assert on["time_adjusted"] is True, "시계열을 줬는데 시점수정이 꺼져 있다 — 배선 끊김"
    assert on["unit_price_per_sqm"] > off["unit_price_per_sqm"], (
        "시점수정이 값을 바꾸지 않는다 — 인자만 받고 쓰지 않는 «외형»이다")


def test_시계열이_비면_하는_척하지_않는다() -> None:
    """★위양성 축 — 빈 시계열에 «보정했다»가 뜨면 거짓 근거가 원장에 남는다."""
    rows = _rows(MIN_SAMPLE + 2, dong="화도읍 마석우리", land_use="일반상업지역",
                 jimok="대", ym="202501", price_10k=10_000)
    r = dong_land_stats(rows, target_dong="마석우리", target_land_use="일반상업지역",
                        target_jimok="대", rate_series=None, now_ym="202612")
    assert r and r["time_adjusted"] is False and r["time_adjusted_count"] == 0
