"""데이터 신뢰·정확도 교차검증 유틸(플랫폼 공통 기반).

이번 분양가 사고의 교훈: 잘못은 '최종 계산'이 아니라 '원천 데이터 수집' 단계에서 났다
(럭셔리 분양 outlier 채택 + 실거래 anchor 누락). 따라서 모든 조사/분석은 값을 쓰기 전에
'여러 출처를 교차검증 → 이상치 제거 → 일관성/신선도 확인 → 신뢰도 산출 → 통과 시에만 사용,
아니면 정직 강등'의 반복 루프를 거쳐야 한다. 이 모듈은 그 공통 1차 게이트를 제공한다.

설계 원칙(무목업·정직): 신뢰 못 할 값은 trusted_value=None + verdict='fail'/'warn'로 강등하고
이유를 남긴다(가짜값을 'live'로 단정하지 않음). 도메인 sanity 범위는 verification/range_rules,
산식·할루시네이션은 verification/verifier_service 와 함께 계층적으로 동작한다.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Signal:
    """한 출처에서 온 값 1개(예: 실거래 중앙값·주변 분양가·AVM)."""
    name: str
    value: float
    sample_size: int = 1          # 표본 수(많을수록 신뢰↑)
    source: str = "unknown"       # live/fallback/mock 등 출처 등급
    weight: float = 1.0           # 신뢰 가중(앵커 출처는 높게)


@dataclass
class TrustResult:
    trusted_value: float | None
    confidence: float             # 0.0~1.0
    verdict: str                  # pass | warn | fail
    used: list[str] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    consensus_ratio: float | None = None  # 사용 출처들의 최대/최소 비

    def to_dict(self) -> dict[str, Any]:
        return {
            "trusted_value": self.trusted_value,
            "confidence": round(self.confidence, 3),
            "verdict": self.verdict,
            "used_sources": self.used,
            "excluded_outliers": self.excluded,
            "warnings": self.warnings,
            "consensus_ratio": round(self.consensus_ratio, 3) if self.consensus_ratio else None,
        }


def cross_validate(
    signals: list[Signal],
    *,
    anchor: str | None = None,
    outlier_ratio: float = 1.6,
    min_anchor_samples: int = 20,
    plausible_min: float | None = None,
    plausible_max: float | None = None,
) -> TrustResult:
    """여러 출처 값을 교차검증해 신뢰 가능한 단일 값 + 신뢰도/판정을 반환한다.

    절차:
      1) 양수·범위(plausible_min/max) 통과 값만 후보로.
      2) anchor(예: 실거래 중앙값, 표본 충분)가 있으면 기준으로, 없으면 후보 중앙값을 기준으로.
      3) 기준 대비 outlier_ratio 배 이상 벗어난 출처는 '이상치'로 제외(예: 인근 럭셔리 분양가).
      4) 남은 출처의 가중평균을 trusted_value 로, 일관성·표본·출처등급으로 confidence 산출.
      5) anchor가 표본 부족/부재이고 합의도 낮으면 verdict=warn/fail 로 정직 강등.
    """
    warnings: list[str] = []
    excluded: list[dict[str, Any]] = []

    # 1) 범위·양수 필터
    cands: list[Signal] = []
    for s in signals:
        if s.value is None or s.value <= 0:
            continue
        if plausible_min is not None and s.value < plausible_min:
            excluded.append({"name": s.name, "value": s.value, "reason": f"하한({plausible_min}) 미만"})
            continue
        if plausible_max is not None and s.value > plausible_max:
            excluded.append({"name": s.name, "value": s.value, "reason": f"상한({plausible_max}) 초과"})
            continue
        cands.append(s)

    if not cands:
        return TrustResult(None, 0.0, "fail", warnings=["유효한 출처 값이 없습니다(범위·양수 실패)."], excluded=excluded)

    # 2) 기준값(anchor 우선)
    anchor_sig = next((s for s in cands if s.name == anchor), None) if anchor else None
    anchor_ok = bool(anchor_sig and anchor_sig.sample_size >= min_anchor_samples)
    ref = anchor_sig.value if anchor_ok else statistics.median([s.value for s in cands])

    # 3) 이상치 제외(기준 대비 비율)
    kept: list[Signal] = []
    for s in cands:
        r = max(s.value, ref) / max(min(s.value, ref), 1e-9)
        if r > outlier_ratio and not (anchor_ok and s.name == anchor):
            excluded.append({"name": s.name, "value": s.value, "ratio": round(r, 2),
                             "reason": f"기준 대비 {r:.1f}배 — 이상치 제외"})
        else:
            kept.append(s)
    if not kept:
        kept = [anchor_sig] if anchor_sig else cands

    # 4) 가중평균 + 합의비
    wsum = sum(s.weight for s in kept) or 1.0
    trusted = sum(s.value * s.weight for s in kept) / wsum
    vals = [s.value for s in kept]
    consensus = (max(vals) / max(min(vals), 1e-9)) if len(vals) > 1 else 1.0

    # 5) confidence: 출처수·합의도·앵커표본·출처등급 종합
    conf = 0.35
    conf += min(0.25, 0.08 * len(kept))                       # 다중 출처
    conf += 0.20 if consensus <= 1.15 else (0.10 if consensus <= 1.35 else 0.0)  # 합의
    if anchor_ok:
        conf += min(0.20, 0.0005 * anchor_sig.sample_size)    # 앵커 표본
    if any(s.source == "live" for s in kept):
        conf += 0.10
    conf = max(0.0, min(1.0, conf))

    verdict = "pass"
    if not anchor_ok and anchor:
        warnings.append(f"앵커({anchor}) 표본 부족/부재 — 신뢰도 하향.")
    if excluded:
        warnings.append(f"이상치 {len(excluded)}건 제외(인근 비교 등급 상이 가능).")
    if conf < 0.45 or consensus > 1.6:
        verdict = "warn"
    if conf < 0.3 or not kept:
        verdict = "fail"

    return TrustResult(round(trusted), conf, verdict, used=[s.name for s in kept],
                       excluded=excluded, warnings=warnings, consensus_ratio=consensus)
