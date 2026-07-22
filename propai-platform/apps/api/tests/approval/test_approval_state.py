"""공용 승인 상태머신(ApprovalState, W1-A) 게이트 테스트 — 순수 함수·무 DB.

v4.0 명세 P13 Gate("승인 없이 Published/APPROVED 경로 0")를 기계 검증한다:
 ① 전이표 완전성 — 5x5=25개 (from,to) 전 조합 중 합법 4건만 통과, 나머지 21건은 전부 거부.
 ② actor 없는 APPROVED 진입 0 — 합법 전이(EXPERT_REVIEWED→APPROVED)라도 actor가
    None/빈 문자열/공백뿐이면 여전히 거부된다.
 ③ 정상 승인 전이는 TransitionEvent(from/to/actor/occurred_at)를 정확히 반환한다.
"""
from __future__ import annotations

import itertools

import pytest

from app.services.approval.approval_state import (
    ApprovalState,
    IllegalApprovalTransitionError,
    TransitionEvent,
    apply_transition,
    can_transition,
)

# 전이표상 유일하게 합법인 4개 전이(선형 사슬) — 그 외 전부 불법.
_LEGAL_PAIRS = {
    (ApprovalState.DRAFT, ApprovalState.MACHINE_VALIDATED),
    (ApprovalState.MACHINE_VALIDATED, ApprovalState.EXPERT_REVIEWED),
    (ApprovalState.EXPERT_REVIEWED, ApprovalState.APPROVED),
    (ApprovalState.APPROVED, ApprovalState.SUPERSEDED),
}


# ── ① 전이표 완전성 — 전 상태쌍(25개) 전수 검사 ─────────────────────────────


@pytest.mark.parametrize("from_state,to_state", list(itertools.product(ApprovalState, ApprovalState)))
def test_transition_table_exhaustive(from_state, to_state):
    """25개 (from,to) 조합 중 합법 4건만 True, 나머지는 전부 False."""
    expected = (from_state, to_state) in _LEGAL_PAIRS
    assert can_transition(from_state, to_state) is expected


@pytest.mark.parametrize("from_state,to_state", list(itertools.product(ApprovalState, ApprovalState)))
def test_apply_transition_rejects_illegal_pairs(from_state, to_state):
    """전이표에 없는 조합은 apply_transition이 예외로 거부(actor 유무와 무관하게 우선 거부)."""
    if (from_state, to_state) in _LEGAL_PAIRS:
        pytest.skip("합법 전이는 별도 테스트에서 검증")
    with pytest.raises(IllegalApprovalTransitionError):
        apply_transition(from_state, to_state, actor="누군가")


def test_legal_transitions_succeed_with_actor_when_not_approved():
    """APPROVED가 아닌 합법 전이는 actor 없이도 통과한다(actor 필수는 APPROVED 전용)."""
    ev = apply_transition(ApprovalState.DRAFT, ApprovalState.MACHINE_VALIDATED)
    assert isinstance(ev, TransitionEvent)
    assert ev.from_state == ApprovalState.DRAFT
    assert ev.to_state == ApprovalState.MACHINE_VALIDATED
    assert ev.actor is None
    assert ev.occurred_at  # 비어있지 않음(문자열)

    ev2 = apply_transition(ApprovalState.MACHINE_VALIDATED, ApprovalState.EXPERT_REVIEWED)
    assert ev2.to_state == ApprovalState.EXPERT_REVIEWED


# ── ② actor 없는 APPROVED 진입 0(v4.0 Gate 핵심) ────────────────────────────


@pytest.mark.parametrize("actor", [None, "", "   "])
def test_approved_entry_without_actor_is_rejected(actor):
    """EXPERT_REVIEWED→APPROVED는 전이표상 합법이지만, actor가 비어있으면 반드시 거부된다."""
    with pytest.raises(IllegalApprovalTransitionError):
        apply_transition(ApprovalState.EXPERT_REVIEWED, ApprovalState.APPROVED, actor=actor)


def test_approved_entry_with_actor_succeeds():
    """actor가 있으면 EXPERT_REVIEWED→APPROVED가 정상 전이되고 이력에 actor가 남는다."""
    ev = apply_transition(
        ApprovalState.EXPERT_REVIEWED, ApprovalState.APPROVED,
        actor="reviewer@propai.io", occurred_at="2026-07-22T00:00:00+00:00",
    )
    assert ev.from_state == ApprovalState.EXPERT_REVIEWED
    assert ev.to_state == ApprovalState.APPROVED
    assert ev.actor == "reviewer@propai.io"
    assert ev.occurred_at == "2026-07-22T00:00:00+00:00"


def test_approved_to_superseded_does_not_require_actor():
    """APPROVED→SUPERSEDED(폐기·재발급 트리거)는 승인 액션이 아니므로 actor 불필요."""
    ev = apply_transition(ApprovalState.APPROVED, ApprovalState.SUPERSEDED)
    assert ev.to_state == ApprovalState.SUPERSEDED
    assert ev.actor is None


def test_superseded_is_terminal():
    """SUPERSEDED에서는 어떤 상태로도 전이할 수 없다(재발급은 새 DRAFT로 원칙)."""
    for to_state in ApprovalState:
        assert can_transition(ApprovalState.SUPERSEDED, to_state) is False
