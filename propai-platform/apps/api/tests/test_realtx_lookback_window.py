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
    """★종전 단언(`>= 1`)은 **공허했다** — `recent_months` 가 `max(1, months)` 라
    `RECENT_MONTHS = 0` 이어도 창은 1개월이 나온다(2026-08-27 리뷰 L1).

    해제는 1개월부터 평평하지만(2.9·2.3·2.6·2.1·2.5%), **신규 거래의 지연 신고**를
    덮으려면 여러 달이 필요하다 — 실측 표본에서 202607 조회에 202605 거래가 섞여 있었다.
    값을 못 박고 사유를 적는다.
    """
    assert T.RECENT_MONTHS == 3, "최근 창을 바꾸려면 지연 신고 분포를 먼저 재라"


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


# ══════════════════════════════════════════════════════════════
# 4. ★꼬리는 **등기를 보고하는 유형만** — 저장분 전수 실측이 근거
# ══════════════════════════════════════════════════════════════
#
#   유형    행      등기            해제
#   apt   4,110    737(17.9%)      79(1.9%)
#   land    788      **0(0.0%)**   49(6.2%)   ← 6개 시군구 전부 0
#
# 대조군으로 같은 조회에서 apt 는 나온다(노출별 28.6%·12.8%·3.8%) — **조회기가 죽은 것이
# 아니라 원천이 안 준다.** 꼬리는 오직 등기를 잡으려고 있으므로 land 를 넣으면 순수 낭비다.


def test_tail_excludes_types_that_never_report_registration():
    """★`land` 를 꼬리에 넣으면 **잡을 것이 없는 요청**을 매주 낸다."""
    assert "land" not in T.TAIL_PROP_TYPES, (
        "토지는 등기를 0% 보고한다(저장분 788행 전수 · 6개 시군구 전부 0) — 꼬리에 넣지 않는다"
    )
    assert "apt" in T.TAIL_PROP_TYPES, "등기를 보고하는 유형이 꼬리에서 빠지면 꼬리가 무의미하다"


def test_tail_types_are_a_subset_of_all_types():
    """대조군 — 꼬리에만 있고 평상시엔 없는 유형이 생기면 그건 오타다."""
    assert set(T.TAIL_PROP_TYPES) <= set(T.DEFAULT_PROP_TYPES)


def test_recent_months_still_fetch_every_type():
    """★최근 창에서는 land 를 빼면 안 된다 — 토지의 신호(해제 6.2%)가 거기 있다."""
    now = _at(26)
    recent = T.recent_months(now, T.RECENT_MONTHS)
    for ym in recent:
        assert T.prop_types_for(ym, recent) == T.DEFAULT_PROP_TYPES, ym


def test_tail_months_fetch_only_tail_types():
    now = _at(26)
    months, tail = T.months_for(now)
    recent = T.recent_months(now, T.RECENT_MONTHS)
    assert tail
    tail_only = [m for m in months if m not in recent]
    assert tail_only, "꼬리 달이 하나도 없다 — 이 단언이 공허하다"
    for ym in tail_only:
        assert T.prop_types_for(ym, recent) == T.TAIL_PROP_TYPES, ym


def test_scope_count_stays_within_the_measured_quota_budget():
    """★쿼터는 실측 기준으로 계산했다 — 스코프가 조용히 늘면 여기서 걸린다.

    실측: 최근 36 스코프 = 103.58초(6 시군구 × 3월 × 2유형).
    꼬리일은 60 스코프(= 36 + 6 시군구 × 4월 × 1유형)여야 한다.
    """
    now = _at(26)
    months, tail = T.months_for(now)
    recent = T.recent_months(now, T.RECENT_MONTHS)
    per_region = sum(len(T.prop_types_for(m, recent)) for m in months)
    # ★기대값을 **상수에서 파생**한다 — 리터럴로 못 박으면 문서가 권하는 정당한
    #   변경(TAIL_MONTHS 를 늘리는 것)이 테스트에서 죽는다(2026-08-27 리뷰 M5 · 위양성).
    expect_tail = (T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)
                   + (T.TAIL_MONTHS - T.RECENT_MONTHS) * len(T.TAIL_PROP_TYPES))
    assert tail and per_region == expect_tail, (per_region, expect_tail)
    weekday_months, _ = T.months_for(_at(27))
    per_region_weekday = sum(len(T.prop_types_for(m, T.recent_months(_at(27), T.RECENT_MONTHS)))
                             for m in weekday_months)
    assert per_region_weekday == T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)
    assert per_region > per_region_weekday              # ★두 모집단이 갈린다


# ══════════════════════════════════════════════════════════════
# 5. ★배선을 **실제로 태운다** — 2026-08-27 독립 리뷰 C1 봉합
# ══════════════════════════════════════════════════════════════
#
# 종전 15건은 **전부 순수 함수·상수 단언**이었고 `sync_realtx_trades` 를 임포트하는
# 테스트가 저장소 전체에 **0건**이었다. 그래서 리뷰어가 배선을 통째로 되돌렸는데
# **15개가 전부 초록**이었다(저자 재현 확인 · 4/4 SURVIVED):
#
#     루프가 `prop_types_for` 를 안 쓴다        → SURVIVED
#     `months_for` 를 안 쓴다(꼬리 폐지)         → SURVIVED
#     `recent = months`(최근/꼬리 경계 소멸)      → SURVIVED
#     `tail_included` 필드 삭제                  → SURVIVED
#
# ★어제 기록한 「변이를 함수 안에만 넣으면 5/5 CAUGHT 인데 배선은 무잠금」의
#   **세 번째 재발**이다. 그래서 여기서는 **호출 인자 삼중쌍을 직접 단언**한다.

import pytest


class _RecordingClient:
    """`get_transactions` 호출 인자를 기록만 하는 스텁."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def get_transactions(self, lawd_cd, deal_ym, prop_type="apt", **_kw):
        self.calls.append((lawd_cd, deal_ym, prop_type))
        return []          # 빈 응답 — 이 락은 **무엇을 조회하는가**만 본다

    async def close(self) -> None: ...


async def _run_and_capture(monkeypatch, when: datetime) -> set[tuple[str, str, str]]:
    """실제 `sync_realtx_trades` 를 태우고 **조회한 (시군구, 월, 유형)** 집합을 돌려준다."""
    import contextlib

    client = _RecordingClient()

    class _Sess:
        async def __aenter__(self): return object()
        async def __aexit__(self, *a): return False

    monkeypatch.setattr(T, "datetime", _FrozenDatetime(when), raising=False)
    monkeypatch.setattr("apps.api.database.session.AsyncSessionLocal", lambda: _Sess())
    monkeypatch.setattr("apps.api.integrations.molit_client.MolitClient", lambda *a, **k: client)

    async def _targets(_db): return {"41370", "41465"}
    async def _persist(*_a, **_k): return {"submitted": 0, "corrections": [], "baseline": True}
    monkeypatch.setattr("app.services.land_intelligence.realtx_store.derive_scan_targets", _targets)
    monkeypatch.setattr("app.services.land_intelligence.realtx_store.persist_scope", _persist)

    with contextlib.suppress(Exception):
        await T.sync_realtx_trades({})
    return set(client.calls)


class _FrozenDatetime:
    """`datetime.now(tz=…)` 만 고정한다(나머지는 원본에 위임)."""

    def __init__(self, when: datetime) -> None:
        self._when = when

    def now(self, tz=None):  # noqa: A003
        return self._when

    def __getattr__(self, name):
        import datetime as _dt
        return getattr(_dt.datetime, name)


@pytest.mark.asyncio
async def test_tail_day_actually_fetches_tail_months_apt_only(monkeypatch):
    """★수요일 실행이 **꼬리 달을 apt 로만** 조회하는지 — 호출 인자로 확인한다."""
    calls = await _run_and_capture(monkeypatch, _at(26))    # 수
    assert calls, "조회가 한 번도 안 일어났다 — 이 단언이 공허하다"

    recent = set(T.recent_months(_at(26), T.RECENT_MONTHS))
    tail_only = {ym for _l, ym, _p in calls} - recent
    assert tail_only, f"꼬리 달을 하나도 안 봤다: {sorted({y for _l,y,_p in calls})}"
    for lawd, ym, pt in calls:
        if ym in tail_only:
            assert pt in T.TAIL_PROP_TYPES, f"꼬리 달 {ym} 을 {pt} 로 조회했다"
    # ★두 모집단: 꼬리 달의 land 는 **없어야** 한다
    assert not [c for c in calls if c[1] in tail_only and c[2] == "land"]


@pytest.mark.asyncio
async def test_weekday_run_never_touches_tail_months(monkeypatch):
    """★대조군 — 목요일은 꼬리를 **안** 본다(두 모집단이 갈린다)."""
    calls = await _run_and_capture(monkeypatch, _at(27))    # 목
    assert calls
    recent = set(T.recent_months(_at(27), T.RECENT_MONTHS))
    assert {ym for _l, ym, _p in calls} == recent, "평일에 꼬리 달을 조회했다"


@pytest.mark.asyncio
async def test_recent_months_are_fetched_for_every_type_on_both_days(monkeypatch):
    """최근 창에서는 land 를 빼면 안 된다 — 토지의 신호(해제)가 거기 있다."""
    for day in (26, 27):
        calls = await _run_and_capture(monkeypatch, _at(day))
        recent = set(T.recent_months(_at(day), T.RECENT_MONTHS))
        for ym in recent:
            for pt in T.DEFAULT_PROP_TYPES:
                assert any(c[1] == ym and c[2] == pt for c in calls), (day, ym, pt)


@pytest.mark.asyncio
async def test_scope_count_matches_the_quota_arithmetic(monkeypatch):
    """★실제 호출 수가 계획서의 쿼터 산술과 맞는지 — 조용히 늘면 여기서 걸린다."""
    wed = await _run_and_capture(monkeypatch, _at(26))
    thu = await _run_and_capture(monkeypatch, _at(27))
    regions = 2                                   # 스텁이 준 시군구 수
    per_region = (T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)
                  + (T.TAIL_MONTHS - T.RECENT_MONTHS) * len(T.TAIL_PROP_TYPES))
    assert len(wed) == regions * per_region, (len(wed), per_region)
    assert len(thu) == regions * T.RECENT_MONTHS * len(T.DEFAULT_PROP_TYPES)
    assert len(wed) > len(thu)                    # ★두 모집단이 갈린다


# ══════════════════════════════════════════════════════════════
# 6. ★상수 결속 — 캐시 절벽과 실패 신호 (리뷰 H3 · M3)
# ══════════════════════════════════════════════════════════════

def test_tail_stays_below_the_cache_ttl_cliff():
    """★`TAIL_MONTHS` 를 늘리면 **캐시가 주간 갱신을 삼킨다** — 그런데 성공처럼 보인다.

    실측(2026-08-27):

        TAIL_MONTHS=7 → 최고령 경과 6 → TTL **24h**  (주간 조회 168h > TTL · 정상)
        TAIL_MONTHS=8 → 최고령 경과 7 → TTL **720h** (★주간 조회가 캐시에 삼켜진다)

    그때 `submitted` 는 정상적으로 올라가므로 로그만으로는 안 드러난다.
    """
    from apps.api.integrations.molit_client import _RECENT_MONTHS_SHORT_TTL

    oldest_elapsed = T.TAIL_MONTHS - 1          # 최신 달이 경과 0
    assert oldest_elapsed <= _RECENT_MONTHS_SHORT_TTL, (
        f"꼬리 {T.TAIL_MONTHS}개월의 최고령 달은 경과 {oldest_elapsed} 로 "
        f"_RECENT_MONTHS_SHORT_TTL({_RECENT_MONTHS_SHORT_TTL})을 넘는다 → TTL 30일이 되어 "
        "주간 조회가 캐시에 삼켜진다. 꼬리를 늘리려면 그 상수를 함께 올려라."
    )


def test_the_cliff_lock_is_not_vacuous():
    """★대조군 — 절벽이 실재하는지 실제 함수로 확인한다(상수 비교만으로는 공허하다)."""
    from datetime import datetime

    from apps.api.integrations.molit_client import _deal_ymd_ttl

    ref = datetime(2026, 8, 26, tzinfo=UTC)
    safe = T.recent_months(ref, T.TAIL_MONTHS)[-1]
    over = T.recent_months(ref, T.TAIL_MONTHS + 1)[-1]
    week = 168 * 3600
    assert _deal_ymd_ttl(safe, now=ref) <= week, "현재 꼬리가 이미 절벽 위다"
    assert _deal_ymd_ttl(over, now=ref) > week, "★절벽이 없다 — 이 락이 공허하다"


def test_fetch_errors_are_not_reported_as_ok():
    """★종전엔 전 스코프가 429 로 실패해도 `status="ok"` 였다(리뷰 M3)."""
    import ast
    import inspect
    import textwrap

    # ★소스 문자열로 보면 **이 수정을 설명하는 내 주석**에 걸린다(실제로 걸렸다 —
    #   변이가 SURVIVED 했다). 판정은 **파서로** 한다.
    fn = ast.parse(textwrap.dedent(inspect.getsource(T.sync_realtx_trades))).body[0]

    targets = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Subscript)
                and isinstance(t.slice, ast.Constant) and t.slice.value == "status"
                for t in n.targets)
    ]
    assert targets, "status 대입식을 못 찾았다 — 조회기 의심(공허한 참 방지)"
    keys = {n.slice.value for a in targets for n in ast.walk(a.value)
            if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)}
    assert "fetch_errors" in keys, f"status 판정이 fetch_errors 를 안 본다: {sorted(keys)}"
    assert "persist_errors" in keys, f"status 판정이 persist_errors 를 안 본다: {sorted(keys)}"
