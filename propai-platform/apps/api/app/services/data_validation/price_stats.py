"""실거래 가격 분포의 대표 통계 — 이상치 제거 후 최저/최고/평균 산출.

trust.py의 '값 사용 전 이상치 제거' 원칙을 분포(다수 거래 레코드)에 적용한다. cross_validate가
다출처 앵커 교차검증인 것과 달리, 이 헬퍼는 단일 유형의 거래금액 분포에서 대표값을 뽑는다.

동기(실버그): 토지 실거래 최저가가 4만원(=지분·도로·정정 등 미미 거래)으로 표시되고 평균이
왜곡되던 문제. 원시 min/max/avg는 극단 양단(미미 지분거래·초고가)에 지배된다.

방법: **로그스케일 IQR(1.5×)** — 부동산 가격은 우편향(log-normal 유사)이라 로그 변환 후 사분위로
양단 극단을 제외한다. 하드코딩 임계값 없음(통계적). 표본 과소(<8건) 시 트림 생략(원시 유지).
"""
from __future__ import annotations

import math
import statistics
from typing import Any

_MIN_SAMPLE_FOR_TRIM = 8


def robust_price_stats(prices: list[int | float]) -> dict[str, Any]:
    """거래금액(동일단위: 만원 등) 리스트 → {avg, min, max, count, excluded}.

    · count : 원시 유효건수(양수)로 정직 표기.
    · avg/min/max : 이상치(로그 IQR 밖) 제외 후 대표값.
    · excluded : 제외된 이상치 건수.
    빈 입력/전량 비양수 → 0.
    """
    vals = sorted(int(p) for p in prices if p and int(p) > 0)
    n = len(vals)
    if n == 0:
        return {"avg": 0, "min": 0, "max": 0, "count": 0, "excluded": 0}

    if n < _MIN_SAMPLE_FOR_TRIM:
        core = vals  # 표본 과소 — 통계적 트림 불가(원시 유지)
    else:
        logs = [math.log(v) for v in vals]
        q1, _q2, q3 = statistics.quantiles(logs, n=4)
        iqr = q3 - q1
        lo = math.exp(q1 - 1.5 * iqr)
        hi = math.exp(q3 + 1.5 * iqr)
        core = [v for v in vals if lo <= v <= hi] or vals

    return {
        "avg": round(sum(core) / len(core)),
        "min": min(core),
        "max": max(core),
        "count": n,
        "excluded": n - len(core),
    }
