"""잔여 개발용량 산정 — 용도지역 법정 용적률 상한 − 기존 용적률(remaining FAR).

증축/재건축 심의안의 규모 적정성 자동 판정. 기존 연면적(getBuildingUse)/대지면적(토지특성) →
기존 용적률, 법정 상한과의 차로 잔여 용량. 기존이 상한 초과(기존불적합)면 over_limit 표면화.
지자체 조례 강화 가능성은 note로(무음 단정 금지). 결정론.
"""
from __future__ import annotations

from app.services.land.zone_limits import lookup_zone_limit


def remaining_capacity(zone_name: str | None, lot_area: float | None,
                       existing_floor_area: float | None) -> dict | None:
    """{법정한도·기존용적률·잔여FAR·최대연면적·잔여연면적·초과여부}. 매칭/면적 결손 None."""
    limit = lookup_zone_limit(zone_name)
    if limit is None or not lot_area or lot_area <= 0:
        return None
    far_limit = limit["far_limit_pct"]
    existing = existing_floor_area or 0.0
    existing_far = round(existing / lot_area * 100, 1)
    max_total = round(far_limit / 100 * lot_area, 1)
    return {
        "zone_matched": limit["zone_matched"],
        "far_limit_pct": far_limit,
        "bcr_limit_pct": limit["bcr_limit_pct"],
        "lot_area": round(lot_area, 1),
        "existing_floor_area": round(existing, 1),
        "existing_far_pct": existing_far,
        "remaining_far_pct": round(far_limit - existing_far, 1),
        "max_total_floor_area": max_total,
        "remaining_floor_area": round(max_total - existing, 1),
        "over_limit": existing_far > far_limit,
        "note": "국토계획법 시행령 용적률/건폐율 상한 기준 — 지자체 조례로 강화(하향) 가능, 확인 필요",
    }
