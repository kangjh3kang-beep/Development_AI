"""사업 부담금 공용 헬퍼 — B(공사)+C(분양) 단계 시행사 부담분 표준 계약.

★부담금 상시-0 봉합(전역 전파방지): 개략수지(rough) 경로가 total_tax_cost_won=0으로
아예 부담금을 계상하지 않아 학교용지·광역교통·상하수도·HUG 등이 총사업비에서 통째로
누락되던 결함의 공용 봉합 지점. 새 산식은 만들지 않고 기존 검증 엔진
(utility_stage_engine·sale_stage_engine)을 조합만 한다.

계약:
- A(취득)단계는 포함하지 않는다 — 개략수지 토지비(land_cost_engine,
  include_taxes_and_fees=True)에 이미 계상돼 있어 포함 시 이중계상.
- D(양도)단계도 포함하지 않는다 — 총사업비(사업 수행 비용) 성격이 아님.
- 시행사 부담분만 합산한다(sale 단계 total_won은 이미 시행사분만 —
  수분양자 부담 C04~C06은 buyer_borne_total_won으로 분리돼 있음).
- 산출 불가 항목(표준건축비 미고시·조례 단가 미등록 등)은 값을 지어내지 않고
  unavailable_notes로 정직 표기한다(무목업).
"""

from __future__ import annotations

from typing import Any

from app.services.tax.sale_stage_engine import calculate_all_sale_stage
from app.services.tax.utility_stage_engine import calculate_all_utility_stage

# JSON/쿼리스트링 직렬화로 불리언이 문자열로 오는 흔한 오염 케이스의 거짓값 표기들.
_FALSY_STRINGS = frozenset({"", "0", "false", "no", "n", "off"})


def parse_bool_flag(value: Any) -> bool:
    """부담금 게이트용 불리언 안전 파서 — 문자열 "false"/"0" 오부과 방지(리뷰 P2-1).

    무타입 dict(params·overrides)에서 오는 게이트는 클라이언트 직렬화에 따라
    문자열 "false"가 올 수 있고, 원시 bool("false")=True라 부담구역이 아닌
    사업지에 C07이 부과된다. 문자열은 표기 기준으로, 그 외는 truthiness로 판정한다.
    """
    if isinstance(value, str):
        return value.strip().lower() not in _FALSY_STRINGS
    return bool(value)


def _collect_unavailable_notes(stage: dict[str, Any]) -> list[str]:
    """단계 items에서 '산출 불가(정직 강등)' 항목의 사유를 수집한다.

    엔진들의 정직 표기 관례 2종을 모두 인식한다:
    - detail.confidence == "unavailable" (B01 표준건축비 미고시, B03/B04 조례 미등록)
    - detail.amount_computable == False (B01 광역교통 — 금액 산출 불가 플래그)
    """
    notes: list[str] = []
    for item in stage.get("items") or []:
        if not isinstance(item, dict):
            continue
        detail = item.get("detail") or {}
        if not isinstance(detail, dict):
            continue
        unavailable = detail.get("confidence") == "unavailable" or detail.get("amount_computable") is False
        if unavailable:
            reason = detail.get("reason") or "산출 근거 미확보"
            notes.append(f"{item.get('name', item.get('code', '부담금'))}: {reason} — 합계 미반영(정직 강등)")
    return notes


def compute_developer_stage_charges(
    *,
    sido_name: str = "",
    sigungu_name: str = "",
    total_households: int = 0,
    total_sale_amount_won: int = 0,
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    avg_area_sqm: float = 85.0,
    in_infra_charge_zone: bool = False,
) -> dict[str, Any]:
    """B(공사)+C(분양) 단계 시행사 부담금 일괄 계산 — 개략수지 총사업비 계상용.

    Returns:
        {
            'construction': {...},   # utility_stage 원본(items·total_won)
            'sale': {...},           # sale_stage 원본(items·total_won=시행사분)
            'total_won': int,        # 시행사 부담 합계(B.total + C.total)
            'unavailable_notes': [...],  # 산출 불가 항목 정직 사유(합계 미반영분)
        }
    """
    construction = calculate_all_utility_stage(
        sido_name=sido_name,
        sigungu_name=sigungu_name,
        total_households=max(0, total_households),
        total_sale_amount_won=max(0, total_sale_amount_won),
        total_gfa_sqm=max(0.0, total_gfa_sqm),
        building_type=building_type,
    )
    sale = calculate_all_sale_stage(
        total_sale_amount_won=max(0, total_sale_amount_won),
        total_units=max(0, total_households),
        avg_area_sqm=avg_area_sqm or 85.0,
        total_gfa_sqm=max(0.0, total_gfa_sqm),
        building_type=building_type,
        in_infra_charge_zone=in_infra_charge_zone,
    )
    notes = _collect_unavailable_notes(construction) + _collect_unavailable_notes(sale)
    return {
        "construction": construction,
        "sale": sale,
        "total_won": int(construction["total_won"]) + int(sale["total_won"]),
        "unavailable_notes": notes,
    }
