"""R0 — 신뢰도 타입/합성 대수(기본). 값역 [0,1] 강제.

combine: 독립 증거 합성(곱). degrade: 충돌/보류 시 하향. 모든 결과는 clamp01로 값역 보장.
법정 수치 없음 — 합성계수는 호출자(파라미터)에서 주입.
"""
from __future__ import annotations

from collections.abc import Iterable

_LO = 0.0
_HI = 1.0


def clamp01(x: float) -> float:
    """[0,1] 범위로 클램프."""
    return max(_LO, min(_HI, float(x)))


def combine(values: Iterable[float]) -> float:
    """독립 신뢰도 합성(곱). 빈 입력은 1.0(중립)."""
    acc = _HI
    for v in values:
        acc *= clamp01(v)
    return clamp01(acc)


def degrade(confidence: float, factor: float) -> float:
    """충돌/보류 시 신뢰도 하향. factor는 외부에서 주입(파라미터)."""
    return clamp01(confidence * factor)
