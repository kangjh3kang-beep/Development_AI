"""INC-5b — 2D 폴리곤 경계좌표 → 면적(슈레이스 공식) 결정론 적분.

도면 벡터(폴리라인/해치) 경계좌표로부터 면적을 결정론적으로 계산한다(VLLM 텍스트 area에 의존하지 않는
1차출처 후보). 좌표는 도면단위 → 실척 환산은 scale_convert(INC-4)가 scale_denominator²로 수행한다.
"""
from __future__ import annotations

from collections.abc import Sequence


def shoelace_area(coords: Sequence[Sequence[float]]) -> float:
    """폴리곤 경계좌표 [[x,y],...] → 면적(슈레이스, 닫힘/열림·시계방향 무관). 점 3개 미만 → 0.0."""
    pts = [(float(p[0]), float(p[1])) for p in coords if len(p) >= 2]
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_real_area(coords: Sequence[Sequence[float]], scale_denominator: float) -> float:
    """도면단위 폴리곤 → 실척 면적(슈레이스 × 분모²). 결정론."""
    return shoelace_area(coords) * (float(scale_denominator) ** 2)
