"""시점수정 시계열 무결성 — **거짓 값을 만들지 않는다.**

## 왜 (2026-09-07 라이브 적발)

라이브 응답 `land_price_trend.monthly[].period` 전수를 보니

    기간 고유 **1개** / 전체 24개 — 전부 `202607`

「최근 24개월」이 아니라 **같은 달의 24개 지역**이었다. `rate_series_from_rows` 의
지역 필터가 안 맞으면 `_collect(None)` 폴백이 **전체 행**을 돌려주는 fail-open 이었다.

그 24개를 `∏(1+r/100)` 로 곱해 **1.0414** 를 만들고 **채택 단가에 곱했다**
→ 토지가액이 근거 없이 **+4.14%** 부풀었다.

### 산수 확증(추론 아님)

    월 변동률 범위 0.05 ~ 0.267%  → 12개월 최대 합 **3.20%**
    화면 연도별 2024 **+80.68%**   → 최대치로도 **302개 항목** 필요(12개월로 불가)
"""

from __future__ import annotations

from app.services.external_api.reb_client import (
    cumulative_factor_from_rows,
    distinct_period_count,
    rate_series_from_rows,
    rate_series_scope,
)


def _row(period: str, rate: float, region: str) -> dict:
    return {"WRTTIME_IDTFR_ID": period, "DTA_VAL": rate, "CLS_NM": region, "ITM_NM": "지가변동률"}


def _one_month_many_regions(n: int = 24) -> list[dict]:
    """★라이브에서 실제로 온 형태 — 같은 달, 여러 지역."""
    regs = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
            "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
    return [_row("202607", 0.1 + (i % 5) * 0.03, regs[i % len(regs)]) for i in range(n)]


def _real_series(months: int = 24, region: str = "경기") -> list[dict]:
    out = []
    y, m = 2026, 7
    for _ in range(months):
        out.append(_row(f"{y:04d}{m:02d}", 0.15, region))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


# ── 판정 거부 ────────────────────────────────────────────────────────────────

def test_같은달_여러지역이면_누적계수를_만들지_않는다() -> None:
    """★핵심 — 이게 없으면 지역 개수만큼의 거듭제곱이 「24개월 누적」으로 나간다."""
    rows = _one_month_many_regions(24)
    # 필터가 안 맞는 지역을 줘 fail-open 폴백을 태운다(라이브 재현).
    f = cumulative_factor_from_rows(rows, "없는지역", months=24)
    assert f is None, (
        f"고유 기간 1개인 24행으로 누적계수 {f} 를 만들었다 — "
        "「24개월 누적」이 아니라 지역 개수만큼의 거듭제곱이다"
    )


def test_진짜_24개월이면_계수를_만든다() -> None:
    """★위양성 축 — 이 축이 없으면 «항상 None» 인 구현이 만점을 받는다."""
    rows = _real_series(24, "경기")
    f = cumulative_factor_from_rows(rows, "경기", months=24)
    assert f is not None and 1.0 < f < 1.3, f"정상 시계열인데 판정을 거부했다: {f}"


def test_임계가_요청_개월수에_결속된다() -> None:
    """★독립 리뷰 적발(MEDIUM-7) — 임계를 `< 2` 로 바꿔도 **통과**했다(변이 SURVIVED).

    종전 락은 «고유 기간 **1개**»만 잡아서, 「요청 개월 수만큼 있어야 한다」는 **계약
    자체가 무잠금**이었다. 고유 3개 × 8지역 = 24행짜리 오염도 통과했다.
    → **두 모집단**: `distinct == months-1`(거부) ↔ `distinct == months`(허용).
    """
    MONTHS = 12
    # ① 고유 11개월 × 지역 중복으로 12행 — **거부**여야 한다.
    short = _real_series(MONTHS - 1, "경기") + [_row("202607", 0.15, "경기")]
    assert len(short) == MONTHS
    f_short = cumulative_factor_from_rows(short, "경기", months=MONTHS)
    assert f_short is None, (
        f"고유 {MONTHS - 1}개월인데 {MONTHS}개월 누적계수 {f_short} 를 만들었다 — "
        "임계가 요청 개월 수에 결속되지 않았다(«고유 1개»만 막는 구현이 통과한다)")
    # ② 고유 12개월 — **허용**이어야 한다(위양성 축).
    ok = _real_series(MONTHS, "경기")
    assert cumulative_factor_from_rows(ok, "경기", months=MONTHS) is not None


def test_고유기간_계수는_지역중복을_센다() -> None:
    assert distinct_period_count([("202607", 0.1)] * 24) == 1
    assert distinct_period_count([(f"2026{m:02d}", 0.1) for m in range(1, 13)]) == 12
    assert distinct_period_count([]) == 0


# ── 범위 라벨 ────────────────────────────────────────────────────────────────

def test_범위_라벨이_실제_필터_결과를_말한다() -> None:
    """★화면이 라벨을 지어내지 않게 — 값과 함께 «무엇인지»를 준다."""
    rows = _real_series(24, "경기")
    assert rate_series_scope(rows, "경기") == "경기"
    # 매칭 실패 시 「경기」라고 말하면 안 된다(거짓 라벨).
    scope = rate_series_scope(rows, "제주")
    assert scope != "제주", "필터가 안 맞았는데 그 지역명을 라벨로 돌려준다"
    assert "미상" in scope or scope == "전국", scope


def test_시계열이_지역으로_실제_갈린다() -> None:
    """★두 모집단 — 필터가 값을 바꾸지 않으면 필터가 아니다."""
    rows = _real_series(12, "경기") + [_row(f"2026{m:02d}", 9.9, "서울") for m in range(1, 13)]
    gg = rate_series_from_rows(rows, "경기")
    se = rate_series_from_rows(rows, "서울")
    assert len(gg) == 12 and len(se) == 12, f"경기 {len(gg)} 서울 {len(se)}"
    assert {r for _, r in gg} != {r for _, r in se}, "지역이 달라도 같은 값이 나온다 — 필터 무효"
