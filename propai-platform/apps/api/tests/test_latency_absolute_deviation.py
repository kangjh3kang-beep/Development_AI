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

# ---------------------------------------------------------------------------
# ★리뷰 생존변이 봉합 — 중앙값을 **양방향**으로 잠근다
#
#   종전 락은 `min(calm) <= t <= max(calm)` 이었고 이것은 **p0(최솟값)에서도 참**이라
#   `p50 → p0` 변이가 SURVIVED 했다. 잠기지 않은 그 방향이 하필
#   *"평소값이 너무 낮아짐 = 위양성 폭증"* — **이 변경이 고치겠다고 선언한 바로 그 방향**이다.
#   방향이 있는 결함에는 방향이 있는 단언을 건다(파티션형).
# ---------------------------------------------------------------------------

#: 두 방향을 **동시에** 가르는 픽스처. 산포(1,000~10,000)가 임계(5,000ms)보다 커야
#: 평소값이 낮게 붕괴했을 때 실제로 위양성이 난다 — 산포가 임계보다 작으면
#: `p0` 변이를 넣어도 아무 일이 안 일어나 **락이 공허해진다**(실측으로 고른 값).
_SPREAD = [1000.0, 2000.0, 8000.0, 9000.0, 10000.0]   # p50=8,000 · p0=1,000 · p100=10,000


def test_typical_is_interior_not_an_extreme():
    """평소값은 **양쪽 극단 어느 쪽도 아니어야** 한다.

    · 낮은 쪽으로 붕괴 → 위양성 폭증(`p0`·`p25` 변이를 죽인다)
    · 높은 쪽으로 끌려감 → 장애 미탐(`p100`·평균 변이를 죽인다)
    """
    t = az.typical_p95(_SPREAD)
    assert t is not None, "평소값이 없다 — 창 수 하한이 잘못 걸렸다"
    assert t > min(_SPREAD), f"평소값 {t} 가 최솟값으로 붕괴 — **위양성 폭증** 방향이 열렸다"
    assert t < max(_SPREAD), f"평소값 {t} 가 최댓값에 끌려감 — **장애 미탐** 방향이 열렸다"


def test_typical_bias_is_locked_by_its_effect_not_its_name():
    """★단언을 **효과**에 건다 — *"중앙값을 쓴다"* 가 아니라 *"그래서 어떻게 되는가"*.

    같은 실행에서 **두 모집단**을 가른다(한 모집단만 보면 *"아무것도 안 하는 구현"* 과
    *"올바른 구현"* 을 구별할 수 없다):

      · 평소 범위 안의 관측 → **발화하지 않는다**  ← 평소값이 낮게 붕괴하면 깨진다
      · 진짜 버스트          → **발화한다**        ← 평소값이 높게 끌려가면 깨진다
    """
    t = az.typical_p95(_SPREAD)
    normal = 9000.0   # 평소 범위 안(평소값 8,000 + 임계 5,000 = 13,000 미만)
    # ★**리터럴로 못 박는다** — 종전엔 `8000 + az.LATENCY_ABSOLUTE_DEVIATION_MS + 1000` 이라
    #   기대값이 **내가 변이시키려는 바로 그 상수에서 파생**됐다. 그러면 임계를 5,000 → 50,000
    #   으로 **올려도** burst 가 같이 커져 이 단언은 초록이다(자기지시적 기대값).
    #   실측: 그 변이는 **형제 락**(실장애 최소 편차 상한)이 잡고 있었을 뿐,
    #   **이 락 자신은 통과시켰다** — 동료 development-ai-29 가 `#900`·`#925` 에서
    #   같은 형태를 실증해 알려 준 축이다.
    #   ★자문: *"이 가드의 기대값이 내가 깎으려는 그 상수에서 나오는가?"*
    burst = 14000.0   # 8,000 + 5,000 = 13,000 초과 → 임계가 커지면 **이 락이 직접 빨개진다**

    assert az.classify_latency_absolute(normal, t) is None, (
        "평소 범위 안의 관측이 발화했다 — 평소값이 낮은 쪽으로 붕괴한 것이다(위양성)")
    assert az.classify_latency_absolute(burst, t) is not None, (
        "진짜 버스트를 놓쳤다 — 평소값이 높은 쪽으로 끌려간 것이다(미탐)")


# ---------------------------------------------------------------------------
# ★H4 봉합 — `triggers`·`typical_p95` 의 **소비처 0** 을 끝낸다
#
#   두 필드는 `metrics_json` 에 **쓰이기만** 하고 읽는 곳이 0건이었다(실측:
#   `typical_p95` 3건 전부 analyzer.py 안 · `typical_windows` 1건 = 쓰기뿐).
#   그 결과 절대편차 **단독** 발화가 화면에 `p95 33,000ms (이전 baseline 23,524ms)`
#   = **1.40배**로 나가, 비율 임계(1.5배) **미만**인 수치 옆에 `warn` 이 붙었다.
#   ★코드 주석이 *"안 남기면 왜 울렸는지 알 수 없다"* 라고 적어 놓고 표면까지 안 보낸 것.
# ---------------------------------------------------------------------------


def _ins(triggers, typical, windows=5, sev="warn"):
    return {"insight_type": "latency_regression", "severity": sev,
            "metrics_json": {"key": "/api/v1/zoning/parcel-boundaries", "p95_ms": 33000.0,
                             "prev_baseline_p95": 23524.0, "samples": 20,
                             "triggers": triggers, "typical_p95": typical,
                             "typical_windows": windows}}


def test_narrative_says_which_axis_fired_two_populations():
    """★**두 모집단**이 서로 다른 문장을 내야 한다.

    한쪽만 단언하면 *"항상 같은 문자열을 붙이는 구현"* 이 통과한다.
    """
    ratio_only = az._rule_narrative(_ins(["ratio"], 23000.0))
    abs_only = az._rule_narrative(_ins(["absolute"], 23524.0))

    assert "비율" in ratio_only and "절대편차" not in ratio_only, (
        f"비율 단독 발화인데 문장이 축을 잘못 말한다: {ratio_only}")
    assert "절대편차" in abs_only and "비율" not in abs_only, (
        f"절대편차 단독 발화인데 문장이 축을 잘못 말한다: {abs_only}")
    assert ratio_only != abs_only, "두 축이 **같은 문장**을 낸다 — 축을 읽지 않는 구현이다"


def test_narrative_carries_typical_value():
    """평소값이 문장에 **실려야** 한다 — 키만 있고 값이 안 실리는 것을 막는다."""
    out = az._rule_narrative(_ins(["absolute"], 23524.0))
    assert "23524" in out.replace(",", ""), f"평소값이 문장에 없다: {out}"


def test_unknown_typical_is_not_disguised_as_zero():
    """★「모름」을 **유효값으로 위장하지 않는다.**

    평소값이 `None`(창 부족)인데 `0ms` 로 그리면 *"평소가 0ms 인 경로"* 라는
    **관측이 되어 버린다** — 면제 확정 0원과 미조회 0원을 구별 못 하게 만든 것과 같은 결함.
    """
    out = az._rule_narrative(_ins(["absolute"], None, windows=2))
    assert "판정 불가" in out, f"「모름」이 판정 불가라고 말하지 않는다: {out}"
    assert "평소값 0ms" not in out, f"「모름」이 0ms 로 위장됐다: {out}"


def test_non_firing_row_gets_no_axis_phrase():
    """발화가 아니면(`triggers` 빈 목록) 축 문구를 **붙이지 않는다**.

    ★음성 대조군 — 이것이 없으면 *"항상 문구를 붙이는 구현"* 이 위 락을 전부 통과한다.
    """
    out = az._rule_narrative(_ins([], 23524.0, sev="info"))
    assert "발화 축" not in out, f"발화가 아닌 행에 축 문구가 붙었다: {out}"


def test_unknown_axis_code_is_shown_raw_not_hidden():
    """모르는 축 코드는 **감추지 않고 원문 그대로** — 숨기면 새 축이 조용히 사라진다."""
    out = az._rule_narrative(_ins(["ratio", "brand_new_axis"], 23524.0))
    assert "brand_new_axis" in out, f"모르는 축이 화면에서 사라졌다: {out}"
