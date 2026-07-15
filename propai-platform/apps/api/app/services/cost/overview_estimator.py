"""공용 개산식 SSOT — 적산(estimate-overview)·수지(construction_cost_engine) 공용.

★적산→수지 단절 봉합(2026-07-15 감사 P2): 종전에는
- 수지: 순수 `연면적 × ₩/㎡` (구조유형·지하할증·조경 무반영)
- 적산 라우터: 자체 인라인 산식(구조계수 + 지하 30% 할증 + 조경 1.5%)
으로 같은 프로젝트의 공사비가 두 모듈에서 갈라졌다. 이 모듈이 산식의 단일 출처다 —
한 곳을 고치면 적산·수지가 함께 따라온다(전역 전파방지).

주의: QTO(StandardQuantityEstimator) 총액은 골조 중심 8공종만 커버해 시장 도급가의
약 1/3 수준(2026-07-15 실측)이므로 공사비 '총액 기저'로 쓰지 않는다(무날조).
QTO는 항목 분해·근거 노출 용도로만 병렬 사용한다(estimate-overview items_qto).
"""

from __future__ import annotations

from typing import Any

# 구조유형별 비용계수 — routers/cost.py 인라인 정의에서 이관(값 동일).
# ※ standard_quantity_estimator.STRUCTURE_FACTORS(물량 보정계수)와는 다른 축이다:
#   이쪽은 ₩/㎡ 도급단가 보정(비용), 그쪽은 골조 물량 보정. 혼용 금지.
STRUCT_COST_FACTOR: dict[str, float] = {
    "RC": 1.0, "RC조": 1.0,
    "SRC": 1.15, "SRC조": 1.15,
    "SC": 1.10, "철골": 1.10, "철골조": 1.10,
    "PC": 0.95,
    "목구조": 0.85,
}

# 지하공사 단가 할증(토공·흙막이·방수 반영 관례치) — routers/cost.py에서 이관.
BASEMENT_COST_SURCHARGE = 1.3
# 지하 바닥판 확장계수 — 지하는 주차·기계실로 지상 footprint보다 약간 넓다(≈1.2배).
BASEMENT_PLATE_EXPANSION = 1.2
# 조경공사 비율(직접비 대비) — routers/cost.py에서 이관.
LANDSCAPE_RATIO = 0.015


def split_gfa_below(
    total_gfa_sqm: float, floor_count_above: int, floor_count_below: int
) -> tuple[float, float]:
    """연면적을 지상/지하로 분해 — 층 바닥판 비례(지하 바닥판 1.2배 확장).

    routers/cost.py 인라인 산식과 동일: 지하면적 = 총GFA × (지하층수×1.2)/(지상+지하×1.2).
    Returns: (gfa_above_sqm, gfa_below_sqm)
    """
    fa = max(1, int(floor_count_above))
    fb = max(0, int(floor_count_below))
    below = (total_gfa_sqm * (fb * BASEMENT_PLATE_EXPANSION) / (fa + fb * BASEMENT_PLATE_EXPANSION)) if fb > 0 else 0.0
    return max(0.0, total_gfa_sqm - below), below


def estimate_overview_direct_cost(
    *,
    total_gfa_sqm: float,
    base_unit_cost_per_sqm: float,
    structure_type: str = "RC",
    floor_count_above: int = 1,
    floor_count_below: int = 0,
    scenario_factor: float = 1.0,
) -> dict[str, Any]:
    """지상/지하/조경 분해 직접공사비 — 적산 estimate-overview scenario()와 동일 산식.

    Args:
        total_gfa_sqm: 총 연면적(㎡).
        base_unit_cost_per_sqm: 구조계수 적용 전 기준 ₩/㎡ 단가(호출자가 SSOT에서 resolve).
        structure_type: 구조유형(STRUCT_COST_FACTOR 키). 미등록 유형은 1.0(RC 기준).
        floor_count_above / floor_count_below: 지상/지하 층수.
        scenario_factor: 물가 시나리오 계수(최저 0.92 / 기대 1.0 / 최대 1.12).

    Returns:
        {'unit_cost_per_sqm', 'structure_factor', 'gfa_above_sqm', 'gfa_below_sqm',
         'aboveground_won', 'underground_won', 'landscape_won', 'direct_won'}

    ※ 연산 순서·int 절사까지 routers/cost.py 종전 인라인과 동일하게 유지(byte 호환 —
      리팩토링으로 기존 적산 응답이 1원도 달라지지 않는다).
    """
    struct_factor = STRUCT_COST_FACTOR.get(structure_type, 1.0)
    unit_f = base_unit_cost_per_sqm * struct_factor
    u = int(unit_f * scenario_factor)
    gfa_above, gfa_below = split_gfa_below(total_gfa_sqm, floor_count_above, floor_count_below)
    above = int(gfa_above * u)
    below = int(gfa_below * u * BASEMENT_COST_SURCHARGE)
    landscape = int((above + below) * LANDSCAPE_RATIO)
    return {
        "unit_cost_per_sqm": u,
        "structure_factor": struct_factor,
        "gfa_above_sqm": round(gfa_above, 2),
        "gfa_below_sqm": round(gfa_below, 2),
        "aboveground_won": above,
        "underground_won": below,
        "landscape_won": landscape,
        "direct_won": above + below + landscape,
    }
