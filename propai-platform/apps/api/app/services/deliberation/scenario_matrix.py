"""심의 시나리오 매트릭스 — 하나의 부지 입력에 여러 '만약(overrides)'을 적용해 결정론 엔진을
N회 실행하고 나란히 비교한다(BE-4). 라우터(app/routers/deliberation.py)의 새 엔드포인트가
기존 analyze 흐름(build_input_dump→prevalidate→멱등캐시→_engine_post_analyze→_compat_fields)을
시나리오마다 재사용하고, 이 모듈은 (1) overrides를 base 입력에 안전하게 병합하는 순수함수와
(2) 엔진 결과를 매트릭스 응답 형태로 다듬는 순수함수만 담당한다(엔진 호출·DB·감사는 라우터 담당).

지원 overrides 축(엔진 `AnalysisInput` 실계약 확인 후 확정 — services/deliberation-review/.../contracts):
  1) relaxation_states: {rule_id: {완화상태키: 값}} — rules[].relaxation_states(완화 전제 적용/미적용)에 병합
  2) rules: [{rule_id, measured?, limit?, relaxation_states?}] — 기존 rule_id 매칭 시 measured/limit 대안값
     패치(예: FAR 대안 배치안 A/B), 미매칭 rule_id는 신규 룰 행으로 추가
  3) use_zone: "제3종일반주거지역" 같은 대상 용도지역명 — 엔진 AnalysisInput에는 zone 필드가 없으므로,
     플랫폼 권위 SSOT(app.services.zoning.auto_zoning_service.ZONE_LIMITS, reg_reconcile.py가 이미
     쓰는 것과 동일 출처)에서 대상 zone의 FAR/BCR 상한을 조회해 target_variable이 far_floor_area/
     building_area인 rules[]의 limit을 치환한다(종상향 시나리오의 실제 효과 — 값 없는 라벨만 붙이는
     목업 금지)
  4) calc_targets: [{target, payload?, declared?}] — target 매칭 시 payload 딕셔너리 얕은 병합(대지면적·
     계획GFA 등 변형), 미매칭 target은 신규 항목 추가

base 딕셔너리는 절대 변형하지 않는다(copy.deepcopy 후 패치) — 동일 base로 여러 시나리오를 병렬 실행해도
서로 오염되지 않아야 한다.
"""
from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, Field

# 매트릭스 1회 요청당 최대 시나리오 수 — 엔진 부하·응답시간 상한 가드(요구사항 캡 12).
MAX_SCENARIOS = 12


class ScenarioSpec(BaseModel):
    """시나리오 1건 — base AnalysisInput에 적용할 overrides. overrides 내부 구조는 위 모듈 docstring 참고."""

    scenario_id: str
    label: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class ScenarioMatrixRequest(BaseModel):
    """POST /deliberation/scenario-matrix 요청 본문. base는 기존 /analyze와 동일 계약(raw dict).
    scenarios 개수는 pydantic이 1~MAX_SCENARIOS로 강제(초과 시 FastAPI가 자동 422)."""

    base: dict[str, Any] = Field(default_factory=dict)
    scenarios: list[ScenarioSpec] = Field(..., min_length=1, max_length=MAX_SCENARIOS)


# ── overrides 병합(순수함수 — base 원본 불변) ──────────────────────────────────


def _rule_id(row: Any) -> str | None:
    """rules[] 항목({rule:{rule_id,...}, measured, limit, relaxation_states})에서 rule_id 추출.
    비정상 구조(딕셔너리 아님 등)는 None(무매칭 취급 — prevalidate가 별도로 형식 오류를 잡는다)."""
    if not isinstance(row, dict):
        return None
    rule = row.get("rule")
    return rule.get("rule_id") if isinstance(rule, dict) else None


def _apply_relaxation_states(rules: list[Any], patch: dict[str, dict[str, Any]]) -> tuple[list[Any], list[str]]:
    """rule_id별 relaxation_states 패치를 매칭되는 rules[] 항목에 병합(완화 전제 적용/미적용 시나리오).
    미매칭 rule_id는 무음 스킵하지 않고 warnings로 표면화."""
    matched: set[str] = set()
    for row in rules:
        rid = _rule_id(row)
        if rid is not None and rid in patch:
            existing = row.get("relaxation_states")
            row["relaxation_states"] = {**(existing if isinstance(existing, dict) else {}), **patch[rid]}
            matched.add(rid)
    warnings = [f"relaxation_states_no_matching_rule:{rid}" for rid in patch if rid not in matched]
    return rules, warnings


def _apply_rule_patches(rules: list[Any], patches: list[dict[str, Any]]) -> tuple[list[Any], list[str]]:
    """rule_id 매칭 시 measured/limit/relaxation_states 갱신(대안 배치안 A/B), 미매칭 rule_id는 새 룰 행 추가.

    ★독립리뷰 HIGH 반영: overrides는 클라이언트 입력이라 내부 구조가 검증돼 있지 않다 —
    비-dict 항목(예: 문자열)은 예외로 배치 전체를 죽이는 대신 경고로 표면화하고 건너뛴다
    (_apply_relaxation_states/_apply_use_zone의 isinstance 가드와 동일 방어 패리티)."""
    by_id: dict[str, int] = {}
    warnings: list[str] = []
    for i, row in enumerate(rules):
        rid = _rule_id(row)
        if rid is not None:
            by_id[rid] = i
    for patch in patches:
        if not isinstance(patch, dict):
            warnings.append(f"rules_patch_not_dict:{str(patch)[:40]}")
            continue
        rid = patch.get("rule_id")
        idx = by_id.get(rid) if rid else None
        if idx is not None:
            row = rules[idx]
            for key in ("measured", "limit"):
                if key in patch:
                    row[key] = patch[key]
            if isinstance(patch.get("relaxation_states"), dict):
                existing = row.get("relaxation_states")
                row["relaxation_states"] = {**(existing if isinstance(existing, dict) else {}),
                                            **patch["relaxation_states"]}
        else:
            rules.append(copy.deepcopy(patch))
    return rules, warnings


# 플랫폼 권위 zone→FAR/BCR 상한(auto_zoning_service.ZONE_LIMITS) 키 ↔ 엔진 rule.target_variable 매핑.
# reg_reconcile.py의 _METRICS와 동일 대응(FAR=far_floor_area, BCR=building_area) — 새로 지어내지 않고 재사용.
_ZONE_TARGET_VARS = (("max_far", "far_floor_area"), ("max_bcr", "building_area"))


def _apply_use_zone(rules: list[Any], use_zone: str) -> tuple[list[Any], str | None]:
    """종상향/종변경 시나리오 — 대상 용도지역 SSOT 상한으로 해당 target_variable 룰의 limit을 치환.
    엔진 AnalysisInput에 zone 필드가 없어 rules[].limit 치환으로 실제 효과를 낸다(값 없는 라벨 금지).
    zone 미상/매칭 룰 없음은 무음 통과가 아니라 (원본유지, 경고사유) 반환 — 정직 표면화."""
    from app.services.zoning.auto_zoning_service import ZONE_LIMITS

    limits = ZONE_LIMITS.get(use_zone)
    if limits is None:
        return rules, f"unknown_use_zone:{use_zone}"
    matched = False
    for row in rules:
        if not isinstance(row, dict):
            continue
        rule = row.get("rule")
        target_variable = rule.get("target_variable") if isinstance(rule, dict) else None
        for zone_key, target_var in _ZONE_TARGET_VARS:
            if target_variable == target_var and limits.get(zone_key) is not None:
                row["limit"] = limits[zone_key]
                matched = True
    return rules, (None if matched else f"use_zone_no_matching_rule:{use_zone}")


def _apply_calc_target_patches(targets: list[Any], patches: list[dict[str, Any]]) -> tuple[list[Any], list[str]]:
    """target 키 매칭 시 payload 얕은 병합(대지면적·계획GFA 변형), 미매칭 target은 새 항목 추가.

    ★독립리뷰 HIGH 반영: 비-dict 패치 항목은 경고 표면화 후 스킵(배치 생존 계약 보존)."""
    by_target: dict[str, list[int]] = {}
    warnings: list[str] = []
    for i, row in enumerate(targets):
        tk = row.get("target") if isinstance(row, dict) else None
        if tk:
            by_target.setdefault(tk, []).append(i)
    for patch in patches:
        if not isinstance(patch, dict):
            warnings.append(f"calc_targets_patch_not_dict:{str(patch)[:40]}")
            continue
        tk = patch.get("target")
        idxs = by_target.get(tk) if tk else None
        if idxs:
            for idx in idxs:
                row = targets[idx]
                if "payload" in patch:
                    existing = row.get("payload")
                    row["payload"] = {**(existing if isinstance(existing, dict) else {}), **(patch["payload"] or {})}
                if "declared" in patch:
                    row["declared"] = patch["declared"]
        else:
            targets.append(copy.deepcopy(patch))
    return targets, warnings


def apply_overrides(base: dict[str, Any], overrides: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """base(원본 불변) + overrides → 새 AnalysisInput 원시 페이로드. 반환 warnings=무매칭/미상 등
    적용 중 무음 스킵 없이 표면화할 사유(엔진 호출은 계속 진행 — 시나리오 자체를 죽이지 않음)."""
    merged = copy.deepcopy(base)
    warnings: list[str] = []

    rel_states = overrides.get("relaxation_states")
    if isinstance(rel_states, dict) and rel_states:
        rules = merged.get("rules")
        merged["rules"], w = _apply_relaxation_states(rules if isinstance(rules, list) else [], rel_states)
        warnings.extend(w)

    rule_patches = overrides.get("rules")
    if isinstance(rule_patches, list) and rule_patches:
        merged["rules"], rw = _apply_rule_patches(
            merged.get("rules") if isinstance(merged.get("rules"), list) else [], rule_patches)
        warnings.extend(rw)

    use_zone = overrides.get("use_zone")
    if isinstance(use_zone, str) and use_zone:
        rules = merged.get("rules")
        merged["rules"], zw = _apply_use_zone(rules if isinstance(rules, list) else [], use_zone)
        if zw:
            warnings.append(zw)

    ct_patches = overrides.get("calc_targets")
    if isinstance(ct_patches, list) and ct_patches:
        targets = merged.get("calc_targets")
        merged["calc_targets"], cw = _apply_calc_target_patches(
            targets if isinstance(targets, list) else [], ct_patches)
        warnings.extend(cw)

    return merged, warnings


# ── 엔진 결과 → 매트릭스 응답 정규화(순수함수) ─────────────────────────────────


def unavailable_result(scenario_id: str, label: str, *, reason: str,
                       run_id: str | None = None, warnings: list[str] | None = None) -> dict[str, Any]:
    """엔진 미도달/무결성실패/입력오류 등 — 정직 강등(무음0). 200으로 감싸는 것은 라우터 책임."""
    return {
        "scenario_id": scenario_id, "label": label, "degraded": True, "reason": reason,
        "run_id": run_id, "verdict": "unavailable", "key_criteria": [], "capacity": None,
        "issues_count": None, "needs_input": True, "complianceScore": None,
        "warnings": warnings or [],
    }


def normalize_result(scenario_id: str, label: str, compat: dict[str, Any], result: dict[str, Any], *,
                     run_id: str, reused: bool, warnings: list[str] | None = None) -> dict[str, Any]:
    """엔진 성공 결과 → 매트릭스 항목. compat=기존 `_compat_fields(result)` 산출(라우터가 재사용해 전달) —
    findings/finalStatus/complianceScore 재가공 로직을 여기서 복제하지 않는다.
    key_criteria: findings(rule_id·measured_value·limit_value·verdict)를 그대로 투영(가공 최소화).
    capacity: result.land_card.remaining_capacity(있으면) — 지어내지 않고 엔진이 계산한 값만 노출."""
    findings = compat.get("findings") or []
    key_criteria = [
        {
            "name": f.get("rule_id"),
            "measured": f.get("measured_value"),
            "limit": f.get("limit_value"),
            # COMPLIANT=True, NON_COMPLIANT=False, CONDITIONAL(완화 전제 조건부)=None(단정 금지)
            "pass": True if f.get("verdict") == "COMPLIANT" else (False if f.get("verdict") == "NON_COMPLIANT" else None),
        }
        for f in findings if isinstance(f, dict)
    ]
    issues_count = sum(1 for c in key_criteria if c["pass"] is not True)
    land_card = result.get("land_card") if isinstance(result, dict) else None
    capacity = land_card.get("remaining_capacity") if isinstance(land_card, dict) else None
    final_status = compat.get("finalStatus")
    needs_input = final_status == "NEEDS_REVIEW" or any(c["pass"] is None for c in key_criteria)
    return {
        "scenario_id": scenario_id, "label": label, "degraded": False, "reason": None,
        "run_id": run_id, "reused": reused, "verdict": final_status,
        "key_criteria": key_criteria, "capacity": capacity, "issues_count": issues_count,
        "needs_input": needs_input, "complianceScore": compat.get("complianceScore"),
        "warnings": warnings or [],
    }


def build_comparison(results: list[dict[str, Any]]) -> dict[str, Any]:
    """시나리오 비교 요약 — 가용(비degraded) 중 complianceScore 최고(동률은 issues_count 최소)를 best로,
    나머지는 best 대비 delta. 전원 degraded면 best_scenario_id=None(거짓 비교 금지)."""
    available = [r for r in results if not r.get("degraded")]
    if not available:
        return {"best_scenario_id": None, "deltas": {}}

    def _rank(r: dict[str, Any]) -> tuple[float, int]:
        cs = r.get("complianceScore")
        return (cs if cs is not None else -1.0, -(r.get("issues_count") or 0))

    best = max(available, key=_rank)
    deltas: dict[str, Any] = {}
    for r in results:
        if r["scenario_id"] == best["scenario_id"]:
            continue
        cs_delta = None
        if r.get("complianceScore") is not None and best.get("complianceScore") is not None:
            cs_delta = round(r["complianceScore"] - best["complianceScore"], 2)
        issues_delta = None
        if r.get("issues_count") is not None and best.get("issues_count") is not None:
            issues_delta = r["issues_count"] - best["issues_count"]
        deltas[r["scenario_id"]] = {"complianceScore_delta": cs_delta, "issues_count_delta": issues_delta}
    return {"best_scenario_id": best["scenario_id"], "deltas": deltas}
