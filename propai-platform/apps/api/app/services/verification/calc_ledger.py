"""결정론적 수치-원장(Calc Ledger) — 분석 출력의 계산 환각을 Python 재계산으로 적발.

LLM 판단과 무관하게, 한국 부동산 결정론 산식(용적률=연면적/대지×100, 매출−원가=이익,
수익률=이익/원가×100, 평당공사비=총공사비/연면적평, 세액=과표×세율)을 직접 재실행해
원본/출력에 적힌 '주장값'과 ε 오차로 대조한다. 입력·주장값이 모두 존재하는 산식만 검사한다.

설계 원칙:
- 데이터에 없는 값은 추정하지 않는다(검사 미수행). 거짓 음성 < 거짓 양성.
- 상대오차 허용 2%(반올림·표시단위 차이 흡수). 초과 시 high 이슈.
"""

from __future__ import annotations

from typing import Any

_PYEONG = 3.305785  # 1평 = 3.305785㎡
_REL_TOL = 0.02     # 상대오차 허용 2%


def _num(v: Any) -> float | None:
    try:
        if isinstance(v, bool):
            return None
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def _deep_find(obj: Any, keys: tuple[str, ...]) -> float | None:
    """중첩 dict/list에서 후보 키들 중 최초로 발견되는 유한 숫자값(깊이우선)."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                n = _num(obj[k])
                if n is not None:
                    return n
        for v in obj.values():
            r = _deep_find(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find(v, keys)
            if r is not None:
                return r
    return None


# (이름, 산식설명, 입력키 목록, 주장값키, recompute(inputs)->float)
_CHECKS: list[dict[str, Any]] = [
    {
        "name": "용적률(FAR)",
        "formula": "연면적 / 대지면적 × 100",
        "inputs": {"gfa": ("total_gfa_sqm", "gfa", "total_floor_area_sqm"),
                   "land": ("land_area_sqm", "land_area", "lot_area_sqm")},
        "claimed": ("far", "floor_area_ratio", "far_pct"),
        "fn": lambda i: i["gfa"] / i["land"] * 100 if i["land"] else None,
    },
    {
        "name": "건폐율(BCR)",
        "formula": "건축면적 / 대지면적 × 100",
        "inputs": {"bldg": ("building_area_sqm", "building_area", "footprint_sqm"),
                   "land": ("land_area_sqm", "land_area", "lot_area_sqm")},
        "claimed": ("bcr", "building_coverage_ratio", "bcr_pct"),
        "fn": lambda i: i["bldg"] / i["land"] * 100 if i["land"] else None,
    },
    {
        "name": "순이익",
        "formula": "분양매출 − 총사업비",
        "inputs": {"rev": ("total_revenue_won", "total_revenue", "revenue_won", "sales_revenue_won"),
                   "cost": ("total_cost_won", "total_cost", "total_project_cost_won")},
        "claimed": ("net_profit_won", "net_profit", "profit_won", "operating_profit_won"),
        "fn": lambda i: i["rev"] - i["cost"],
    },
    {
        "name": "수익률(ROI)",
        "formula": "(분양매출 − 총사업비) / 총사업비 × 100",
        "inputs": {"rev": ("total_revenue_won", "total_revenue", "revenue_won"),
                   "cost": ("total_cost_won", "total_cost", "total_project_cost_won")},
        "claimed": ("profit_rate_pct", "roi", "roi_pct", "profit_rate"),
        "fn": lambda i: (i["rev"] - i["cost"]) / i["cost"] * 100 if i["cost"] else None,
    },
    {
        "name": "평당 공사비",
        "formula": "총공사비 / (연면적 ÷ 3.3058)",
        "inputs": {"cost": ("total_construction_cost_won", "total_won", "total_construction_cost"),
                   "gfa": ("total_gfa_sqm", "gfa", "total_floor_area_sqm")},
        "claimed": ("per_pyeong_won", "cost_per_pyeong", "per_pyeong"),
        "fn": lambda i: i["cost"] / (i["gfa"] / _PYEONG) if i["gfa"] else None,
    },
    {
        "name": "취득세",
        "formula": "과세표준 × 세율",
        "inputs": {"base": ("base_won", "tax_base_won", "purchase_won"),
                   "rate": ("rate", "base_rate", "tax_rate")},
        "claimed": ("acquisition_tax_won", "amount_won", "acquisition_tax"),
        "fn": lambda i: i["base"] * i["rate"],
    },
]


def run_calc_checks(source: Any, output: Any) -> dict[str, Any]:
    """원본+출력에서 재계산 가능한 산식을 찾아 결정론 검증. 검사결과·통과율·이슈 반환."""
    haystack = [output, source]  # 주장값은 출력 우선
    checks: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []

    for c in _CHECKS:
        # 입력값 수집(출력→원본 순서로 탐색)
        inputs: dict[str, float] = {}
        ok_inputs = True
        for var, keys in c["inputs"].items():
            val = None
            for h in haystack:
                val = _deep_find(h, keys)
                if val is not None:
                    break
            if val is None:
                ok_inputs = False
                break
            inputs[var] = val
        if not ok_inputs:
            continue

        claimed = None
        for h in haystack:
            claimed = _deep_find(h, c["claimed"])
            if claimed is not None:
                break
        if claimed is None:
            continue  # 주장값 없으면 대조 불가 → 미검사

        try:
            recomputed = c["fn"](inputs)
        except Exception:  # noqa: BLE001
            recomputed = None
        if recomputed is None:
            continue

        denom = max(abs(claimed), abs(recomputed), 1.0)
        diff_pct = abs(claimed - recomputed) / denom * 100
        ok = diff_pct <= _REL_TOL * 100
        checks.append({
            "name": c["name"], "formula": c["formula"],
            "claimed": round(claimed, 4), "recomputed": round(recomputed, 4),
            "diff_pct": round(diff_pct, 2), "ok": ok,
        })
        if not ok:
            issues.append({
                "type": "계산오류",
                "claim": f"{c['name']} {claimed:,.2f}",
                "severity": "high",
                "note": f"결정론 재계산({c['formula']}) = {recomputed:,.2f} 와 불일치(Δ{diff_pct:.1f}%)",
            })

    total = len(checks)
    passed = sum(1 for c in checks if c["ok"])
    return {
        "checks": checks,
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total * 100, 1) if total else None,
        "issues": issues,
    }
