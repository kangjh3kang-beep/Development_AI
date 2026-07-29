"""cross_field 불변식 — 서로 다른 필드 간 도메인 관계를 pure fn으로 판정한다.

W1-1 [P0 G1]: "규제목록에 보호구역이 있으면 종합 개발리스크는 그 보호구역의 SSOT severity
하한 이상이어야 한다." 미달이면 P0 AuditFinding을 낸다(예: 통제보호구역+방공기지인데
리스크 '낮음' → 하한 '높음' 미달 → finding). 값을 생산하지 않고 이미 계산된 result를
protection_zone_severity 권위표(독립 오라클)와 대조만 한다(neuro proposes / symbolic disposes).

★거버넌스(계획 §2.4 1단계 — 비차단): 이 규칙은 finding(P0)을 **표면화**만 한다. 소비처
하드차단(risk를 강제로 올리거나 return을 막는 것)은 골든 안정 후 2단계다. runner의 F4a
관측전용 emit도 verdict/자동토글을 구동하지 않는다(성장루프 격리 유지).

경로 비의존: 실 analyze() 결과(development_plans.*)와 골든 fixture(regulations/risk.*) 두 shape
모두에서 규제·리스크를 추출한다(runner가 다중 삽입점에 재사용되므로).
"""

from __future__ import annotations

from typing import Any

from app.services.regulation.protection_zone_severity import (
    meets_floor,
    risk_floor_for_regulations,
)
from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import register_audit_rule

# 안정 식별자 — rule_id는 rules_registry 등록·per-rule 롤백 키, code는 finding 안정 식별자.
_G1_RULE_ID = "G1_PROTECTION_ZONE_RISK"
_G1_FINDING_CODE = "G1_PROTECTION_ZONE_RISK_FLOOR"


def _extract_regulations(payload: dict[str, Any]) -> list[str]:
    """result/payload에서 규제 designation 목록을 추출(경로 비의존)."""
    if not isinstance(payload, dict):
        return []
    # 실 analyze() 결과: result["development_plans"]["land_use_regulations"].
    dp = payload.get("development_plans")
    if isinstance(dp, dict):
        regs = dp.get("land_use_regulations")
        if isinstance(regs, list) and regs:
            return [str(r) for r in regs if r]
    # 골든 fixture/평면 shape: payload["regulations"].
    regs = payload.get("regulations")
    if isinstance(regs, list):
        return [str(r) for r in regs if r]
    return []


def _extract_risk_level(payload: dict[str, Any]) -> str | None:
    """result/payload에서 종합 리스크 등급을 추출(경로 비의존). 미산출이면 None."""
    if not isinstance(payload, dict):
        return None
    # 실 analyze() 결과: result["development_plans"]["risk_level"].
    dp = payload.get("development_plans")
    if isinstance(dp, dict) and dp.get("risk_level"):
        return dp.get("risk_level")
    # 골든 fixture shape: payload["risk"]["risk_level"].
    risk = payload.get("risk")
    if isinstance(risk, dict) and risk.get("risk_level"):
        return risk.get("risk_level")
    # 평면 shape: payload["risk_level"].
    return payload.get("risk_level")


def _g1_protection_zone_risk_floor(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """G1 불변식: 보호구역 존재 → 종합리스크 ≥ SSOT 하한. 미달 시 P0 finding.

    보호구역이 없으면(floor None) 무발동 — 정상 필지에 배지 인플레를 만들지 않는다.
    산출 리스크가 하한을 충족하면 finding 0(제한보호=중간을 중간으로 산출하면 통과 — 과잉교정 X).
    """
    regs = _extract_regulations(payload)
    if not regs:
        return []
    floor, driver = risk_floor_for_regulations(regs)
    if floor is None:
        return []  # 규제목록에 보호구역 없음 → 무발동
    observed = _extract_risk_level(payload)
    if meets_floor(observed, floor):
        return []  # 하한 충족 → 정상(근본수정 후 경로)
    return [
        AuditFinding(
            code=_G1_FINDING_CODE,
            severity="P0",
            panel="risk",
            field="risk_level",
            expected=floor,
            observed=observed,
            rule_id=_G1_RULE_ID,
            tier="A",
            note=(
                f"보호구역 '{driver}' 존재 → 종합 개발리스크 하한 '{floor}' 미달"
                f"(산출 '{observed}'). protection_zone_severity SSOT 대조 위반."
            ),
        )
    ]


def register_rules() -> None:
    """cross_field 불변식을 rules_registry에 등록(멱등 — _SEEN_IDS가 중복 무시).

    프로덕션은 모듈 임포트 시 하단에서 자동 호출한다. clear_registry()로 레지스트리를
    비우는 격리 테스트는 이 함수를 다시 호출해 프로덕션 규칙을 재등록한다.
    """
    register_audit_rule(rule_id=_G1_RULE_ID, tier="A")(_g1_protection_zone_risk_floor)


# 프로덕션 임포트 시 자동 등록(field_audit 패키지 __init__가 이 모듈을 임포트한다).
register_rules()
