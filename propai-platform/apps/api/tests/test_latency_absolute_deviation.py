"""latency **절대편차** 판정 락 — 비율 방식의 표본 잡음을 우회한다.

## 왜 이 축이 필요했나 (라이브 7일 전수 · 2026-08-27)

같은 지연 풀에서 `n=20` 을 **두 번 뽑아** 비교하면(= **회귀가 전혀 없는** 상태)
그것만으로 발화한다: **p95 23.0%** · p75 14.9% · p50 14.7%.
★백분위를 낮추는 것으로는 안 된다 — `tiles/vworld` 계열은 **어느 백분위에서도 20%대**다.

★단순 절대임계(10초)도 아니다 — 발화 29건 중 **69%가 상시 느린 4개 route** 다
(`/api/v1/zoning/parcel-boundaries` 는 판정 16회 중 **14회** 발화).

→ **그 route 자신의 평소값 대비 편차**. 07:05Z 실장애 버스트 **5/5 포착** ·
  그 창에 정상이던 `/api/v1/auth/login` 은 **미발화** · 하루 **2.1건**.

## ★이 파일이 잠그는 것과 **안 잠그는** 것

잠근다: 판정 함수 · 평소값 산출 · **배선**(두 축이 실제로 결과에 실리는가) · 상수 결속.
안 잠근다: SQL 의미(실 Postgres 락은 `test_latency_absolute_deviation_pg.py`) ·
          임계 5000ms 가 **제품적으로 옳은지**(그건 SLO 결정이지 테스트 대상이 아니다).
"""
from __future__ import annotations

import pytest

from app.services.growth import analyzer as az

# ══════════════════════════════════════════════════════════════
# 1. 평소값 — 중앙값이고, 창이 모자라면 **판정하지 않는다**
# ══════════════════════════════════════════════════════════════


def test_typical_is_median_not_mean():
    """★평균이면 장애 시간창이 평소값을 끌어올려 **다음 장애를 놓친다**.

    ★값을 못 박지 않고 **성질**을 단언한다 — `_percentile` 은 nearest-rank 라
      짝수 개에서 어느 쪽 중앙값을 고를지가 구현 세부이고, 그것에 결속하면
      정규화만 바꿔도 깨지는 취약한 락이 된다.
    """
    calm = [3000.0, 3100.0, 3200.0]
    hist = [*calm, 66230.0]                      # 마지막이 장애
    t = az.typical_p95(hist)
    assert t is not None
    # ★평소값이 **정상 구간 안**에 있어야 한다(장애에 안 끌려감)
    assert min(calm) <= t <= max(calm), f"평소값 {t} 가 정상 구간 밖 — 장애에 끌려갔다"
    assert t < sum(hist) / len(hist) / 5, "평균에 끌려갔다 — 다음 장애를 놓친다"

    # ★★두 모집단 — 장애가 **하나 더** 들어와도 평소값이 흔들리면 안 된다
    t2 = az.typical_p95([*hist, 70000.0])
    assert min(calm) <= t2 <= max(calm), f"장애 2건에 평소값이 밀렸다: {t2}"


def test_typical_withholds_when_too_few_windows():
    """★한두 창으로 「평소」를 말하면 그 자체가 잡음 — 비율 방식과 같은 문제다."""
    for n in range(az.LATENCY_TYPICAL_MIN_WINDOWS):
        assert az.typical_p95([100.0] * n) is None, f"창 {n}개로 평소값을 만들었다"
    # ★대조군 — 하한을 채우면 값이 나온다(위 단언이 공허하지 않다)
    assert az.typical_p95([100.0] * az.LATENCY_TYPICAL_MIN_WINDOWS) == 100.0


def test_typical_min_windows_is_above_one():
    """★하한이 1 이면 「평소」가 곧 「직전 한 번」이라 비율 방식과 같아진다."""
    assert az.LATENCY_TYPICAL_MIN_WINDOWS >= 3


# ══════════════════════════════════════════════════════════════
# 2. ★판정 — 라이브 버스트를 넣어 태운다(합성 숫자가 아니라 실측값)
# ══════════════════════════════════════════════════════════════

#: 2026-08-27T07:05Z 실장애 버스트 실측 (평소값, 버스트 p95)
_BURST = {
    "/api/v1/zoning/parcel-boundaries": (23524.0, 66230.0),
    "/api/v1/analysis-ledger/history": (3045.0, 13763.0),
    "/api/v1/store/projects": (3202.0, 12340.0),
    "/api/v1/auth/is-admin": (3169.0, 11408.0),
    "/api/v1/auth/me": (3210.0, 11309.0),
}
#: 같은 창에 **정상이던** route — 발화하면 위양성이다
_CALM = {"/api/v1/auth/login": (594.0, 594.0)}


@pytest.mark.parametrize(("route", "pair"), sorted(_BURST.items()))
def test_real_burst_is_caught(route, pair):
    """★실장애 5/5 를 잡는가 — 합성 입력이 아니라 라이브 실측값이다."""
    typical, p95 = pair
    assert az.classify_latency_absolute(p95, typical) == "warn", (route, typical, p95)


@pytest.mark.parametrize(("route", "pair"), sorted(_CALM.items()))
def test_calm_route_does_not_fire(route, pair):
    """★★두 모집단 — 같은 창에 정상이던 route 는 **울리면 안 된다**."""
    typical, p95 = pair
    assert az.classify_latency_absolute(p95, typical) is None, (route, typical, p95)


def test_chronically_slow_route_is_auto_excluded():
    """★고정 임계였다면 매시 울렸을 route 가, 자기 기준선 덕에 조용하다.

    `/api/v1/zoning/parcel-boundaries` 는 평소가 이미 23.5초다 — 고정 10초 임계로는
    **판정 16회 중 14회(88%)** 울렸다(라이브 실측). 자기 기준선이면 평소일 때 조용하다.
    """
    typical = 23524.0
    assert az.classify_latency_absolute(23600.0, typical) is None, "평소인데 울렸다"
    assert az.classify_latency_absolute(66230.0, typical) == "warn", "장애인데 안 울렸다"


def test_boundary_is_strict_not_inclusive():
    """★경계를 **정각**에서 태운다 — `>` 를 `>=` 로 바꾸는 변이가 여기서 죽는다.

    ±1 로만 태우면 경계를 안 밟아 그 변이가 **생존**한다(#902 의 F4 와 같은 실패라
    한 번 더 겪었다).
    """
    t = 3000.0
    exact = t + az.LATENCY_ABSOLUTE_DEVIATION_MS
    assert az.classify_latency_absolute(exact, t) is None, "경계 정각에 울렸다(>= 회귀)"
    assert az.classify_latency_absolute(exact + 1, t) == "warn"
    assert az.classify_latency_absolute(exact - 1, t) is None


def test_unknown_typical_does_not_fire():
    """★「모름」을 「정상」으로도 「장애」로도 읽지 않는다 — 판정하지 않는다."""
    assert az.classify_latency_absolute(99999.0, None) is None


def test_threshold_is_bounded_both_ways():
    """★경계를 양방향으로 — 너무 낮으면 잡음, 너무 높으면 버스트를 놓친다."""
    assert az.LATENCY_ABSOLUTE_DEVIATION_MS >= 1000, "1초 미만이면 정상 변동에 울린다"
    # ★상한은 **실측으로** 정한다: +10초면 위 5개 중 2개만 잡힌다(라이브 확인)
    smallest = min(p - t for t, p in _BURST.values())
    assert smallest >= az.LATENCY_ABSOLUTE_DEVIATION_MS, (
        f"임계 {az.LATENCY_ABSOLUTE_DEVIATION_MS} 가 실장애 최소 편차 {smallest} 보다 크다 "
        "— 버스트를 놓친다"
    )


# ══════════════════════════════════════════════════════════════
# 3. ★비율과 절대편차는 **서로를 대체하지 않는다**
# ══════════════════════════════════════════════════════════════


def test_two_axes_catch_different_things():
    """★`/api/v1/ai/status`: 평소 70ms → 3,282ms = **47배**인데 편차는 3.2초.

    비율은 잡고 절대편차는 못 잡는다. **둘 다 필요하다**는 것을 잠근다 —
    한 축을 지우면 이 단언이 죽는다.
    """
    typical, p95 = 70.0, 3282.0
    assert az.classify_latency_absolute(p95, typical) is None, "절대편차가 이걸 잡으면 안 된다"
    assert az._classify_latency(p95, typical) == "warn", "비율은 이걸 잡아야 한다"

    # ★역방향 — 비율은 못 잡고 절대편차만 잡는 경우가 실제로 있는가
    t2, p2 = 23524.0, 33000.0        # 1.40배 — 비율 임계 1.5 미만
    assert az._classify_latency(p2, t2) is None
    assert az.classify_latency_absolute(p2, t2) == "warn"
