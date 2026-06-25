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


# 최소요건(>=) 위반 유형 — 그 외는 상한(<=) 초과. design_audit/building_compliance 공유.
_GE_TYPES = {"setback", "sunlight"}

# ⚠️ comprehensive_analysis는 shadow 대상에서 제외(정직): 플랫폼에 FAR/BCR '적합 verdict'가 없고,
# effective_far는 합법 완화근거(지구단위계획 상한·기부채납)로 법정상한을 정당히 초과할 수 있어
# (far_tier_service: 법정상한의 최대 2배) 법정 대비 단순 비교는 거짓 발산만 낳는다. verdict 합성 불가 →
# 미배선. 정량(effective vs 적용한도) 관측 shadow는 엔진 정량 노출 후속 트랙에서 재검토.


def _comparator_for(rule_id: str) -> str:
    """check_id/type에 setback·sunlight(최소요건)이 포함되면 >=, 그 외 상한 <=."""
    return ">=" if any(g in rule_id for g in _GE_TYPES) else "<="


# finding status → 등급(엔진이 보는 수치 finding subset의 worst status로 scope-정합 verdict 산출).
_STATUS_SEV = {"fail": 3, "warning": 2, "pass": 1}


def design_audit(result: dict[str, Any]) -> Mapped | None:
    """설계심사 → 엔진 rules로 변환되는 **수치 finding subset**만 비교(scope-정합). platform_verdict는
    overall.verdict_en(전 체크 종합, 비수치 parking/permit/solar 포함)이 아니라 그 subset의 worst status로
    산출 → 엔진이 같은 rules로 도출한 verdict와 apples-to-apples(범위 불일치 거짓발산 제거).
    setback/sunlight는 >= comparator. 수치 finding 없으면 None(생략)."""
    rules = []
    worst_status, worst_sev = "", -1
    for i, f in enumerate(result.get("findings") or []):
        if not isinstance(f, dict):
            continue
        rid = str(f.get("check_id") or f.get("engine") or "").strip() or f"chk{i}"  # 폴백도 고유(rule dedup 방지)
        r = _rule(rid, _comparator_for(rid), f.get("current"), f.get("limit"))
        if not r:
            continue  # 비수치(parking/permit/solar/grammar 등) — 엔진 rule 변환 불가 → subset 제외
        rules.append(r)
        st = str(f.get("status") or "").lower()
        sev = _STATUS_SEV.get(st, 0)
        if sev > worst_sev:
            worst_sev, worst_status = sev, st
    if not rules:
        return None  # 비교 가능한 정량 체크 없음 → 생략(거짓발산 방지)
    # subset worst status가 곧 platform이 그 rules에 내린 판정(엔진과 동일 범위).
    return worst_status or "pass", {"rules": rules}, rules[0]["measured"]


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
