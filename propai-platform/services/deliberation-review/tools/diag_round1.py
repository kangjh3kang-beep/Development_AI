"""라운드1 진단 — run_analysis 다중 시나리오 다각도 실측(단선/병목/정합성).

실행: cd apps/api && ../../.venv/bin/python ../../tools/diag_round1.py
"""
from __future__ import annotations

import json
import time
from datetime import date

from app.contracts.analysis import AnalysisInput
from app.services.pipeline.analysis_pipeline import run_analysis

_IFC = """ISO-10303-21;
DATA;
#1= IFCWALLSTANDARDCASE('guid-w1',#2,'외벽-1',$,$);
#2= IFCSTAIR('guid-s1',#2,'직통계단-1',$,$);
#3= IFCSLAB('guid-b1',#2,'지하층 슬래브',$,$);
#4= IFCSPACE('guid-p1',#2,'주차장',$,$);
#5= IFCBUILDINGELEMENTPROXY('guid-x1',#2,'미상요소',$,$);
ENDSEC;
END-ISO-10303-21;
"""

_BASE = AnalysisInput(
    pnu="1111010100100000002",
    application_date=date(2026, 1, 1),
    axis_date=date(2026, 1, 1),
    drawing={"scale_text": "1:100"},
    calc_targets=[
        {"target": "building_area", "payload": {"outer_area": 600.0},
         "elements": [{"semantic_type": "PILOTIS", "area": 100.0, "confidence": 0.95}]},
    ],
    rules=[
        {"rule": {"rule_id": "far_limit", "comparator": "<=", "basis_article": "국토계획법 시행령",
                  "relaxations": [{"relaxation_id": "far_relax", "prerequisite_rule_id": "public_space"}]},
         "measured": 250.0, "limit": 200.0, "relaxation_states": {"public_space": "MET"}, "confidence": 0.9},
        {"rule": {"rule_id": "height_limit", "comparator": "<=", "basis_article": "건축법 시행령"},
         "measured": 30.0, "limit": 20.0, "confidence": 0.9},
    ],
    sim_inputs={
        "sunlight": {"latitude": 37.5, "building_height": 30.0, "adjacent_distance": 12.0, "geom_confidence": 0.9},
        "parking": {"turn_radius": 5.0, "geom_confidence": 0.9},
    },
    issue="FAR_DISPUTE",
    corpus=[{"case_id": f"c{i}", "source": f"의결서-{i}", "decision_type": "CONDITIONAL",
             "issue_labels": ["FAR_DISPUTE"], "conditions": ["공개공지 확대"]} for i in range(8)],
    mirror_rules=[{"ref": "건축법 시행령", "effective_date": "2025-01-01"}],
    citations=[{"ref": "건축법 시행령"}],
    qual_facts=[{"feature": "경관조화", "candidate_rubric": "경관 심의기준 3.1",
                 "mapping_confidence": 0.9, "compatibility": 0.8, "criterion_exists": True}],
)


def _g(it, key):
    return it.get(key) if isinstance(it, dict) else getattr(it, key, None)


def summ(r) -> dict:
    return {
        "drawing_source": r.drawing_source,
        "drawing_n": r.drawing_elements_n,
        "calc_src": r.calc_targets_source,
        "precedent_src": r.precedent_source,
        "mirror_src": r.mirror_source,
        "extraction": r.extraction_source,
        "bim_n": len(r.bim_elements),
        "preflight": bool(r.preflight),
        "legalq": [round(q.value, 1) for q in r.legal_quantities],
        "findings": [[f.rule_id, f.verdict.value, round(f.composite_confidence, 2),
                      list(getattr(f, "conflicts", []) or [])] for f in r.findings],
        "report_status": [[_g(it, "item_id"), _g(it, "status"), _g(it, "confidence_grade")]
                          for it in r.report.items],
        "sim": [[m.metric_id, round(m.value, 2), m.flags] for m in r.sim_metrics],
        "precedent": (list(r.precedent.distribution.items()) if r.precedent else None),
        "qual_n": len(r.qualitative),
        "reg_graph": bool(r.reg_graph),
        "skipped_n": len(r.skipped),
        "hash": r.input_hash[:12],
    }


def scen():
    s = {}
    s["S1_full_2D"] = _BASE
    s["S2_bim_design"] = _BASE.model_copy(update={"ifc": _IFC})
    s["S3_2D_fallback"] = _BASE.model_copy(update={
        "ifc": None, "elements": [{"element_id": "e1", "features": {"semantic_hint": "PILOTIS", "hint_strength": 0.9}}]})
    # P-A: 도면 자동해석(힌트 경로) → 요소 자동추출 → extraction VLLM
    s["S8_drawing_auto"] = _BASE.model_copy(update={"ifc": None, "elements": [], "drawings": [
        {"sheet_id": "A-PLAN", "sheet_role": "PLAN",
         "element_hints": [{"semantic_hint": "PILOTIS", "hint_strength": 0.9, "area": 100.0},
                           {"semantic_hint": "PARKING", "hint_strength": 0.85}]}]})
    s["S4_minimal_empty"] = AnalysisInput(pnu="1111010100100000002", application_date=date(2026, 1, 1),
                                          drawing={"scale_text": "1:100"})
    # 위반: far 완화 전제 미충족(NOT_MET) + 초과 → NON_COMPLIANT 기대
    s["S5_violation"] = _BASE.model_copy(update={"rules": [
        {"rule": {"rule_id": "far_limit", "comparator": "<=", "basis_article": "국토계획법 시행령"},
         "measured": 250.0, "limit": 200.0, "confidence": 0.9}]})
    # 저신뢰: 분류 confidence 0.3 → NEEDS_REVIEW 게이팅 기대
    s["S6_low_conf"] = _BASE.model_copy(update={"rules": [
        {"rule": {"rule_id": "far_limit", "comparator": "<=", "basis_article": "국토계획법 시행령"},
         "measured": 180.0, "limit": 200.0, "confidence": 0.3}]})
    # 충돌: conflicts → NEEDS_REVIEW 기대
    s["S7_conflict"] = _BASE.model_copy(update={"rules": [
        {"rule": {"rule_id": "far_limit", "comparator": "<=", "basis_article": "국토계획법 시행령"},
         "measured": 180.0, "limit": 200.0, "confidence": 0.9, "conflicts": ["mirror_mismatch"]}]})
    return s


def main():
    results = {}
    for name, inp in scen().items():
        t0 = time.perf_counter()
        try:
            r = run_analysis(inp)
            dt = (time.perf_counter() - t0) * 1000
            results[name] = {"ms": round(dt, 1), **summ(r)}
        except Exception as e:  # noqa: BLE001
            results[name] = {"ERROR": f"{type(e).__name__}: {str(e)[:200]}"}
        print(json.dumps({name: results[name]}, ensure_ascii=False))

    # 결정론: S1 두 번 → hash 동일 + 전체 동일
    a = run_analysis(_BASE)
    b = run_analysis(_BASE)
    print(json.dumps({"DETERMINISM": {"hash_equal": a.input_hash == b.input_hash,
                                       "full_equal": a == b}}, ensure_ascii=False))

    # 성능 워밍업 후 10회 평균(병목 측정)
    n = 10
    t0 = time.perf_counter()
    for _ in range(n):
        run_analysis(_BASE)
    avg = (time.perf_counter() - t0) / n * 1000
    print(json.dumps({"PERF": {"runs": n, "avg_ms": round(avg, 2)}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
