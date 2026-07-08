"""다필지 합필(land assembly) 시니어 정량 평가기 — S5(다필지 통합분석 최종화).

입력(context['inputs'] — S3-B usable_area 3계층 + S3-A straddle + S4 검증 산출):
- gross_sqm / usable_confirmed_sqm / usable_conditional_sqm / excluded_sqm : usable 3계층(㎡)
- blocked_sqm : BLOCKED 게이트 필지 면적 합(㎡). 결측 시 excluded_sqm로 보수 대체.
- unverified_parcel_count : 면적 3원 교차검증(공부·좌표·입력) 미수렴 필지 수
- zone_straddle : 용도지역 걸침(혼재) 여부(bool)
- straddle_applied_rule : "가중평균+과반"(국계법 §84 소규모 걸침) | "부분별각각"(초과형)

★임계값의 성격(정직·무날조): 아래 WARN/BLOCK 임계(30%·50%)는 법정 기준이 아니라
'실무 보수 원칙'에 따른 **내부 리뷰 기준**이다 — 차단 필지 비중이 클수록 합필 사업의
실현 가능성·경제성이 급감한다는 통상적 실무 판단을 보수적으로 수치화한 것. 각 평가의
basis에 이 성격을 명시하며, 법령을 근거로 하는 항목(§84 혼재)만 조문을 인용한다.
결측 입력은 평가 생략(가짜 수치 금지 — 무목업). 순수함수·무DB·결정론.
"""

from __future__ import annotations

from typing import Any

from app.services.senior_agents.evaluators.base import (
    BLOCK,
    PASS,
    WARN,
    RuleEvaluation,
    num,
)

# ── 내부 리뷰 임계(실무 보수 원칙 — 법정 기준 아님) ──
# 차단면적 비중: 전체 대비 BLOCKED 면적이 30% 초과면 사업구조 재검토(WARN),
# 50% 초과면 과반 상실로 합필 전제 자체가 성립 곤란(BLOCK). 내부 리뷰 기준.
BLOCKED_SHARE_WARN_PCT = 30.0
BLOCKED_SHARE_BLOCK_PCT = 50.0
# 조건부 의존도: 사용가능 면적 중 조건부(PRECONDITION·CONDITIONAL·측량필요) 비중이
# 과반(50% 초과)이면 확정 면적만으로 사업이 성립하지 않음 → WARN. 내부 리뷰 기준.
CONDITIONAL_DEPENDENCY_WARN_PCT = 50.0

_INTERNAL_BASIS = "내부 리뷰 기준(실무 보수 원칙) — 법정 기준 아님"


def _eval_blocked_share(inputs: dict[str, Any]) -> RuleEvaluation | None:
    """규칙① 차단면적 비중 — >30% WARN·>50% BLOCK(내부 기준). 결측 생략."""
    gross = num(inputs, "gross_sqm")
    if gross is None or gross <= 0:
        return None
    blocked = num(inputs, "blocked_sqm")
    source = "blocked_sqm(BLOCKED 게이트 필지)"
    if blocked is None:
        # 보수 대체: excluded_sqm(BLOCKED+도로·구거 등 건축불가 지목 포함) — 과대평가 방향(안전측)
        blocked = num(inputs, "excluded_sqm")
        source = "excluded_sqm(BLOCKED+건축불가 지목 — 보수 대체)"
    if blocked is None or blocked < 0:
        return None
    share_pct = blocked / gross * 100.0
    if share_pct > BLOCKED_SHARE_BLOCK_PCT:
        verdict, note = BLOCK, " — 과반 상실: 합필 전제 성립 곤란(제외 시나리오 재검토)"
    elif share_pct > BLOCKED_SHARE_WARN_PCT:
        verdict, note = WARN, " — 차단 비중 과다: 차단 필지 제외안 병행 검토"
    else:
        verdict, note = PASS, ""
    return RuleEvaluation(
        rule_id="assembly.blocked_share", label="차단면적 비중",
        value=round(share_pct, 1), unit="%", verdict=verdict,
        threshold=f"≤{BLOCKED_SHARE_WARN_PCT:.0f}% 양호·>{BLOCKED_SHARE_WARN_PCT:.0f}% WARN"
                  f"·>{BLOCKED_SHARE_BLOCK_PCT:.0f}% BLOCK(내부 기준)",
        basis=_INTERNAL_BASIS + " — 차단 필지 비중 증가 시 합필 실현성·경제성 급감(실무 통념의 보수적 수치화)",
        detail=f"차단 {blocked:,.1f}㎡ / 전체 {gross:,.1f}㎡ = {share_pct:.1f}% (출처: {source}){note}")


def _eval_area_verification(inputs: dict[str, Any]) -> RuleEvaluation | None:
    """규칙② 면적 검증 미수렴 필지 — 존재 시 WARN(확정 전 지적측량 확인). 결측 생략."""
    n = num(inputs, "unverified_parcel_count")
    if n is None or n < 0:
        return None
    count = int(n)
    verdict = WARN if count > 0 else PASS
    note = (f"미수렴 {count}필지 — 면적 확정 전 지적측량 확인 필요(자동 보정 금지·무날조)"
            if count > 0 else "전 필지 면적 3원 신호 수렴")
    return RuleEvaluation(
        rule_id="assembly.area_verification", label="면적 검증 수렴",
        value=float(count), unit="필지", verdict=verdict,
        threshold="미수렴 0필지(1필지 이상 → WARN)",
        basis="면적 3원 교차검증(공부·좌표·입력) 내부 검증 정책 — 법정 기준 아님. "
              "미수렴 면적의 확정은 지적측량(공간정보관리법상 측량) 결과로만 가능",
        detail=note)


def _eval_conditional_dependency(inputs: dict[str, Any]) -> RuleEvaluation | None:
    """규칙③ 조건부 의존도 — 사용가능 중 조건부 비중 >50% WARN(내부 기준). 분모 0 생략."""
    confirmed = num(inputs, "usable_confirmed_sqm")
    conditional = num(inputs, "usable_conditional_sqm")
    if confirmed is None or conditional is None or confirmed < 0 or conditional < 0:
        return None
    total_usable = confirmed + conditional
    if total_usable <= 0:
        return None
    dep_pct = conditional / total_usable * 100.0
    verdict = WARN if dep_pct > CONDITIONAL_DEPENDENCY_WARN_PCT else PASS
    note = (" — 확정면적만으로 사업 성립 곤란: 조건(인허가 전제·측량 등) 해소 계획 선행 필요"
            if verdict == WARN else "")
    return RuleEvaluation(
        rule_id="assembly.conditional_dependency", label="조건부 면적 의존도",
        value=round(dep_pct, 1), unit="%", verdict=verdict,
        threshold=f"≤{CONDITIONAL_DEPENDENCY_WARN_PCT:.0f}%(초과 → WARN, 내부 기준)",
        basis=_INTERNAL_BASIS + " — 조건부(전제조건·측량필요) 면적 과반 의존은 확정성 결여",
        detail=f"조건부 {conditional:,.1f}㎡ / 사용가능 {total_usable:,.1f}㎡ = {dep_pct:.1f}%{note}")


def _eval_zone_straddle(inputs: dict[str, Any]) -> RuleEvaluation | None:
    """규칙④ 용도지역 혼재 — 초과형(부분별각각) WARN·소규모 걸침 PASS. 결측 생략."""
    straddle = inputs.get("zone_straddle")
    if not isinstance(straddle, bool):
        return None  # 여부 미상 → 평가 생략(무날조)
    if not straddle:
        return RuleEvaluation(
            rule_id="assembly.zone_straddle", label="용도지역 혼재", value=None, unit="",
            verdict=PASS, threshold="단일 용도지역(혼재 없음)",
            basis="국토계획법 제84조(둘 이상의 용도지역에 걸치는 대지) — 걸침 없음으로 미적용",
            detail="전 필지 단일 용도지역 — §84 걸침 규정 미적용")
    applied = str(inputs.get("straddle_applied_rule") or "").strip()
    if applied == "부분별각각":
        verdict = WARN
        note = ("걸침 부분이 §84 소규모 기준 초과 → 부분별 각각 적용(사실상 분리 검토) — "
                "통합 지표(가중평균 용적률 등) 단독 의존 금지, 부분별 개별 성립성 확인 필요")
    elif applied:
        verdict = PASS
        note = f"소규모 걸침 — §84에 따라 '{applied}' 적용(건폐·용적 가중평균, 그 밖 규정은 과반 부분)"
    else:
        # 걸침인데 적용규정 미산정 → 유리한 가정 금지(무날조) — 보수적으로 WARN
        verdict = WARN
        note = "혼재 확인되었으나 §84 적용규정 미산정 — 초과형 가능성을 배제할 수 없어 보수적 경고"
    return RuleEvaluation(
        rule_id="assembly.zone_straddle", label="용도지역 혼재", value=None, unit="",
        verdict=verdict,
        threshold="§84 소규모 걸침(가중평균+과반) 허용·초과형(부분별각각)/미상 → WARN",
        basis="국토계획법 제84조(둘 이상의 용도지역·지구·구역에 걸치는 대지에 대한 적용 기준). "
              "WARN 강도 자체는 내부 리뷰 기준(실무 보수 원칙)",
        detail=note)


def evaluate_land_assembly(inputs: dict) -> list[RuleEvaluation]:
    """다필지 합필 종합 리뷰 — 차단 비중·검증 수렴·조건부 의존·혼재(결측 생략·무목업)."""
    out: list[RuleEvaluation] = []
    for ev in (
        _eval_blocked_share(inputs),
        _eval_area_verification(inputs),
        _eval_conditional_dependency(inputs),
        _eval_zone_straddle(inputs),
    ):
        if ev is not None:
            out.append(ev)
    return out
