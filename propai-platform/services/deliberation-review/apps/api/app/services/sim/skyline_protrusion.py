"""스카이라인 돌출도 — 신축안 층수 vs 주변 스카이라인(가로경관 연속성·경관심의 참고).

주변 평균/최고 층수 대비 신축안의 돌출 정도를 정량화. 주변 최고 초과·평균 대비 배수로 등급화.
결정론. 신축안/스카이라인 결손 None.
"""
from __future__ import annotations

_HIGH_MULTIPLE = 2.0  # 주변 최고의 N배 초과 시 HIGH


def skyline_protrusion(skyline: dict | None, proposed_floors: int | None,
                       high_multiple: float = _HIGH_MULTIPLE) -> dict | None:
    """신축안 층수 + 주변 스카이라인 → 돌출도(평균 대비 배수·최고 초과·등급). 결손 None."""
    if not skyline or not proposed_floors or proposed_floors <= 0:
        return None
    avg = skyline.get("avg_floors")
    mx = skyline.get("max_floors")
    out: dict = {
        "proposed_floors": proposed_floors,
        "context_avg_floors": avg,
        "context_max_floors": mx,
    }
    if avg:
        out["ratio_vs_avg"] = round(proposed_floors / avg, 2)
    if mx:
        out["exceeds_context_max"] = proposed_floors > mx
        if proposed_floors > mx * high_multiple:
            level = "HIGH"
        elif proposed_floors > mx:
            level = "MEDIUM"
        else:
            level = "LOW"
        out["protrusion_level"] = level
    out["note"] = "가로경관 연속성·돌출도 — 경관심의 참고(주변 스카이라인 대비, 절대 높이제한과 별개)"
    return out
