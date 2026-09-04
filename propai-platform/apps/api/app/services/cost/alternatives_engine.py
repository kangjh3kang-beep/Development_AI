"""D1 대안설계 원가비교 엔진(공용) — app/routers/cost.py에 인라인이던 로직을 서비스로
추출한다(전파방지: 같은 계산을 라우터가 다시 구현하지 않고 여기 한 곳만 고치면 됨).

계약(override 축)은 기존 라우터가 실제로 지원하던 5개 키 그대로다(발명 금지):
  building_type · total_gfa_sqm · floor_count_above · floor_count_below · structure_type

P4(saving_scenarios.py — 절감 Top-N, change_forecast.py — 설계변경 예측공사비)가 라우터를
다시 호출하는 대신 이 모듈의 함수를 직접 재사용해 같은 BOQ 재산정 엔진으로 delta를 낸다.
"""

from __future__ import annotations

from typing import Any

from app.services.cost.boq_builder import build_boq

# 대안설계가 지원하는 override 축(원본 cost.py._merge_params의 allowed 키와 동일).
ALLOWED_OVERRIDE_KEYS = frozenset({
    "building_type", "total_gfa_sqm", "floor_count_above",
    "floor_count_below", "structure_type",
})


def merge_params(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """base_params + overrides 병합(허용 5축만 반영 — 원본 로직 그대로 이전)."""
    out = {
        "building_type": base.get("building_type", "apartment"),
        "total_gfa_sqm": float(base.get("total_gfa_sqm", 0) or 0),
        "floor_count_above": int(base.get("floor_count_above", 1) or 1),
        "floor_count_below": int(base.get("floor_count_below", 0) or 0),
        "structure_type": base.get("structure_type", "RC"),
    }
    for k, v in (overrides or {}).items():
        if k in ALLOWED_OVERRIDE_KEYS and v is not None:
            out[k] = v
    out["total_gfa_sqm"] = float(out["total_gfa_sqm"])
    out["floor_count_above"] = int(out["floor_count_above"])
    out["floor_count_below"] = int(out["floor_count_below"])
    return out


async def build_boq_for_params(params: dict[str, Any]) -> dict[str, Any]:
    """정규화된 params(merge_params 결과)로 BOQ를 산정한다.

    qto_source="derived" 고정 — 대안/절감/예측 비교는 항상 건축개요 기반 추정(±12%)이다
    (BIM 실치수는 이 비교 경로의 범위 밖 — 실제 alternatives 라우터와 동일 계약).
    """
    return await build_boq(
        building_type=params["building_type"], total_gfa_sqm=params["total_gfa_sqm"],
        floor_count_above=params["floor_count_above"], floor_count_below=params["floor_count_below"],
        structure_type=params["structure_type"], qto_source="derived",
    )


def diff_variant(
    base_params: dict[str, Any],
    base_total: int,
    base_by_code: dict[str, int],
    variant_params: dict[str, Any],
    variant_boq: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    """base 대비 variant의 총액 델타·델타%·영향공종·rationale(원본 cost.py 로직 그대로).

    affected_work_types: 항목명 리스트(기존 /alternatives 응답 계약 — 무회귀 유지).
    affected_details: 항목명 + WB 대공종(wb_code/wb_name) + 항목별 델타금액(additive — P4가
    "영향 공종을 WB로 병기"하는 데 재사용. work_breakdown 브리지를 다시 부르지 않고 build_boq가
    이미 각 항목에 붙여둔 wb_code/wb_name을 그대로 투영한다 — 중복 계산 금지).
    """
    v_total = int(variant_boq["summary"]["total"])
    delta = v_total - base_total
    affected_details: list[dict[str, Any]] = []
    for it in variant_boq["items"]:
        b_amt = base_by_code.get(it["code"], 0)
        amt_delta = it["amount"] - b_amt
        if abs(amt_delta) > max(1, base_total * 0.005):
            affected_details.append({
                "name": it["name"], "wb_code": it.get("wb_code"), "wb_name": it.get("wb_name"),
                "delta_amount": amt_delta,
            })
    rationale = ", ".join(
        f"{k}={variant_params[k]}" for k in
        ("structure_type", "floor_count_above", "floor_count_below", "total_gfa_sqm")
        if variant_params[k] != base_params[k]
    ) or "변경 없음"
    return {
        "label": label, "total": v_total,
        "delta": delta, "delta_pct": round(delta / base_total * 100, 2) if base_total else 0,
        "affected_work_types": [a["name"] for a in affected_details[:8]],
        "affected_details": affected_details[:8],
        "rationale": rationale,
    }
