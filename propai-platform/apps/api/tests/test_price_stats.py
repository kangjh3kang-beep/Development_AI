"""실거래 대표통계(이상치 제거) 회귀가드 — 토지 최저 4만원(지분/정정) 왜곡 수정.

로그스케일 IQR 트림: 양단 극단 제외·표본 과소 시 원시유지·count는 원시 정직. 순수 함수(로컬 실행).
"""
from __future__ import annotations

from app.services.data_validation.price_stats import robust_price_stats


def test_land_tiny_share_outlier_excluded():
    """★토지 4만원(지분/정정) 미미거래가 최저에서 제외되고 count는 원시 유지."""
    land = [4, 300, 800] + [5000, 6000, 7000, 8000, 9000, 10000, 12000, 15000, 20000] * 15 + [549037, 200000]
    r = robust_price_stats(land)
    assert r["min"] >= 1000, f"미미거래 미제외 — min={r['min']}"
    assert r["min"] != 4
    assert r["count"] == len(land), "count는 원시 유효건수(정직)"
    assert r["excluded"] >= 1


def test_small_sample_no_trim():
    """표본 과소(<8) → 통계적 트림 불가 → 원시 유지(정직)."""
    r = robust_price_stats([4, 5000, 10000])
    assert r["min"] == 4 and r["max"] == 10000 and r["count"] == 3 and r["excluded"] == 0


def test_empty_and_nonpositive():
    """빈/비양수 → 0."""
    assert robust_price_stats([]) == {"avg": 0, "min": 0, "max": 0, "count": 0, "excluded": 0}
    assert robust_price_stats([0, -5, None])["count"] == 0  # type: ignore[list-item]


def test_representative_avg_between_min_max():
    """평균은 트림 후 min~max 사이·양수."""
    apt = [15300, 20000] + [90000, 95000, 100000, 110000] * 50 + [188000]
    r = robust_price_stats(apt)
    assert r["min"] <= r["avg"] <= r["max"]
    assert r["count"] == len(apt)


def test_count_honest_excludes_only_nonpositive():
    """count = 양수 건수(0·음수만 제외)."""
    r = robust_price_stats([0, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000, -1])
    assert r["count"] == 8  # 0·-1 제외
