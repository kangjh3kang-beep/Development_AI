"""I6 — 수요기반 평형 MD 추천(경량·결정론).

연구문서 §A3: 권역 가구원수 분포(+연령·1인가구 통계) → 전용면적 밴드별 공급배분(unit mix).
시장보고서용 경량 추천기(정밀 수익최적은 feasibility/unit_mix_optimizer SLSQP 경로).

매핑 근거(가구원수 → 전용면적 밴드, 최저주거기준·실무 평형 통념):
  1인 → 소형(~49㎡), 2인 → 59㎡ 중심, 3인 → 74~84㎡, 4인+ → 84~99㎡+.
가구 데이터 없으면 unavailable(가짜 추천 금지). 출처(data_source) 전파.
"""

from __future__ import annotations

from typing import Any, Optional

# 전용면적 밴드(표준 평형).
BANDS = ["소형(~49㎡)", "59㎡", "74㎡", "84㎡", "99㎡+"]

# 가구원수 → 밴드 가중(각 행 합=1.0). 최저주거기준+실무 통념 기반 결정론 매핑.
_HH_TO_BAND: dict[str, dict[str, float]] = {
    "1_person": {"소형(~49㎡)": 1.0},
    "2_person": {"소형(~49㎡)": 0.3, "59㎡": 0.7},
    "3_person": {"59㎡": 0.2, "74㎡": 0.5, "84㎡": 0.3},
    "4_over": {"84㎡": 0.5, "99㎡+": 0.5},
}
_BASIS = "가구원수별 최저주거기준 + 실무 평형 통념(1인 소형·4인+ 84~99㎡+) 매핑 — 연구 §A3."


def recommend_unit_mix(
    household_types: Optional[dict[str, Any]],
    *,
    data_source: Optional[str] = None,
) -> dict[str, Any]:
    """가구원수 분포 → 권장 전용면적 밴드별 공급배분(%).

    Args:
        household_types: {"1_person":..,"2_person":..,"3_person":..,"4_over":..} (인원수 또는 비율).
        data_source: 인구 데이터 출처(live/fallback/mock) — 그대로 전파.

    Returns:
        recommended_mix(밴드→%), dominant(최대 밴드), rationale, data_source, basis.
        가구 데이터 없으면 data_source='unavailable'(가짜 추천 금지).
    """
    ht = household_types or {}
    # 값 합산(인원수/비율 무관 — 상대비중만 사용).
    total = 0.0
    ratios: dict[str, float] = {}
    for k in _HH_TO_BAND:
        try:
            v = float(ht.get(k) or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0:
            ratios[k] = v
            total += v

    if total <= 0:
        return {
            "data_source": "unavailable",
            "note": "가구원수 분포 데이터 없음 — 인구/가구 분석(SGIS) 선택 시 평형 MD 추천(가짜값 금지).",
            "basis": _BASIS,
        }

    # 밴드별 가중 누적 → % 정규화.
    band_score = {b: 0.0 for b in BANDS}
    for hh, cnt in ratios.items():
        w = cnt / total  # 가구 비중
        for band, bw in _HH_TO_BAND[hh].items():
            band_score[band] += w * bw

    score_sum = sum(band_score.values()) or 1.0
    recommended_mix = {b: round(band_score[b] / score_sum * 100, 1) for b in BANDS if band_score[b] > 0}
    dominant = max(recommended_mix, key=lambda k: recommended_mix[k]) if recommended_mix else None

    # 근거 문장(주력 가구 → 주력 평형).
    hh_label = {"1_person": "1인", "2_person": "2인", "3_person": "3인", "4_over": "4인 이상"}
    top_hh = max(ratios, key=lambda k: ratios[k])
    rationale = (
        f"주력 가구는 {hh_label.get(top_hh, top_hh)} 가구"
        f"({round(ratios[top_hh] / total * 100)}%) — {dominant} 평형 특화 공급이 유리."
    )

    return {
        "recommended_mix": recommended_mix,   # 밴드→공급배분%
        "dominant_band": dominant,
        "rationale": rationale,
        "data_source": data_source if data_source in ("live", "fallback", "mock") else "fallback",
        "basis": _BASIS,
        "note": "수요(가구원수) 기반 권장 평형 배분(개략). 정밀 수익최적 배분은 unit_mix_optimizer(SLSQP) 사용.",
    }
