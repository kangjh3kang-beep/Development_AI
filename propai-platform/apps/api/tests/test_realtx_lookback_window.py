"""실거래 수집 창 락 — **등기와 해제는 시간상수가 다르다**.

## 무엇이 결함이었나 (라이브 실측 2026-08-26 · 41465 apt)

종전 `DEFAULT_LOOKBACK_MONTHS = 3` 은 **등기의 절반을 구조적으로 못 봤다.**
같은 시군구를 **노출 기간별로** 재니 기재율이 시간의 함수였다:

    노출     1개월   2개월   3개월   5개월   7개월
    등기     5.4%   24.3%  **54.1%**  96.1%  97.4%
    해제     2.9%    2.3%    2.6%    2.1%   2.5%   ← 평평

계약→등기 간격(**완전 관측** 202601 · 표본 629): 중앙 **72일** · p95 **109** · 최대 **150**.
**90일 초과 23.5%.**

## ★그리고 절단된 표본은 **확신에 찬 오답**을 준다

노출 1개월 달로 같은 지표를 재면 *"90일 초과 0건(0.0%)"* 이다. 우리가 저장한 3개월치
(4,898행)만 봐도 같은 0% 가 나온다 — **창 자체가 관측을 자르기 때문**이다.
**완전 관측된 옛 달을 따로 태우고서야** 23.5% 가 보였다.

## ★이 락이 **못 보는** 것

1. **표본이 시군구 1개(`41465` · `apt`)** 다. `land` 와 다른 시군구의 시간상수는 **미측정**.
2. **`TAIL_MONTHS = 7` 자체가 새 절단**이다 — 10·12개월은 재지 않았다. 5→7개월이
   96.1→97.4% 로 완만해 고른 값이고, **줄이면 등기를 다시 놓친다**.
3. **주간 실행이 실제로 발화하는지**는 배포 후 로그로만 안다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.tasks import realtx_sync_task as T


def _at(day: int, hour: int = 19) -> datetime:
    return datetime(2026, 8, day, hour, 10, tzinfo=UTC)


# ══════════════════════════════════════════════════════════════
# 1. ★두 모집단 — 꼬리 실행일과 비실행일이 **다른 집합**을 낸다
# ══════════════════════════════════════════════════════════════

def test_tail_day_and_normal_day_yield_different_month_sets():
    """차가 0이면 배선을 끊어도 결과가 같아 아무것도 안 잠긴다."""
    wed, _ = T.months_for(_at(26))     # 2026-08-26 = 수
    thu, _ = T.months_for(_at(27))     # 목
    assert len(wed) == T.TAIL_MONTHS
    assert len(thu) == T.RECENT_MONTHS
    assert len(wed) != len(thu), (wed, thu)
    assert set(thu) < set(wed), "최근 창은 꼬리 창의 부분집합이어야 한다(중복 요청 방지)"


def test_tail_flag_matches_the_span():
    """★플래그와 실제 집합이 갈리면 로그가 거짓말을 한다."""
    for day in range(24, 31):
        months, tail = T.months_for(_at(day))
        assert len(months) == (T.TAIL_MONTHS if tail else T.RECENT_MONTHS), (day, tail, months)


def test_exactly_one_tail_run_per_week():
    days = [T.months_for(_at(d))[1] for d in range(24, 31)]
    assert sum(days) == 1, f"주 7일 중 꼬리 실행이 {sum(days)}회 — 1회여야 한다"


# ══════════════════════════════════════════════════════════════
# 2. ★절단 회피 — 상수에 결속한다(3으로 되돌리면 실패)
# ══════════════════════════════════════════════════════════════

#: 라이브 실측 포화점 — 5개월에 96.1%. 이보다 짧으면 등기를 구조적으로 놓친다.
_MEASURED_SATURATION_MONTHS = 5


def test_tail_reaches_the_measured_saturation_point():
    """★`TAIL_MONTHS` 를 3(종전 값)으로 되돌리면 여기서 죽는다.

    3개월은 등기의 **54.1%** 만 본다(실측). 포화는 5개월(96.1%)이다.
    """
    assert T.TAIL_MONTHS >= _MEASURED_SATURATION_MONTHS, (
        f"꼬리 {T.TAIL_MONTHS}개월은 실측 포화점 {_MEASURED_SATURATION_MONTHS}개월에 미달 — "
        "등기 정정을 구조적으로 놓친다"
    )


def test_recent_window_is_short_enough_to_stay_daily():
    """대조군 — 최근 창이 꼬리만큼 길면 매일 꼬리를 도는 것과 같아 쿼터가 는다."""
    assert T.RECENT_MONTHS < T.TAIL_MONTHS


def test_recent_window_covers_the_flat_cancel_signal():
    """해제는 1개월부터 평평하므로 최근 창은 **1개월 이상**이면 된다(하한만 건다)."""
    assert T.RECENT_MONTHS >= 1


# ══════════════════════════════════════════════════════════════
# 3. 결정성 — `now` 만으로 정해진다
# ══════════════════════════════════════════════════════════════

def test_same_instant_gives_the_same_answer():
    a = T.months_for(_at(26))
    b = T.months_for(_at(26))
    assert a == b


def test_hour_does_not_change_the_window():
    """크론이 밀려도 같은 날이면 같은 창이어야 한다."""
    assert T.months_for(_at(26, 3)) == T.months_for(_at(26, 23))


def test_month_list_is_descending_and_unique():
    months, _ = T.months_for(_at(26))
    assert months == sorted(months, reverse=True)
    assert len(set(months)) == len(months)


def test_window_crosses_the_year_boundary():
    """연말 경계 — 문자열 산술이 아니라 날짜 산술이어야 한다."""
    months, _ = T.months_for(datetime(2026, 1, 15, tzinfo=UTC))
    assert months[0] == "202601"
    assert "202512" in months, months
