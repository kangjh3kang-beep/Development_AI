"""cross_field 불변식 — 서로 다른 필드 간 도메인 관계를 pure fn으로 판정한다.

W1-1 [P0 G1]: "규제목록에 보호구역이 있으면 종합 개발리스크는 그 보호구역의 SSOT severity
하한 이상이어야 한다." 미달이면 P0 AuditFinding을 낸다(예: 통제보호구역+방공기지인데
리스크 '낮음' → 하한 '높음' 미달 → finding). 값을 생산하지 않고 이미 계산된 result를
protection_zone_severity 권위표(독립 오라클)와 대조만 한다(neuro proposes / symbolic disposes).

W1-2 [P1 G2]: "입지 school_count는 dedup_school_cluster로 병합한 고유 모학교 수와 같아야
한다." 불일치(부속시설·분교 개별집계로 과카운트)면 P1 AuditFinding을 낸다(예: 대보초 1곳을
운동장·병설유치원·분교로 5개교 집계 → 고유 모학교 1 ≠ school_count 5 → finding). G1과 동형으로
값을 생산하지 않고 이미 계산된 result의 학교목록/카운트를 dedup SSOT와 대조만 한다.

★거버넌스(계획 §2.4): G1(P0)은 차단후보로 finding을 표면화, G2(P1)는 **제자리 교정+배지**
(비차단 — dedup가 올바른 값을 산출하므로 is_valid를 뒤집지 않는다). 소비처 하드차단은 골든
안정 후 단계다. runner의 F4a 관측전용 emit도 verdict/자동토글을 구동하지 않는다(성장루프 격리).

경로 비의존: 실 analyze() 결과(development_plans.*·education.*·infrastructure.*)와 골든
fixture(regulations/risk.*·poi.*) 두 shape 모두에서 규제·리스크·학교를 추출한다(runner가 다중
삽입점에 재사용되므로).
"""

from __future__ import annotations

from typing import Any

from app.services.external_api.poi_dedup import dedup_school_cluster
from app.services.regulation.protection_zone_severity import (
    meets_floor,
    risk_floor_for_regulations,
)
from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import register_audit_rule

# 안정 식별자 — rule_id는 rules_registry 등록·per-rule 롤백 키, code는 finding 안정 식별자.
_G1_RULE_ID = "G1_PROTECTION_ZONE_RISK"
_G1_FINDING_CODE = "G1_PROTECTION_ZONE_RISK_FLOOR"
_G2_RULE_ID = "G2_SCHOOL_POI_DEDUP"
_G2_FINDING_CODE = "G2_SCHOOL_POI_DEDUP"


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


# 학교 POI가 실릴 수 있는 컨테이너 이름(어느 부모 밑이든 이름은 같다).
_SCHOOL_CONTAINERS = ("poi", "education", "infrastructure")


def _school_containers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """학교 POI 컨테이너 후보를 얕은 곳부터 모은다(경로 비의존).

    ★2026-08-02 봉합(가드 갭): 종전에는 **최상위**의 poi/education/infrastructure만 봤다.
      그런데 실제 analyze() 응답은 학교를 `result["location"]["education"]`에 담는다 —
      즉 이 불변식은 **프로덕션 주경로에서 발동할 수 없었다**(평면 shape인 골든 픽스처에서만
      통과). 규칙은 초록인데 실제로는 아무것도 지키지 않았고, dedup가 회귀해도 못 잡는다.
      그래서 최상위와 `location` 밑을 모두 후보로 본다.
    """
    if not isinstance(payload, dict):
        return []
    parents: list[dict[str, Any]] = [payload]
    loc = payload.get("location")
    if isinstance(loc, dict):
        parents.append(loc)

    out: list[dict[str, Any]] = []
    for parent in parents:
        for name in _SCHOOL_CONTAINERS:
            c = parent.get(name)
            if isinstance(c, dict):
                out.append(c)
    return out


def _extract_schools(payload: dict[str, Any]) -> list[Any]:
    """result/payload에서 학교 POI 목록을 추출(경로 비의존)."""
    if not isinstance(payload, dict):
        return []
    # 실 analyze(): location.education.schools / site_score: education.schools / 골든: poi.schools.
    for c in _school_containers(payload):
        if isinstance(c.get("schools"), list):
            return c["schools"]
    # 평면 shape: payload["schools"].
    if isinstance(payload.get("schools"), list):
        return payload["schools"]
    return []


def _extract_school_count(payload: dict[str, Any]) -> int | None:
    """result/payload에서 산출된 학교 카운트를 추출(경로 비의존). 미산출이면 None."""
    if not isinstance(payload, dict):
        return None
    for c in _school_containers(payload):
        if isinstance(c.get("school_count"), int):
            return c["school_count"]
    v = payload.get("school_count")
    return v if isinstance(v, int) else None


def _g2_school_poi_dedup(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """G2 불변식: 산출 school_count == dedup 고유 모학교 수. 불일치(과카운트) 시 P1 finding.

    학교목록/카운트가 없으면 무발동. dedup(고유 모학교) 수와 산출 카운트가 일치하면 finding 0
    (근본수정 후 경로 — 소비처가 dedup_school_cluster를 소비해 고유 수를 쓰면 통과).
    P1 = 제자리 교정(dedup가 올바른값 산출)+배지(비차단 — is_valid 미변경).
    """
    schools = _extract_schools(payload)
    observed = _extract_school_count(payload)
    if observed is None:
        return []  # 카운트 미산출 → 무발동(정상 필지 배지 인플레 방지)
    expected = len(dedup_school_cluster(schools))
    if observed == expected:
        return []  # dedup된 고유 수와 일치 → 정상(근본수정 후 경로)
    return [
        AuditFinding(
            code=_G2_FINDING_CODE,
            severity="P1",
            panel="입지",
            field="school_count",
            expected=expected,
            observed=observed,
            rule_id=_G2_RULE_ID,
            tier="A",
            note=(
                f"학교 POI 과카운트 — 고유 모학교 {expected}개인데 school_count {observed}"
                f"(부속시설·분교 개별집계). dedup_school_cluster SSOT 대조 위반."
            ),
        )
    ]


def register_rules() -> None:
    """cross_field 불변식을 rules_registry에 등록(멱등 — _SEEN_IDS가 중복 무시).

    프로덕션은 모듈 임포트 시 하단에서 자동 호출한다. clear_registry()로 레지스트리를
    비우는 격리 테스트는 이 함수를 다시 호출해 프로덕션 규칙을 재등록한다.
    """
    register_audit_rule(rule_id=_G1_RULE_ID, tier="A")(_g1_protection_zone_risk_floor)
    register_audit_rule(rule_id=_G2_RULE_ID, tier="A")(_g2_school_poi_dedup)


# 프로덕션 임포트 시 자동 등록(field_audit 패키지 __init__가 이 모듈을 임포트한다).
register_rules()
