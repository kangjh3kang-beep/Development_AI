"""낙찰가능가(공매) 추정 — 감정가 기반 예상 낙찰가 범위 산정.

G2B 입찰분석의 낙찰가율(award_rate) 개념을 공매 도메인으로 차용한다:
  예상낙찰가 = 감정가 × (종류·지역별 공매 낙찰가율) × (유찰보정)
유찰 1회당 통상 최저입찰가가 10%씩 하락(온비드 매각관행)하며, 낙찰은 그 시점
최저가 부근~감정가 사이에서 형성된다. 단정 금지 — 저~고 범위 + 신뢰도 + 가정 명시.

주의: 공매 낙찰가율은 시장·물건별 편차가 크므로 본 추정은 '참고용 범위'이며,
실데이터(낙찰 통계) 연동 시 calibrate로 보정 가능하도록 설계했다(이번 1단계는 기본 계수).
"""

from __future__ import annotations

from typing import Any

# ── 종류별 기준 낙찰가율(감정가 대비, 공매 시장 통념 기반 보수적 기본값) ──
# 출처: 공매 시장 일반 통념(토지·공장은 변동성↑·낙찰가율↓, 아파트·오피스텔은↑).
# 실통계 연동 전까지의 가정값임을 응답에 명시한다.
BASE_WIN_RATE: dict[str, float] = {
    "apt": 0.86,
    "officetel": 0.80,
    "building": 0.74,
    "land": 0.68,
    "factory": 0.66,
    "etc": 0.72,
}

# 지역 보정(수도권 경쟁↑ → 낙찰가율↑, 지방 일부 ↓). 가정값.
REGION_ADJ: dict[str, float] = {
    "서울": 1.06,
    "경기": 1.03,
    "인천": 1.02,
    "부산": 1.00,
    "대구": 0.99,
    "대전": 0.99,
    "광주": 0.98,
    "세종": 1.00,
}

# 유찰 1회당 최저입찰가 하락폭(온비드 공매 관행: 통상 10%).
FAIL_STEP = 0.10

# 낙찰가율 분산(저~고 범위 산정용, 종류 공통 보수치).
WIN_RATE_SPREAD = 0.08


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def estimate_win_price(
    *,
    appraisal_price: int | None,
    min_bid_price: int | None = None,
    kind: str = "etc",
    region_sido: str | None = None,
    fail_count: int = 0,
) -> dict[str, Any]:
    """공매 물건의 예상 낙찰가 범위를 추정한다.

    반환 dict: {
      est_win_low, est_win_mid, est_win_high (원, int|None),
      win_rate_mid (감정가 대비, %), confidence ("low"|"medium"|"high"),
      basis (str), assumptions (list[str]), is_estimate=True
    }
    감정가가 없으면 추정 불가(None 범위 + 사유)로 정직 반환한다.
    """
    assumptions = [
        "공매 낙찰가율은 시장·물건별 편차가 크며 본 값은 참고용 가정치입니다(실낙찰통계 미연동).",
        f"종류({kind}) 기준 낙찰가율 {BASE_WIN_RATE.get(kind, BASE_WIN_RATE['etc']) * 100:.0f}% 적용.",
        f"유찰 1회당 최저입찰가 {int(FAIL_STEP * 100)}% 하락(온비드 매각관행) 반영.",
    ]

    if not appraisal_price or appraisal_price <= 0:
        return {
            "est_win_low": None,
            "est_win_mid": None,
            "est_win_high": None,
            "win_rate_mid": None,
            "confidence": "low",
            "basis": "감정가 부재 — 낙찰가능가 추정 불가",
            "assumptions": assumptions,
            "is_estimate": True,
        }

    base_rate = BASE_WIN_RATE.get(kind, BASE_WIN_RATE["etc"])
    region_adj = REGION_ADJ.get(region_sido or "", 1.0)
    # 유찰 보정: 유찰이 누적될수록 낙찰가율(감정가 대비) 자체가 하락.
    fail_adj = (1.0 - FAIL_STEP) ** max(0, fail_count)
    win_rate_mid = _clamp(base_rate * region_adj * fail_adj, 0.30, 1.05)

    mid = int(appraisal_price * win_rate_mid)
    low = int(appraisal_price * _clamp(win_rate_mid - WIN_RATE_SPREAD, 0.25, 1.0))
    high = int(appraisal_price * _clamp(win_rate_mid + WIN_RATE_SPREAD, 0.30, 1.10))

    # 최저입찰가가 주어지면, 낙찰은 그 이상에서만 성립 → 하한 보정.
    if min_bid_price and min_bid_price > 0:
        low = max(low, min_bid_price)
        mid = max(mid, min_bid_price)
        high = max(high, min_bid_price)
        assumptions.append(
            f"현재 최저입찰가({min_bid_price:,}원) 이상에서만 낙찰 성립 → 하한 보정."
        )

    # 신뢰도: 종류·지역 계수가 표준적이고 유찰이 과도하지 않으면 medium, 그 외 low.
    confidence = "medium" if region_sido in REGION_ADJ and kind in BASE_WIN_RATE and fail_count <= 3 else "low"

    return {
        "est_win_low": low,
        "est_win_mid": mid,
        "est_win_high": high,
        "win_rate_mid": round(win_rate_mid * 100, 1),
        "confidence": confidence,
        "basis": "감정가 × 종류·지역 낙찰가율 × 유찰보정(G2B 낙찰가율 로직 차용)",
        "assumptions": assumptions,
        "is_estimate": True,
    }
