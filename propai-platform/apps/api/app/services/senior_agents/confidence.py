"""confidence 캘리브레이션(critic M2/A9) — verbalized 과신 방지·판단영역 구간출력.

confidence = 0.35·데이터완전성 + 0.25·룰적용가능성 + 0.25·RAG근거강도 + 0.15·(1 − 과거동류_교정빈도)
- 입력 4신호는 [0,1]. 결측은 0.5(중립)로 보수 처리.
- < THRESHOLD_REVIEW(0.6) = 「전문가 확인 필요」 강등(selective prediction).
- 고위험 도메인(심의 부적합·세무 가산세·PF 거절)은 임계 상향(요청 시).
- 판단영역(종상향 잠재·가결확률·세부담·분양률)은 점추정 금지 → make_interval로 구간+근거.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_W = {"completeness": 0.35, "rule_fit": 0.25, "rag_strength": 0.25, "track_record": 0.15}
THRESHOLD_REVIEW = 0.6        # 미만 = 전문가 확인 필요
THRESHOLD_HIGH_RISK = 0.75    # 고위험 도메인 상향 임계(전문가 확인 강등)
# '신뢰' 라벨 하한 — 강등컷과 분리(강등컷+0.2는 고위험에서 0.95=사실상 도달불가였음).
THRESHOLD_TRUST = 0.8            # 일반 '신뢰' 하한
THRESHOLD_HIGH_RISK_TRUST = 0.9  # 고위험 '신뢰' 하한(상향이되 강신호로 도달 가능)


def _clip01(x: float | None) -> float:
    if x is None:
        return 0.5  # 결측 = 중립(보수)
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.5
    if not math.isfinite(v):  # NaN/inf는 비교(<,>)를 우회 → 과신게이트 무력화 방지(중립 처리)
        return 0.5
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def compute_confidence(
    *, data_completeness: float | None, rule_fit: float | None,
    rag_strength: float | None, correction_rate: float | None,
) -> float:
    """4신호 → confidence[0,1]. correction_rate(과거 동류 교정빈도)는 높을수록 신뢰↓."""
    c = _clip01(data_completeness)
    rf = _clip01(rule_fit)
    rs = _clip01(rag_strength)
    tr = 1.0 - _clip01(correction_rate)
    score = _W["completeness"] * c + _W["rule_fit"] * rf + _W["rag_strength"] * rs + _W["track_record"] * tr
    return round(score, 4)


def needs_expert_review(confidence: float, *, high_risk: bool = False) -> bool:
    """selective prediction — 임계 미달 시 전문가 확인 강등(고위험은 상향 임계)."""
    return confidence < (THRESHOLD_HIGH_RISK if high_risk else THRESHOLD_REVIEW)


def confidence_label(confidence: float, *, high_risk: bool = False) -> str:
    # 라벨 등급을 게이트 임계와 정합: 강등컷=needs_expert_review 임계, 신뢰컷=별도 상수(도달 가능).
    if needs_expert_review(confidence, high_risk=high_risk):
        return "참고(전문가 확인 필요)"
    trust_cut = THRESHOLD_HIGH_RISK_TRUST if high_risk else THRESHOLD_TRUST
    return "신뢰" if confidence >= trust_cut else "보통"


@dataclass(frozen=True)
class Interval:
    """판단영역 구간 추정(점추정 금지)."""

    low: float
    high: float
    basis: str

    def to_dict(self) -> dict:
        return {"low": self.low, "high": self.high, "basis": self.basis}


def make_interval(low: float, high: float, basis: str) -> Interval:
    """구간 추정 생성(low<=high 보장·근거 필수). 근거 없으면 ValueError(무목업)."""
    if not (basis and basis.strip()):
        raise ValueError("구간 추정에는 근거(basis)가 필수입니다(무목업).")
    if not (math.isfinite(low) and math.isfinite(high)):  # NaN/inf 구간 거부(무목업)
        raise ValueError("구간 추정값은 유한수여야 합니다(NaN/inf 금지).")
    lo, hi = (low, high) if low <= high else (high, low)
    return Interval(low=round(lo, 4), high=round(hi, 4), basis=basis.strip())
