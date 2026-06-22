"""스카이라인 돌출도 — 신축안 층수 vs 주변 스카이라인(가로경관 연속성·경관심의 참고).

주변 평균/최고 층수 대비 신축안의 돌출 정도를 정량화. 주변 최고 초과·평균 대비 배수로 등급화.
결정론. 신축안/스카이라인 결손 None.
"""
from __future__ import annotations

from app.contracts.rationale import Rationale, RationaleInput
from app.services.explain.legal_refs import refs

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
    out["rationale"] = Rationale(
        summary=(f"신축 {proposed_floors}층 vs 주변 평균 {avg}·최고 {mx}층"
                 + (f" → {out['protrusion_level']}" if mx else "")),
        formula=f"등급: 주변최고×{high_multiple} 초과=HIGH, 주변최고 초과=MEDIUM, 이내=LOW; 평균배수=신축÷주변평균",
        inputs=[
            RationaleInput(name="신축안 층수", value=proposed_floors),
            RationaleInput(name="주변 평균층수", value=avg, source="VWORLD lt_c_bldginfo 표본 반경 집계"),
            RationaleInput(name="주변 최고층수", value=mx, source="VWORLD lt_c_bldginfo 표본 반경 집계"),
            RationaleInput(name="HIGH 임계 배수", value=high_multiple),
        ],
        legal_basis=refs("경관법§9", "건축법§60"),
        caveats=[
            "주변 대비 상대 돌출(경관심의 참고) — 절대 높이제한(건축법 §60·고도지구)과 별개",
            "주변 평균/최고는 표본 반경 내 VWORLD 건축물 집계(표본·반경 의존)",
        ],
    ).model_dump()
    return out


def protrusion_metric(prot: dict | None):
    """skyline_protrusion 결과 → SimMetric(emit 게이트로 근거 강제·돌출 flag). 결손 None."""
    if prot is None:
        return None
    from app.contracts.sim_metric import MethodTrace, MetricStatus, SimMetric, emit
    r = prot.get("rationale", {})
    val = prot.get("ratio_vs_avg")
    level = prot.get("protrusion_level")
    flags = [f"skyline_protrusion_{level.lower()}"] if level in ("HIGH", "MEDIUM") else []
    return emit(SimMetric(
        metric_id="skyline_protrusion", value=val, unit="ratio",
        status=MetricStatus.OK if val is not None else MetricStatus.UNAVAILABLE,
        method_trace=MethodTrace(
            model="skyline_vs_context",
            assumptions=r.get("caveats", []),
            inputs={i["name"]: i["value"] for i in r.get("inputs", [])},
            basis_article="경관법 제9조·지자체 경관조례"),
        flags=flags,
    ))
