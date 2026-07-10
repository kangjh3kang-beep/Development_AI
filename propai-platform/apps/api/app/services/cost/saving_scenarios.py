"""P4 T1 — 공사비 절감 시나리오 Top-N.

alternatives_engine(D1 대안설계 원가비교 엔진)을 그대로 재사용한다 — 새 원가 계산 로직을
만들지 않고, 결정론 변형 후보를 자동 생성해 일괄 delta를 내고 절감액(음수 delta) 기준으로
랭킹만 얹는다(라우터 재호출 없이 서비스 함수 직접 호출 — scenario_matrix.py의 "베이스 1개 +
여러 overrides를 병렬 비교" 패턴과 동일 계열).

지원 override 축은 alternatives_engine.ALLOWED_OVERRIDE_KEYS 중 3개뿐이다(발명 금지):
  - 구조: RC ↔ 철골(SC) — standard_quantity_estimator.STRUCTURE_FACTORS 가 실제로 인식하는
    코드만 쓴다("철골" 같은 미등록 별칭은 원가엔진이 조용히 무시(계수 1.0)해 가짜 대안이 됨).
  - 층수: 지상층수 ±1·±2(연면적 불변 — alternatives 기존 UI와 동일한 override 방식).
  - GFA: 연면적 -5%·-10%(절감 취지상 축소만 다룸 — 확대는 절감 시나리오가 아님).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.cost.alternatives_engine import build_boq_for_params, diff_variant, merge_params

MAX_CANDIDATES = 10
DEFAULT_TOP_N = 5

# RC ↔ 철골(SC) 구조계수 교환 — base가 RC면 SC로, 그 외(SC/SRC/PC/목구조 등)는 RC로 되돌린다.
# standard_quantity_estimator.STRUCTURE_FACTORS 실코드 값(RC/SRC/SC/PC/목구조)만 사용.
_STRUCTURE_SWAP: dict[str, str] = {"RC": "SC"}
_FLOOR_DELTAS = (-2, -1, 1, 2)
_GFA_PCTS = (-5, -10)  # 절감 시나리오이므로 축소만


@dataclass
class Variant:
    """절감 후보 1건 — alternatives 계약과 동일한 overrides + 설명(label/rationale)."""

    label: str
    overrides: dict[str, Any]
    rationale: str


def build_variant_candidates(base_spec: dict[str, Any]) -> list[Variant]:
    """base_spec(alternatives의 base_params와 동일 계약)으로 결정론 변형 후보를 생성한다.

    캡 10(요구사항) — 구조 1건 + 층수 최대 4건(floor_count_above<1 조합은 스킵) + GFA 2건
    = 최대 7건으로 자연히 캡 이내다.
    """
    bp = merge_params(base_spec, {})
    base_structure = bp["structure_type"]
    base_floors = bp["floor_count_above"]
    base_gfa = bp["total_gfa_sqm"]

    candidates: list[Variant] = []

    # 1) 구조 교환(RC↔SC) — 변화가 있을 때만(이미 SC/그 외인데 다시 RC로 가는 경우도 포함).
    alt_structure = _STRUCTURE_SWAP.get(base_structure, "RC")
    if alt_structure != base_structure:
        candidates.append(Variant(
            label=f"구조형식 {base_structure}→{alt_structure}",
            overrides={"structure_type": alt_structure},
            rationale=f"구조형식을 {base_structure}에서 {alt_structure}로 변경(구조계수 차이만큼 골조 물량·단가 변동)",
        ))

    # 2) 층수 ±1·±2(연면적 불변).
    for d in _FLOOR_DELTAS:
        nf = base_floors + d
        if nf < 1:
            continue
        candidates.append(Variant(
            label=f"층수 {d:+d} ({base_floors}→{nf}층)",
            overrides={"floor_count_above": nf},
            rationale=(
                f"지상 층수를 {base_floors}층에서 {nf}층으로 변경(연면적 유지 — "
                f"원가엔진상 15층 이상 구간에서만 직접비에 영향)"
            ),
        ))

    # 3) GFA -5%·-10%.
    for pct in _GFA_PCTS:
        ngfa = round(base_gfa * (1 + pct / 100), 1)
        if ngfa <= 0:
            continue
        candidates.append(Variant(
            label=f"연면적 {pct}%",
            overrides={"total_gfa_sqm": ngfa},
            rationale=f"연면적을 {base_gfa:,.0f}㎡에서 {ngfa:,.0f}㎡로 {abs(pct)}% 축소(전 공종 물량이 비례 감소)",
        ))

    return candidates[:MAX_CANDIDATES]


def _tradeoff_note(rationale: str, diff: dict[str, Any], affected: list[dict[str, Any]]) -> str:
    """정직 서술 — 실제 재산정된 delta·delta_pct·영향공종(WB)만 사용한다(수치 날조 금지)."""
    wb_names = sorted({a["wb_name"] for a in affected if a.get("wb_name")})
    wb_note = f"영향 공종: {', '.join(wb_names)}" if wb_names else "유의미한 공종 영향 없음(±0.5% 미만)"
    return f"{rationale} → 총공사비 {diff['delta']:+,}원({diff['delta_pct']:+.2f}%), {wb_note}"


async def rank_savings(
    base_spec: dict[str, Any], candidates: list[Variant], top_n: int = DEFAULT_TOP_N,
) -> dict[str, Any]:
    """후보별로 alternatives 엔진을 재실행해 delta를 내고, 절감액(음수 delta) 내림차순 Top-N을 낸다.

    savings = -delta(양수만 "절감"). 후보가 실제로 비용을 늘리는 경우(delta>=0)는 절감이 아니므로
    랭킹에서 제외한다(정직 — "절감 Top-N"에 비절감 후보를 억지로 채우지 않음).
    """
    bp = merge_params(base_spec, {})
    if bp["total_gfa_sqm"] <= 0:
        raise ValueError("base_spec.total_gfa_sqm > 0 필요")

    base_boq = await build_boq_for_params(bp)
    base_total = int(base_boq["summary"]["total"])
    base_by_code = {it["code"]: it["amount"] for it in base_boq["items"]}

    evaluated: list[dict[str, Any]] = []
    for c in candidates:
        vp = merge_params(base_spec, c.overrides)
        vb = await build_boq_for_params(vp)
        d = diff_variant(bp, base_total, base_by_code, vp, vb, c.label)
        affected = d.get("affected_details", [])
        savings = -d["delta"]
        evaluated.append({
            "label": c.label,
            "rationale": c.rationale,
            "overrides": c.overrides,
            "total": d["total"],
            "delta": d["delta"],
            "delta_pct": d["delta_pct"],
            "savings": savings,
            "affected_work_types": d["affected_work_types"],
            "affected": affected,
            "tradeoff": _tradeoff_note(c.rationale, d, affected),
        })

    savers = [e for e in evaluated if e["savings"] > 0]
    savers.sort(key=lambda e: e["savings"], reverse=True)
    top = savers[:top_n]

    return {
        "base_total": base_total,
        "top_n": top_n,
        "evaluated_count": len(evaluated),
        "saving_count": len(savers),
        "candidates": top,
        "note": (
            "절감 시나리오는 대안설계 원가비교(D1) 엔진 재사용 — 건축개요 기반 개산(±12%)이며 "
            "전문 적산사 검토를 권장합니다. 절감효과(savings>0)가 있는 후보만 포함됩니다."
        ),
    }
