"""중심엔진 수렴 stage2 — 도메인 산출 → (platform_verdict, 엔진 payload, platform_value) 순수 매퍼.

각 매퍼는 도메인 결과 dict를 받아 shadow_compare에 넘길 3-튜플을 반환하거나, 매핑 불가/데이터 결손 시
None(→ 해당 호출은 shadow 생략, 운영 무영향). 순수함수라 단위테스트 용이. 매핑은 엔진 rules[] 계약
(_engine_contract.prevalidate)과 동일 형식(rule.rule_id 필수·comparator·measured/limit finite).

⚠️ 성격: 엔진에 플랫폼이 쓴 measured/limit를 그대로 넘겨 verdict 일치를 관측(엔진 파이프라인 정합·매핑
breakage 탐지의 sanity shadow). 규제 출처 divergence(플랫폼 ZONE_LIMITS vs 엔진 reg_graph 독립 한도)는
엔진이 결과에 독립 한도를 노출해야 가능 — 후속 트랙. 현재는 종단 통합 관측에 집중.
"""
from __future__ import annotations

import math
from typing import Any

Mapped = tuple[str, dict[str, Any], float | None]


def _finite_num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if math.isfinite(v) else None


def _rule(rule_id: str, comparator: str, measured: Any, limit: Any) -> dict[str, Any] | None:
    """엔진 rules 1행(measured/limit 유한 수치일 때만). prevalidate 통과 형식(rule_id 필수·comparator∈집합)."""
    m, lim = _finite_num(measured), _finite_num(limit)
    if m is None or lim is None:
        return None
    return {"rule": {"rule_id": rule_id, "comparator": comparator}, "measured": m, "limit": lim}


def _le_rule(rule_id: str, measured: Any, limit: Any) -> dict[str, Any] | None:
    return _rule(rule_id, "<=", measured, limit)


def comprehensive(result: dict[str, Any]) -> Mapped | None:
    """종합 부지분석 → FAR/BCR 적합 비교. effective_far_pct/bcr_pct vs 법정범위 max_*_pct(동일 단위 %)."""
    ef = result.get("effective_far")
    if not isinstance(ef, dict):
        return None
    legal = ((ef.get("far_basis_detail") or {}).get("법정범위")) or {}
    rules = []
    far = _le_rule("FAR", ef.get("effective_far_pct"), legal.get("max_far_pct"))
    bcr = _le_rule("BCR", ef.get("effective_bcr_pct"), legal.get("max_bcr_pct"))
    if far:
        rules.append(far)
    if bcr:
        rules.append(bcr)
    if not rules:
        return None  # 비교 가능한 정량 없음 → shadow 생략
    over = any(r["measured"] > r["limit"] for r in rules)
    verdict = "non_compliant" if over else "compliant"
    payload: dict[str, Any] = {"rules": rules}
    pnu = result.get("pnu")
    if isinstance(pnu, str) and len(pnu) == 19:
        payload["pnu"] = pnu  # lineage(19자리만 — prevalidate 패턴)
    return verdict, payload, rules[0]["measured"]


def design_audit(result: dict[str, Any]) -> Mapped | None:
    """설계심사 → overall.verdict_en(pass/fail/conditional) + 체크별 current/limit를 엔진 rules로 매핑.
    norm_verdict가 pass→compliant·fail→non_compliant·conditional→needs_review. 수치 finding 없으면 None."""
    overall = result.get("overall")
    if not isinstance(overall, dict):
        return None
    verdict = overall.get("verdict_en")  # 판정불가는 None → skip
    if not verdict:
        return None
    rules = []
    for f in result.get("findings") or []:
        if not isinstance(f, dict):
            continue
        rid = str(f.get("check_id") or f.get("engine") or "").strip() or "chk"
        r = _le_rule(rid, f.get("current"), f.get("limit"))
        if r:
            rules.append(r)
    if not rules:
        return None  # 비교 가능한 정량 체크 없음 → 생략(거짓발산 방지)
    return str(verdict), {"rules": rules}, rules[0]["measured"]


# 최소요건(>=) 위반 유형 — 그 외는 상한(<=) 초과.
_GE_TYPES = {"setback", "sunlight"}


def building_compliance(raw: dict[str, Any]) -> Mapped | None:
    """건축 법규검증 → 위반 케이스만 엔진 rules로 대조(적합 시 비교 데이터 없어 None=생략, 거짓발산 방지).
    violations[].current_value/limit_value + 유형별 comparator(setback/sunlight=>=, 그외 <=). sanity shadow."""
    if not isinstance(raw, dict) or raw.get("compliant"):
        return None  # 적합 → 위반 0건 → 비교 rule 없음 → 생략
    rules = []
    for v in raw.get("violations") or []:
        if not isinstance(v, dict):
            continue
        comp = ">=" if str(v.get("type")) in _GE_TYPES else "<="
        r = _rule(str(v.get("type") or "viol"), comp, v.get("current_value"), v.get("limit_value"))
        if r:
            rules.append(r)
    if not rules:
        return None
    return "non_compliant", {"rules": rules}, rules[0]["measured"]
