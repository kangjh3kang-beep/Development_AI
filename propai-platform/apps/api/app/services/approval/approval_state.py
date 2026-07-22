"""공용 승인 상태머신 계약 — v4.0 명세 P13(W1-A · 3원형 단일 계약화).

이 파일이 푸는 문제(쉬운 설명):
- site_basis(artifact_status: DRAFT/ANALYZED/REVIEW_REQUIRED/APPROVED/STALE)·
  design_runs(DRAFT/APPROVED)·run_state(RunStateEnum: DRAFT~LOCKED) 세 원형이 각자
  "초안→검증→승인" 흐름을 따로 구현해 왔다. 이 모듈은 그 공통 골격을 v4.0 스펙 문언
  (Draft/MachineValidated/ExpertReviewed/Approved/Superseded) 그대로 딱 하나의 계약으로
  뽑아낸다. 3원형 코드는 이 파일을 몰라도 되고(그린필드 금지), 이 파일도 3원형을 재구현하지
  않는다 — 원형↔공용 변환은 archetype_adapters.py가 별도로 담당한다.

★"승인 없이 APPROVED 도달 경로 0"(v4.0 Gate) — 이 모듈의 구조 자체가 보장한다:
  apply_transition()이 유일한 전이 관문이고, to==APPROVED일 때 actor(승인자)가 비어있으면
  무조건 예외를 던진다(다른 우회 함수가 없다 — site_basis의 can_approve() 선례와 동일 철학).

★전이표는 "합법 전이만" 명시한다(그 외 전부 거부) — 역행(예: APPROVED→DRAFT)은 이 표에
  없다: 사양은 "재발급은 SUPERSEDED 경유"(새 초안을 새로 시작하는 원칙)이지, 기존 레코드를
  과거 상태로 되돌리는 것이 아니기 때문이다. SUPERSEDED는 종단(더 이상 전이 없음).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum  # 프로젝트 requires-python>=3.12 — 표준 StrEnum 직수입(rbac.py 선례)


class ApprovalState(StrEnum):
    """v4.0 명세 P13 승인 상태머신(공용 어휘) — 5상태."""

    DRAFT = "DRAFT"                        # 초안(미검증)
    MACHINE_VALIDATED = "MACHINE_VALIDATED"  # 자동(기계) 검증 통과
    EXPERT_REVIEWED = "EXPERT_REVIEWED"    # 전문가 검토(대기 또는 완료 — 원형별 의미는 어댑터 docstring 참조)
    APPROVED = "APPROVED"                  # 인간승인 완료(actor 필수)
    SUPERSEDED = "SUPERSEDED"              # 갱신·폐기됨(재발급은 새 DRAFT로)


class IllegalApprovalTransitionError(Exception):
    """허용되지 않은 ApprovalState 전이 시도(전이표에 없는 조합·actor 없는 APPROVED 진입)."""


# ── 전이표 — 합법 전이만 명시(그 외 전부 거부) ──────────────────────────────
# DRAFT→MACHINE_VALIDATED→EXPERT_REVIEWED→APPROVED→SUPERSEDED 의 선형 사슬 하나뿐이다.
# 역행·건너뛰기(예: DRAFT→APPROVED 직행)는 site_basis의 "ANALYZED 상태에서만 승인 가능"
# 선례와 동형으로 구조상 차단한다. SUPERSEDED는 종단(빈 집합 — 이 표 안에서는 더 못 감).
_LEGAL_TRANSITIONS: dict[ApprovalState, frozenset[ApprovalState]] = {
    ApprovalState.DRAFT: frozenset({ApprovalState.MACHINE_VALIDATED}),
    ApprovalState.MACHINE_VALIDATED: frozenset({ApprovalState.EXPERT_REVIEWED}),
    ApprovalState.EXPERT_REVIEWED: frozenset({ApprovalState.APPROVED}),
    ApprovalState.APPROVED: frozenset({ApprovalState.SUPERSEDED}),
    ApprovalState.SUPERSEDED: frozenset(),
}


def can_transition(from_state: ApprovalState, to_state: ApprovalState) -> bool:
    """(from, to) 조합이 전이표상 합법인지만 판단(actor 요건은 별도 — apply_transition에서 검사)."""
    from_state = ApprovalState(from_state)
    to_state = ApprovalState(to_state)
    return to_state in _LEGAL_TRANSITIONS.get(from_state, frozenset())


@dataclass(frozen=True)
class TransitionEvent:
    """전이 이력 1건 — 누가(actor)·언제(occurred_at)·무엇→무엇(from_state→to_state).

    site_basis_transition_event(append-only 이벤트 테이블) 선례와 같은 정보 골격을 순수
    dataclass로 반환한다(이번 W1-A는 DB 마이그레이션 스코프 밖 — 영속은 호출측이 기존
    구조를 활용해 추가로 남긴다).
    """

    from_state: ApprovalState
    to_state: ApprovalState
    actor: str | None
    occurred_at: str


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def apply_transition(
    current: ApprovalState,
    to: ApprovalState,
    *,
    actor: str | None = None,
    occurred_at: str | None = None,
) -> TransitionEvent:
    """유일한 전이 관문 — 불법 전이·actor 없는 APPROVED 진입은 모두 예외로 거부.

    ★"승인 없이 APPROVED 도달 경로 0"의 기계적 강제: to==APPROVED 일 때 actor가 비어있으면
      (None·빈 문자열·공백만) 전이표상 합법이어도 무조건 거부한다 — site_basis의
      can_approve()·design_run_store의 can_approve_design_run() 이 각자 강제해온 규칙을
      원형 무관 공용 관문 하나로 흡수한다.
    ★occurred_at 을 명시 주입하면 순수(결정적)하게 테스트 가능 — 미주입 시에만 실제 시각을
      읽는다(⑦ provenance 계열의 "결정성" 관례를 최대한 따르되, 실사용 시엔 실제 시각 필요).
    """
    current = ApprovalState(current)
    to = ApprovalState(to)
    if not can_transition(current, to):
        raise IllegalApprovalTransitionError(
            f"{current.value} → {to.value} 전이는 허용되지 않습니다"
            f"(합법 전이: {sorted(s.value for s in _LEGAL_TRANSITIONS.get(current, frozenset()))})."
        )
    if to == ApprovalState.APPROVED and not (actor and str(actor).strip()):
        raise IllegalApprovalTransitionError(
            "APPROVED 진입에는 승인자(actor)가 필요합니다(승인 없는 자동 APPROVED 금지)."
        )
    return TransitionEvent(
        from_state=current, to_state=to, actor=actor, occurred_at=occurred_at or _utc_now_iso(),
    )


__all__ = [
    "ApprovalState",
    "IllegalApprovalTransitionError",
    "TransitionEvent",
    "apply_transition",
    "can_transition",
]
