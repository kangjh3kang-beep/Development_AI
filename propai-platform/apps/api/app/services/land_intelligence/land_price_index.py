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
