"""provenance 불변식(계층B 배지) — 이미 계산된 result의 데이터 출처(provenance)를 판정해
미등록 출처(unknown-source)·신선도 만료(stale)를 **비차단 P2 배지**로 표면화한다(Phase0 W2-a).

성격(★오라클 독립성·범주):
- provenance는 데이터-메타(출처가 자기선언한 상태·신선도)라 분석 산출값과 **구조적으로 독립**이다
  — G4/G5류의 '값 재구현' 위험이 없다(우리는 값을 다시 계산하지 않고, 이미 부착된 출처 메타를
  규칙에 맞는가로만 판정한다: neuro proposes / symbolic disposes).
- ★"stale=버그"가 아니라 "stale=신선도 경고"이므로 **P2 배지로 한정**하고 correctness(P0/P1)
  finding으로 승격하지 않는다. 계층B(수시변동 안전망)·severity=P2 = 비차단 → AuditReport.is_valid를
  절대 뒤집지 않는다(is_valid = not has_p0). 이게 계층B 배지의 핵심 계약이다.

경로 비의존(실제 shape 재확증 — 2026-07-29):
  실 analyze() 경로(comprehensive_analysis_service.py:890 `result.setdefault("provenance",
  _ev_block.get("provenance", []))`)는 evidence_contract.build_provenance가 낸 **list[dict]**를
  붙인다. 각 엔트리는 두 형태다(evidence_contract.py:83-98):
    - 미등록 출처: {"name", "source_type": "unknown", "registered": False}          (line 88)
    - 등록 출처:   DataSourceStatus.to_dict()                                        (line 90)
                   = {name, source_type, update_frequency, last_updated(isoformat|None),
                      last_error, record_count, is_healthy}  ※ 'registered' 키 없음
                   + "freshness"{is_fresh, age_days, max_age_days, data_type, warning}
                     — 단, status.last_updated is not None일 때만 부착(line 92).
  ★또 다른 dict 형태(ordinance parse-provenance: {source, confidence, recheck_recommended,
  disclaimer, reused} — ordinance_service.py:216)가 다른 경로에 공존한다. 이건 출처-상태 목록이
  아니므로 이 규칙들은 무발동해야 한다(아래 판정이 registered/freshness 특정 필드만 보므로
  구조적으로 0건 — 오탐 방지).

판정(둘 다 pure O(n)·부작용 없음):
  - PROV_UNKNOWN_SOURCE: registered is False 엔트리마다 P2 배지(권위 소스 목록 미등재 — 값 신뢰도 확인).
  - PROV_STALE_DATA:    freshness가 **존재**하면서 is_fresh is False 엔트리마다 P2 배지. ★freshness가
                        없으면(=last_updated None/부재로 신선도 신호 자체가 없음) 무발동
                        — "stale 판정 가능한 것만" 판정(억지 stale 단정 금지).
"""

from __future__ import annotations

from typing import Any

from app.services.verification.field_audit.contracts import AuditFinding
from app.services.verification.field_audit.rules_registry import register_audit_rule

# 안정 식별자 — rule_id=rules_registry 등록·per-rule 롤백 키, code=finding 안정 식별자.
_UNKNOWN_RULE_ID = "PROV_UNKNOWN_SOURCE"
_UNKNOWN_FINDING_CODE = "PROV_UNKNOWN_SOURCE"
_STALE_RULE_ID = "PROV_STALE_DATA"
_STALE_FINDING_CODE = "PROV_STALE_DATA"

# finding expected 마커(값이 아니라 '기대 상태'를 기술 — 값 correctness가 아니라 출처-메타 판정).
# 테스트가 참조하도록 상수로 노출.
_UNKNOWN_EXPECTED = "등록 출처(권위 데이터 소스 목록)"
_STALE_EXPECTED = "신선(freshness 기준 이내)"

# 배지 패널명(EvidencePanel 소비 라벨) — 출처-메타 표면.
_PANEL = "출처"


def _extract_provenance_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """result["provenance"]에서 출처-상태 엔트리(dict) 목록을 안전 추출(경로 비의존).

    실 shape는 **list[dict]**(build_provenance). dict 형태(ordinance parse-provenance)는
    출처-상태 목록이 아니므로 values()의 dict만 추린다(그 flat 메타는 dict 값이 없어 [] 반환
    — 오탐 방지). 부재/빈값/비dict payload면 [](오탐 0).
    """
    if not isinstance(payload, dict):
        return []
    v = payload.get("provenance")
    if isinstance(v, list):
        return [e for e in v if isinstance(e, dict)]
    if isinstance(v, dict):
        # dict-of-status 형태 방어(실 코드엔 없음). ordinance flat 메타는 dict 값이 없어 [].
        return [e for e in v.values() if isinstance(e, dict)]
    return []


def _prov_unknown_source(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """PROV_UNKNOWN_SOURCE(계층B): 미등록 출처(registered is False) 엔트리마다 P2 배지.

    등록 출처는 to_dict()에 'registered' 키가 없어 entry.get("registered") is None → 무발동
    (구조적으로 등록/미등록만 갈라냄). P2 비차단 — is_valid 불변.
    """
    out: list[AuditFinding] = []
    for entry in _extract_provenance_entries(payload):
        if entry.get("registered") is not False:
            continue  # 등록(키 부재/None/True) → 배지 아님
        name = entry.get("name")
        out.append(
            AuditFinding(
                code=_UNKNOWN_FINDING_CODE,
                severity="P2",
                panel=_PANEL,
                field=str(name) if name else "provenance",
                expected=_UNKNOWN_EXPECTED,
                observed="미등록",
                rule_id=_UNKNOWN_RULE_ID,
                tier="B",
                note="출처 미등록(권위소스 목록에 없음)—값 신뢰도 확인 필요",
            )
        )
    return out


def _prov_stale_data(
    payload: dict[str, Any], ctx: dict[str, Any]
) -> list[AuditFinding]:
    """PROV_STALE_DATA(계층B): freshness가 존재하면서 is_fresh is False 엔트리마다 P2 배지.

    ★freshness 부재(=last_updated None/부재)면 무발동 — 신선도 신호 자체가 없어 stale 판정 불가.
    stale=신선도 경고이지 버그가 아니므로 P2 배지에 한정(correctness 승격 금지). P2 비차단 — is_valid 불변.
    """
    out: list[AuditFinding] = []
    for entry in _extract_provenance_entries(payload):
        fresh = entry.get("freshness")
        if not isinstance(fresh, dict):
            continue  # 신선도 미부착(last_updated None/부재) → stale 판정 불가 → 무발동
        if fresh.get("is_fresh") is not False:
            continue  # 신선(True) 또는 판정불명(None) → 배지 아님
        name = entry.get("name")
        age = fresh.get("age_days")
        max_age = fresh.get("max_age_days")
        observed = (
            f"만료(age_days={age}>max={max_age})"
            if isinstance(age, (int, float))
            else "만료(is_fresh=false)"
        )
        out.append(
            AuditFinding(
                code=_STALE_FINDING_CODE,
                severity="P2",
                panel=_PANEL,
                field=str(name) if name else "provenance",
                expected=_STALE_EXPECTED,
                observed=observed,
                rule_id=_STALE_RULE_ID,
                tier="B",
                note=(
                    "원천 데이터 신선도 만료(freshness.is_fresh=false)—값이 오래됨(신선도 경고이지 "
                    "오류 아님·P2 배지). 재수집 권장(mark_updated 상류 배선은 별도 티켓)."
                ),
            )
        )
    return out


def register_rules() -> None:
    """provenance 불변식을 rules_registry에 등록(멱등 — _SEEN_IDS가 중복 무시).

    프로덕션은 모듈 임포트 시 하단에서 자동 호출한다. clear_registry()로 레지스트리를 비우는
    격리 테스트는 이 함수를 다시 호출해 프로덕션 규칙을 재등록한다.
    """
    register_audit_rule(rule_id=_UNKNOWN_RULE_ID, tier="B")(_prov_unknown_source)
    register_audit_rule(rule_id=_STALE_RULE_ID, tier="B")(_prov_stale_data)


# 프로덕션 임포트 시 자동 등록(field_audit 패키지 __init__가 이 모듈을 임포트한다).
register_rules()
