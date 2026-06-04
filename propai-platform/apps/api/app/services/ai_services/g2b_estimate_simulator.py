"""나라장터 적격심사 사정율 시뮬레이터 — 복수예비가 추첨 메커니즘 몬테카를로.

한국 공공입찰(적격심사) 예정가격 결정 구조를 그대로 시뮬:
 1) 발주처가 기초금액 공개 → 기초금액 ±변동폭(공사 통상 ±2%)으로 복수예비가 15개 생성
 2) 입찰자 추첨번호로 4개 예비가 선택 → 평균 = 예정가격(예가)
 3) 예정가격 × 낙찰하한율 = 적격(낙찰가능) 최저선
예정가격이 추첨에 따라 확률적으로 변하므로, 투찰율별 '적격(낙찰가능) 확률'을 산출하고
목표 안전확률을 만족하는 최저 투찰가('적정 투찰가')를 역산한다.

데이터 불요(공식 규칙 기반). 향후 조달청 복수예비가·개찰순위 실데이터로 변동폭·하한율 보정.
"""

from __future__ import annotations

import random
import statistics
from typing import Any

# 공종별 낙찰하한율(적격심사, 대표값). 실제는 금액·발주처별 상이 → 파라미터로 조정.
DEFAULT_FLOOR_RATE = {
    "공사": 0.87745,
    "용역": 0.85,
    "물품": 0.844,
}
DEFAULT_VARIATION = {"공사": 0.02, "용역": 0.03, "물품": 0.03}


def _as_rate(v: float | None) -> float | None:
    """낙찰가율 입력을 소수비율로 정규화(90.82 → 0.9082, 0.9082 → 0.9082)."""
    if v is None:
        return None
    return v / 100.0 if v > 2 else v


def simulate_estimate(
    base_price: float,
    *,
    bid_type: str = "공사",
    prelim_count: int = 15,
    draw_count: int = 4,
    variation: float | None = None,
    floor_rate: float | None = None,
    target_win_prob: float = 0.85,
    iterations: int = 10000,
    empirical_mean: float | None = None,   # 실적 평균 낙찰가율(% 또는 소수)
    empirical_min: float | None = None,
    empirical_max: float | None = None,
    empirical_count: int | None = None,
) -> dict[str, Any]:
    """복수예비가 추첨 시뮬 → 예정가격 분포·적격확률 곡선·적정 투찰가 산출."""
    if base_price <= 0:
        return {"error": "기초금액(base_price)이 필요합니다."}

    var = variation if variation is not None else DEFAULT_VARIATION.get(bid_type, 0.02)
    fr = floor_rate if floor_rate is not None else DEFAULT_FLOOR_RATE.get(bid_type, 0.87745)
    iterations = max(1000, min(50000, iterations))

    rnd = random.Random(20260605)  # 재현성(고정 시드)
    floors: list[float] = []   # 예정가격 × 하한율(적격 최저선) 표본
    yega: list[float] = []     # 예정가격 표본
    for _ in range(iterations):
        prelims = [base_price * (1 + rnd.uniform(-var, var)) for _ in range(prelim_count)]
        drawn = rnd.sample(prelims, min(draw_count, prelim_count))
        y = sum(drawn) / len(drawn)
        yega.append(y)
        floors.append(y * fr)
    floors.sort()
    n = len(floors)

    def quantile(sorted_vals: list[float], q: float) -> float:
        i = min(n - 1, max(0, int(q * n)))
        return sorted_vals[i]

    # 적정 투찰가 = 적격확률이 목표(예 85%) 되는 최저 투찰가 = floors의 target 분위수
    rec_bid = quantile(floors, target_win_prob)
    rec_rate = rec_bid / base_price

    # 투찰율별 적격확률 곡선(낙찰하한선 부근 스캔)
    lo = fr - 0.01
    curve = []
    r = lo
    while r <= 1.0001:
        bid = base_price * r
        # 적격확률 = P(투찰가 ≥ 예정가격×하한율) = P(floor ≤ bid)
        p = sum(1 for f in floors if f <= bid) / n
        curve.append({"bid_rate": round(r, 4), "bid_price": round(bid), "p_valid": round(p, 3)})
        r += 0.0025

    ymean = statistics.mean(yega)
    ystd = statistics.pstdev(yega)

    # ── 실적(낙찰가율) 보정: 실제 낙찰자 투찰 분포로 적정투찰율 재조정 ──
    calibrated: dict[str, Any] | None = None
    e_avg = _as_rate(empirical_mean)
    if e_avg is not None:
        e_min = _as_rate(empirical_min) or e_avg
        e_max = _as_rate(empirical_max) or e_avg
        # 경쟁력: 평균보다 약간 낮게(min 쪽 40%) — 단 적격하한(메커니즘 적정율) 이상 유지
        competitive = e_avg - 0.4 * max(0.0, e_avg - e_min)
        cal_rate = max(competitive, rec_rate)
        # 실적 분포 내 위치(적격확률은 메커니즘 곡선에서 조회)
        cal_p = sum(1 for f in floors if f <= base_price * cal_rate) / n
        calibrated = {
            "empirical_band": {"min_pct": round(e_min * 100, 2), "avg_pct": round(e_avg * 100, 2),
                               "max_pct": round(e_max * 100, 2), "count": empirical_count},
            "calibrated_bid_rate": round(cal_rate, 4),
            "calibrated_bid_rate_pct": round(cal_rate * 100, 3),
            "calibrated_bid_price": round(base_price * cal_rate),
            "calibrated_win_prob": round(cal_p, 3),
            "basis": "실적 낙찰가율(g2b_award_stats) 보정 — 평균보다 경쟁적, 적격하한 이상 유지",
        }

    return {
        "bid_type": bid_type,
        "base_price": round(base_price),
        "variation_pct": round(var * 100, 2),
        "floor_rate_pct": round(fr * 100, 3),
        "prelim_count": prelim_count, "draw_count": draw_count,
        "iterations": iterations,
        "yega_mean": round(ymean), "yega_std": round(ystd),
        "yega_p10_rate": round(quantile(sorted(yega), 0.10) / base_price, 4),
        "yega_p50_rate": round(quantile(sorted(yega), 0.50) / base_price, 4),
        "yega_p90_rate": round(quantile(sorted(yega), 0.90) / base_price, 4),
        "target_win_prob": target_win_prob,
        "recommended_bid_price": round(rec_bid),
        "recommended_bid_rate": round(rec_rate, 4),
        "recommended_bid_rate_pct": round(rec_rate * 100, 3),
        "calibrated": calibrated,   # 실적 낙찰가율 보정(있을 때)
        "curve": curve,
        "note": (
            f"기초금액 ±{round(var*100,1)}% 복수예비가 {prelim_count}개 중 {draw_count}개 추첨 평균=예정가격, "
            f"낙찰하한율 {round(fr*100,2)}% 적용. 적정 투찰가는 적격확률 {int(target_win_prob*100)}% 기준 최저가. "
            "공식 규칙 기반 v1 — 조달청 실데이터로 변동폭·하한율 보정 예정."
        ),
    }
