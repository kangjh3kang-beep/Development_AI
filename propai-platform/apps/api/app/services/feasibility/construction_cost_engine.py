"""공사비 산정 엔진 — 직접공사비/간접공사비/설계감리비.

순수 함수형 설계: DB 의존 없음.
표준품셈 기반 + 건설물가지수 보정.
"""

from __future__ import annotations

from typing import Any

PYEONG_TO_SQM = 3.305785

# 기본 공사비 단가 (원/m², 2025년 기준)
# ★SSOT: 이 상수는 unit_price_repository(_DIRECT_SQM_FALLBACK)와 동일값으로 일원화됨.
#   엔진은 repository.resolve_direct_sqm_sync() 로 단가를 조회하되, import/조회 실패 시
#   아래 상수로 fallback → repo·DB가 비어도 전환 전과 100% 동일값(회귀 0).
#   호환을 위해 상수는 유지(routers/cost.py 등 기존 참조처 무파괴).
DEFAULT_DIRECT_COST_PER_SQM: dict[str, int] = {
    "apartment": 2_400_000,
    "officetel": 2_600_000,
    "commercial": 2_200_000,
    "office": 2_500_000,
    "warehouse": 1_200_000,
    "townhouse": 2_000_000,
    "single_house": 2_100_000,
}


def _resolve_direct_unit_cost(building_type: str) -> int:
    """건물유형 ₩/㎡ 개산단가를 SSOT(unit_price_repository)에서 조회.

    조회/임포트 실패 시 DEFAULT_DIRECT_COST_PER_SQM 로 fallback(회귀 0).
    """
    try:
        from app.services.cost.unit_price_repository import resolve_direct_sqm_sync

        return resolve_direct_sqm_sync(building_type)
    except Exception:  # noqa: BLE001 — SSOT 미가용 시 기존 상수로 안전 폴백
        return DEFAULT_DIRECT_COST_PER_SQM.get(
            building_type, DEFAULT_DIRECT_COST_PER_SQM["apartment"]
        )

# 간접공사비 비율 기본값
DEFAULT_INDIRECT_RATIOS: dict[str, float] = {
    "design_fee": 0.04,       # 설계비 (직접공사비 대비)
    "supervision_fee": 0.03,  # 감리비
    "contingency": 0.05,      # 예비비
    "general_expense": 0.03,  # 일반관리비
}


def pyeong_to_sqm(area_pyeong: float) -> float:
    """평 → m² 변환."""
    return round(area_pyeong * PYEONG_TO_SQM, 2)


def sqm_to_pyeong(area_sqm: float) -> float:
    """m² → 평 변환."""
    return round(area_sqm / PYEONG_TO_SQM, 2)


# ── `apply_cost_index` 제거(2026-08-22) ────────────────────────────────────────
#   연 3% **가정치**로 (1+r)^(target-base) 를 곱하던 물가보정 함수였다.
#   ★프로덕션 소비처 **0**(정의1 + 테스트3 + 기획문서1) — 대조군 `calculate_direct_cost`
#     는 다른 파일 1곳에서 잡히므로 검사기 자체는 살아 있었다.
#   ★죽은 이유는 **배선 누락이 아니라 대체**다:
#     `unit_price_repository._maybe_escalate` 가 **KOSIS 건설공사비지수 실측**
#     (`cost_index_service.escalation_factor`)으로 시점보정하고, 실패 시 무날조로
#     원본 단가를 반환한다. 가정 3% 보다 정확하므로 되살릴 이유가 없다.
#   ※ `cost_index_factor` 파라미터는 **남긴다** — 민감도 분석이 공사비 배수로 실제 사용한다
#     (`precheck_service` 가 params 에 주입). 기본 경로에서는 1.0(보정 없음)이 정상이다.

def calculate_direct_cost(
    *,
    total_gfa_sqm: float,
    building_type: str = "apartment",
    unit_cost_per_sqm: int | None = None,
    cost_index_factor: float = 1.0,
    floor_count_above: int | None = None,
    floor_count_below: int | None = None,
    structure_type: str | None = None,
) -> dict[str, Any]:
    """직접공사비 계산.

    Args:
        total_gfa_sqm: 총 연면적 (m²)
        building_type: 건물유형
        unit_cost_per_sqm: 직접공사비 단가 (원/m², None이면 기본값)
        cost_index_factor: 물가보정계수
        floor_count_above / floor_count_below / structure_type:
            ★적산→수지 배선(2026-07-15 감사 P2) — 하나라도 제공되면 적산
            estimate-overview와 동일한 공용 개산식(overview_estimator SSOT:
            구조계수·지하 30% 할증·조경 1.5%)으로 산정하고 분해를 함께 반환한다.
            전부 미제공(기본 None)이면 종전 `연면적 × ₩/㎡` 그대로(무회귀).

    Returns:
        {'total_gfa_sqm', 'unit_cost_per_sqm', 'cost_index_factor', 'total_direct_cost_won'}
        (+ 공용 개산식 경로일 때 'overview_breakdown', 'basis' 추가 — additive)
    """
    if unit_cost_per_sqm is None:
        unit_cost_per_sqm = _resolve_direct_unit_cost(building_type)

    adjusted_unit = int(unit_cost_per_sqm * cost_index_factor)

    if floor_count_above or floor_count_below or structure_type:
        from app.services.cost.overview_estimator import estimate_overview_direct_cost

        fa = floor_count_above or 0
        fb = floor_count_below or 0
        if fa <= 0 and fb > 0:
            # ★리뷰 R1-P2: 지상층수 미상 상태의 지하 분해는 바닥판 비례식이 fa=1 폴백으로
            #   지하를 극단 배분(예 B3 단독 → GFA 78% 지하 × 30% 할증 = 조용한 과대계상).
            #   지상층수 확보 전까지 지하 분해는 보류한다(정직 강등 — 구조계수·조경만 반영).
            fb = 0
        ov = estimate_overview_direct_cost(
            total_gfa_sqm=total_gfa_sqm,
            base_unit_cost_per_sqm=adjusted_unit,
            structure_type=structure_type or "RC",
            floor_count_above=fa or 1,
            floor_count_below=fb,
        )
        return {
            "total_gfa_sqm": round(total_gfa_sqm, 2),
            "building_type": building_type,
            "unit_cost_per_sqm": ov["unit_cost_per_sqm"],
            "cost_index_factor": cost_index_factor,
            "total_direct_cost_won": ov["direct_won"],
            "overview_breakdown": ov,
            "basis": (
                "적산 estimate-overview 동일 공용 개산식(overview_estimator SSOT) — "
                f"구조계수({structure_type or 'RC'}={ov['structure_factor']}) · "
                "지하할증 30% · 조경 1.5%"
            ),
        }

    total = int(total_gfa_sqm * adjusted_unit)
    return {
        "total_gfa_sqm": round(total_gfa_sqm, 2),
        "building_type": building_type,
        "unit_cost_per_sqm": adjusted_unit,
        "cost_index_factor": cost_index_factor,
        "total_direct_cost_won": total,
    }


def calculate_indirect_cost(
    *,
    direct_cost_won: int,
    design_fee_ratio: float | None = None,
    supervision_fee_ratio: float | None = None,
    contingency_ratio: float | None = None,
    general_expense_ratio: float | None = None,
) -> dict[str, Any]:
    """간접공사비 계산.

    Returns:
        {'design_fee_won', 'supervision_fee_won', 'contingency_won',
         'general_expense_won', 'total_indirect_cost_won', 'ratios'}
    """
    ratios = {
        "design_fee": design_fee_ratio if design_fee_ratio is not None else DEFAULT_INDIRECT_RATIOS["design_fee"],
        "supervision_fee": supervision_fee_ratio if supervision_fee_ratio is not None else DEFAULT_INDIRECT_RATIOS["supervision_fee"],
        "contingency": contingency_ratio if contingency_ratio is not None else DEFAULT_INDIRECT_RATIOS["contingency"],
        "general_expense": general_expense_ratio if general_expense_ratio is not None else DEFAULT_INDIRECT_RATIOS["general_expense"],
    }

    items = {}
    total = 0
    for key, ratio in ratios.items():
        amount = int(direct_cost_won * ratio)
        items[f"{key}_won"] = amount
        total += amount

    return {
        **items,
        "total_indirect_cost_won": total,
        "ratios": ratios,
    }


def calculate_total_construction_cost(
    *,
    total_gfa_sqm: float,
    building_type: str = "apartment",
    unit_cost_per_sqm: int | None = None,
    cost_index_factor: float = 1.0,
    # ★인입 분담금(한전·도시가스사·통신사)을 계상하려면 세대수를 준다. 0이면 미계상.
    #   도급 밖 비용이라 직접공사비 단가에 포함되지 않는다(적산 내역서에 `인입` 0~1회 실측).
    total_households: int = 0,
    design_fee_ratio: float | None = None,
    supervision_fee_ratio: float | None = None,
    contingency_ratio: float | None = None,
    general_expense_ratio: float | None = None,
    floor_count_above: int | None = None,
    floor_count_below: int | None = None,
    structure_type: str | None = None,
) -> dict[str, Any]:
    """공사비 총합 (직접 + 간접).

    floor_count_above/below·structure_type 제공 시 직접비를 적산 동일
    공용 개산식으로 산정(calculate_direct_cost 참조). 미제공 시 무회귀.

    Returns:
        {'direct', 'indirect', 'total_construction_cost_won'}
    """
    direct = calculate_direct_cost(
        total_gfa_sqm=total_gfa_sqm,
        building_type=building_type,
        unit_cost_per_sqm=unit_cost_per_sqm,
        cost_index_factor=cost_index_factor,
        floor_count_above=floor_count_above,
        floor_count_below=floor_count_below,
        structure_type=structure_type,
    )

    indirect = calculate_indirect_cost(
        direct_cost_won=direct["total_direct_cost_won"],
        design_fee_ratio=design_fee_ratio,
        supervision_fee_ratio=supervision_fee_ratio,
        contingency_ratio=contingency_ratio,
        general_expense_ratio=general_expense_ratio,
    )

    # ★인입 공사비(전기·가스·통신) — **종전에는 「부담금」(B05~B07)으로 계상**됐다.
    #   법정 부담금이 아니라 공급자 약관·계약 비용이라 공사비가 옳은 자리다(금액 불변).
    #   상세·근거·한계는 `app/services/cost/utility_connection_cost` 머리말.
    from app.services.cost.utility_connection_cost import calculate_utility_connection_cost

    connection = calculate_utility_connection_cost(
        total_households=total_households, total_gfa_sqm=total_gfa_sqm,
    )

    total = (
        direct["total_direct_cost_won"]
        + indirect["total_indirect_cost_won"]
        + connection["total_won"]
    )

    return {
        "direct": direct,
        "indirect": indirect,
        "utility_connection": connection,
        "total_construction_cost_won": total,
    }
