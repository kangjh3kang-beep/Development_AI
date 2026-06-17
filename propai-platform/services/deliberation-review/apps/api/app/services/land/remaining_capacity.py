"""잔여 개발용량 산정 — 용도지역 법정 용적률 상한 − 기존 용적률(remaining FAR).

증축/재건축 심의안의 규모 적정성 자동 판정. 기존 연면적(getBuildingUse)/대지면적(토지특성) →
기존 용적률, 법정 상한과의 차로 잔여 용량. 기존이 상한 초과(기존불적합)면 over_limit 표면화.
PNU 제공 시 시도 조례 용적률 우선(시행령 상한만 쓰던 모순 해소). 모든 산출에 rationale(도출식·
법령) 동반. 결정론.
"""
from __future__ import annotations

from datetime import date

from app.contracts.rationale import Rationale, RationaleInput
from app.services.explain.legal_refs import refs
from app.services.land.upzoning import ordinance_far
from app.services.land.zone_limits import lookup_zone_limit


def remaining_capacity(zone_name: str | None, lot_area: float | None,
                       existing_floor_area: float | None,
                       pnu: str | None = None, as_of: date | None = None) -> dict | None:
    """{법정한도·기존용적률·잔여FAR·최대연면적·잔여연면적·초과여부·rationale}. 매칭/면적 결손 None.

    pnu 제공 시 조례 용적률 우선(없으면 시행령 상한), as_of 제공 시 한시완화(조건부) 표면화.
    """
    limit = lookup_zone_limit(zone_name)
    if limit is None or not lot_area or lot_area <= 0:
        return None
    zone = limit["zone_matched"]
    of = ordinance_far(pnu, zone, as_of) if pnu else None
    far_limit = of["far_pct"] if of else limit["far_limit_pct"]
    far_source = of["source"] if of else "시행령 상한"
    existing = existing_floor_area or 0.0
    existing_far = round(existing / lot_area * 100, 1)
    max_total = round(far_limit / 100 * lot_area, 1)
    over = existing_far > far_limit
    remaining_far = round(far_limit - existing_far, 1)
    remaining_floor = round(max_total - existing, 1)

    basis_ids: list[str] = []
    if of and of.get("ref_id"):
        basis_ids.append(of["ref_id"])
    if "국토계획법시행령§85" not in basis_ids:
        basis_ids.append("국토계획법시행령§85")
    basis_ids.append("건축법시행령§119")  # 용적률 산정 연면적 정의
    if over:
        basis_ids.append("건축법§6")

    caveats = ["max_total_floor_area는 이론상 최대 — 일조(정북)·높이·주차 등 타 규제로 실제 도달 불가",
               "기존 용적률은 총연면적(buldTotar) 기준 근사 — 용적률 산정 연면적(지하·주차 제외)과 다를 수 있음"]
    if not pnu:
        caveats.append("조례 미반영(PNU 미제공) — 시행령 상한 기준(조례 강화 시 하향 가능)")
    elif far_source == "시행령 상한":
        caveats.append(f"시도({(pnu or '')[:2]}) 조례 미등록 — 시행령 상한 기준(조례 강화 시 하향 가능)")
    if over:
        caveats.append("기존 상한 초과(기존불적합) — 과거 더 높은 상한에서 합법 건축 추정, "
                       "증축 제한·재건축 시 규모 축소(건축법 §6 특례)")
    if of and of.get("temporary_relaxation"):
        tr = of["temporary_relaxation"]
        caveats.append(f"한시완화 가능(조건부): {tr['far_pct']}%까지({tr['until']}) — {tr['condition']}")

    summary = (f"법정 상한 {far_limit}%({far_source}) vs 기존 {existing_far}% → "
               + (f"초과 {round(existing_far - far_limit, 1)}%p(기존불적합)" if over
                  else f"잔여 {remaining_far}%p / {remaining_floor}㎡"))
    rationale = Rationale(
        summary=summary,
        formula="기존용적률=기존연면적÷대지면적×100; 잔여FAR=법정상한−기존; 잔여연면적=상한연면적−기존연면적",
        inputs=[
            RationaleInput(name="대지면적(㎡)", value=round(lot_area, 1), source="vworld 토지특성 lndpclAr"),
            RationaleInput(name="기존연면적(㎡)", value=round(existing, 1), source="vworld 건축물 buldTotar 합"),
            RationaleInput(name="법정용적률상한(%)", value=far_limit, source=far_source),
        ],
        legal_basis=refs(*basis_ids),
        caveats=caveats,
    )
    return {
        "zone_matched": zone,
        "far_limit_pct": far_limit,
        "far_source": far_source,
        "bcr_limit_pct": limit["bcr_limit_pct"],
        "lot_area": round(lot_area, 1),
        "existing_floor_area": round(existing, 1),
        "existing_far_pct": existing_far,
        "remaining_far_pct": remaining_far,
        "max_total_floor_area": max_total,
        "remaining_floor_area": remaining_floor,
        "over_limit": over,
        "note": "용도지역 법정 용적률/건폐율 상한 기준(조례 우선, 없으면 시행령)",
        "rationale": rationale.model_dump(),
    }
