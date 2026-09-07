"""지가변동률 기반 시점수정 — 공시기준일(1/1)→가격시점 누적 변동계수.

공시지가기준법의 '시점수정'은 표준지 공시기준일부터 가격시점까지 지가변동률을 누적 적용.
한국부동산원 R-ONE 지가변동률(시도별 연간) 근사 테이블을 사용(고정 1.02 대체).
실시간 API 연동 시 _ANNUAL_RATE를 동적 갱신하면 됨.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

# 시도별 연간 지가변동률(근사, R-ONE 최근추세 기반). 실데이터 연동 시 대체.
_ANNUAL_RATE: dict[str, float] = {
    "서울": 0.025, "경기": 0.022, "인천": 0.020,
    "부산": 0.012, "대구": 0.008, "대전": 0.015, "광주": 0.012,
    "울산": 0.010, "세종": 0.018, "강원": 0.012, "충북": 0.013,
    "충남": 0.013, "전북": 0.010, "전남": 0.010, "경북": 0.009,
    "경남": 0.010, "제주": 0.012,
}
_DEFAULT_RATE = 0.018  # 전국 평균 근사


def _lookup_rate(address: str) -> tuple[float, str]:
    addr = address or ""
    for sido, rate in _ANNUAL_RATE.items():
        if sido in addr:
            return rate, f"{sido} 연 지가변동률 {rate*100:.1f}% 적용"
    return _DEFAULT_RATE, f"전국 평균 지가변동률 {_DEFAULT_RATE*100:.1f}% 적용"


def _sido_of(address: str) -> str:
    for sido in _ANNUAL_RATE:
        if sido in (address or ""):
            return sido
    return ""


async def time_adjust_factor_async(address: str = "", base_year: int = 2025) -> dict[str, Any]:
    """R-ONE 지가변동률 실데이터로 시점수정(가용 시), 실패 시 근사 테이블 폴백."""
    try:
        from app.services.external_api.reb_client import (
            cumulative_factor_from_rows,
            fetch_land_price_changes,
            reb_ready,
        )
        if reb_ready():
            rows = await fetch_land_price_changes(months=24)
            if rows:
                f = cumulative_factor_from_rows(rows, _sido_of(address))
                # sane-range(24개월 누적 ±30% 이내)만 채택, 벗어나면 근사 폴백
                if f and 0.7 < f < 1.3:
                    return {"factor": f, "annual_rate": None, "elapsed_years": None,
                            "rationale": f"R-ONE 지가변동률 실데이터 최근 24개월 누적 시점수정 {f}", "source": "R-ONE"}
    except Exception:  # noqa: BLE001
        pass
    out = time_adjust_factor(address, base_year)
    out["source"] = "근사테이블"
    return out


def time_adjust_factor(address: str = "", base_year: int = 2025, now: datetime | None = None) -> dict[str, Any]:
    """공시기준일(base_year-01-01)→가격시점 지가변동률 누적 시점수정계수."""
    rate, rationale = _lookup_rate(address)
    cur = now or datetime.now()
    base = date(base_year, 1, 1)
    elapsed_yrs = max(0.0, (cur.date() - base).days / 365.25)
    factor = (1 + rate) ** elapsed_yrs
    return {
        "factor": round(factor, 4),
        "annual_rate": rate,
        "elapsed_years": round(elapsed_yrs, 2),
        "rationale": f"{rationale} × 경과 {elapsed_yrs:.2f}년 → 시점수정 {factor:.4f}",
    }


async def monthly_rate_series_async(
    address: str = "", months: int = 24,
) -> tuple[list[tuple[str, float]], str]:
    """월별 지가변동률 시계열 `[(YYYYMM, 변동률%), …]` + **출처 라벨**.

    ## 왜 이 함수가 필요한가 (2026-09-07 실측)

    `land_dong_stats.land_market_stats(rate_series=…)` 는 **거래별 시점수정을 이미
    구현**해 두었는데, 그 인자를 넘기는 **소비처가 0건**이었다(`git grep rate_series`
    → 정의 파일 밖 0). 그래서 라이브 응답이 항상 `"time_adjusted": false` 였다.

    ★그리고 **비대칭**이 있었다 — 공시지가기준법(방법1)은 R-ONE 이 없으면
    `time_adjust_factor` 의 **근사테이블로 폴백**해 시점수정을 하는데, 시장통계(방법2)는
    폴백이 없어 **통째로 꺼졌다.** 두 방법을 나란히 놓고 비교하면서 한쪽만 시점을
    맞춘 셈이다.

    ★★근사 폴백은 **월별 변동을 모른다** — 연율을 12로 나눠 균등 배분한다. 그건
    «각 달이 실제로 얼마나 움직였는가» 가 아니라 «평균적으로 이만큼» 이다. 그래서
    **출처 라벨을 함께 돌려주고**, 소비처가 그것을 표면까지 싣게 한다(무음 승격 금지).

    Returns:
        (시계열, 출처) — 시계열이 비면 소비처는 시점수정을 **하지 않는다**(지어내지 않음).
    """
    from datetime import UTC, datetime

    try:
        from app.services.external_api.reb_client import (
            fetch_land_price_changes,
            rate_series_from_rows,
            reb_ready,
        )
        if reb_ready():
            rows = await fetch_land_price_changes(months=months)
            if rows:
                series = rate_series_from_rows(rows, _sido_of(address))
                if series:
                    return series, "R-ONE 지가변동률(실데이터)"
    except Exception:  # noqa: BLE001 — 외부 실패는 근사 폴백(무중단)
        pass

    # ── 근사 폴백 — 연율을 균등 배분한다. ★«월별 실제 변동»이 아님을 라벨이 말한다.
    annual, _why = _lookup_rate(address)
    if not annual:
        return [], "지가변동률 미확보 — 시점수정 미적용"
    monthly_pct = (annual / 12.0) * 100.0
    now = datetime.now(UTC)
    y, mo = now.year, now.month
    out: list[tuple[str, float]] = []
    for _ in range(months):
        out.append((f"{y:04d}{mo:02d}", monthly_pct))
        mo -= 1
        if mo == 0:
            mo = 12
            y -= 1
    out.reverse()
    return out, f"근사테이블(연 {annual * 100:.1f}% 균등배분 — 월별 실제 변동 아님)"
