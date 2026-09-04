"""Fact 상태 어휘 계약 (Zero-Trust P1 — SPEC v4 §[Zero-Trust Data 원칙]·§P1) — 계약만.

이 파일이 정의하는 것:
- 모든 Fact(추출·산출된 값 하나하나)가 가질 수 있는 7가지 신뢰상태와 그 전이 규칙.
- ★이번 1차는 "어휘 계약"만 신설한다. 실제 어떤 서비스가 값에 이 상태를 붙이고 읽는 배선은
  아직 없다(소비 배선·필드수준 계보 ReportClaim→...→SourceSnapshot 연결은 W2-2 범위).

7상태 정의(SPEC v4 P1 "Fact의 OBSERVED/DERIVED/ASSUMED/INFERRED/CONFLICT/UNKNOWN/STALE을
구현한다" 요구를 그대로 어휘화):
- OBSERVED : 외부 소스에서 직접 관측된 원값. SourceSnapshot 1건에 1:1 대응하는 것이 이상적.
- DERIVED  : OBSERVED 값(들)로부터 결정론적 규칙/계산식으로 산출된 값.
- ASSUMED  : 관측 불가 시 명시적으로 승인된 가정값(승인자·만료가 있어야 함 — assumptions.json 계약).
- INFERRED : 통계·모델 추정값. 불확실성이 명시되어야 하며 자동으로 확정 승격되지 않는다.
- CONFLICT : 독립 출처 간 값이 불일치하고 아직 해소되지 않음(critical이면 자동승인 0 — Gate 차단).
- UNKNOWN  : 근거가 전혀 없음. 0이나 임의 기본값으로 절대 대체하지 않는다(무날조 원칙).
- STALE    : 과거엔 유효했으나 신선도(freshness) 기준을 넘겨 재검증이 필요함.

★불변식(SPEC v4 [Zero-Trust Data 원칙] 6번): "UNKNOWN, CONFLICT, ASSUMED, STALE을 0 또는
  정상값으로 바꾸지 않는다." — 이 상태들을 조용히 OBSERVED로 승격시키는 코드경로는 계약 위반이다.
  반드시 명시적 재수집/승인/해소 절차를 거쳐야 한다(전이표 참고).
"""
from __future__ import annotations

from enum import StrEnum


class FactStatus(StrEnum):
    """Fact 신뢰상태 7종."""

    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    ASSUMED = "ASSUMED"
    INFERRED = "INFERRED"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


VALID_FACT_STATUSES: frozenset[str] = frozenset(s.value for s in FactStatus)

# 전이 규칙(주석 계약 — 실제 강제는 소비 배선이 생기는 W2-2에서). 키=현재 상태,
# 값=그 상태에서 허용되는 "다음" 상태 집합. 여기 없는 전이는 can_transition_fact()가 거부한다.
#
#   UNKNOWN  → OBSERVED/ASSUMED/INFERRED : 근거 없음 → 실측/가정/추론 중 하나로 최초 확정.
#   ASSUMED  → OBSERVED/STALE            : 가정을 실측이 대체(승격) 하거나, 가정 자체가 만료(STALE).
#   INFERRED → OBSERVED/CONFLICT/STALE   : 추론값이 실측으로 확정되거나, 실측과 충돌하거나, 낡음.
#   OBSERVED → STALE/CONFLICT            : 실측값도 신선도 초과·타 출처와 불일치로 재검토 대상이 됨.
#   DERIVED  → STALE/CONFLICT            : OBSERVED와 동일한 사유로 재계산 대상이 됨.
#   CONFLICT → OBSERVED/DERIVED          : 불일치 해소 후에만 재확정(자동 아님 — 승인 필요).
#   STALE    → OBSERVED/DERIVED          : 재수집/재계산으로 갱신.
_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    FactStatus.UNKNOWN: frozenset({FactStatus.OBSERVED, FactStatus.ASSUMED, FactStatus.INFERRED}),
    FactStatus.ASSUMED: frozenset({FactStatus.OBSERVED, FactStatus.STALE}),
    FactStatus.INFERRED: frozenset({FactStatus.OBSERVED, FactStatus.CONFLICT, FactStatus.STALE}),
    FactStatus.OBSERVED: frozenset({FactStatus.STALE, FactStatus.CONFLICT}),
    FactStatus.DERIVED: frozenset({FactStatus.STALE, FactStatus.CONFLICT}),
    FactStatus.CONFLICT: frozenset({FactStatus.OBSERVED, FactStatus.DERIVED}),
    FactStatus.STALE: frozenset({FactStatus.OBSERVED, FactStatus.DERIVED}),
}


def normalize_fact_status(value: object) -> str | None:
    """Fact 상태 후보를 정규화한다. None/빈문자열 → None(=아직 미부여)."""
    if value is None:
        return None
    s = str(value).strip().upper()
    return s or None


def is_valid_fact_status(value: object) -> bool:
    """7종 중 하나인지(정규화 후) 확인한다."""
    return normalize_fact_status(value) in VALID_FACT_STATUSES


def can_transition_fact(current: object, target: object) -> tuple[bool, str]:
    """current → target 전이가 규칙상 허용되는지 판정한다(순수 함수 — DB 불요).

    - target은 반드시 유효한 7종 중 하나여야 한다.
    - current가 None(아직 상태 없음)이면 임의 유효 상태로 최초 확정을 허용한다.
    - current == target(동일 상태 재확인)은 항상 허용한다(무변화).
    """
    tgt = normalize_fact_status(target)
    if not is_valid_fact_status(tgt):
        return False, f"유효하지 않은 목표 Fact 상태: {target}"
    cur = normalize_fact_status(current)
    if cur is None:
        return True, "ok"
    if not is_valid_fact_status(cur):
        return False, f"유효하지 않은 현재 Fact 상태: {current}"
    if cur == tgt:
        return True, "ok"
    allowed = _ALLOWED_TRANSITIONS.get(cur, frozenset())
    if tgt not in allowed:
        return False, f"허용되지 않은 Fact 상태 전이: {cur} → {tgt}"
    return True, "ok"
