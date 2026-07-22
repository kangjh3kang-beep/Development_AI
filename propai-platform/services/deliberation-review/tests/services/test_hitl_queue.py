"""AT-5 — HITL 큐 우선순위(임박 사업 가중) + SLA aging 알림.

W1-B: SoD(직무분리) dual-control — approver 신원 필수·author==approver 차단.
"""
import pytest

from app.contracts.hitl_task import HITLTask, Priority
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
from app.core.errors import SelfApprovalError
from app.supply.hitl.hitl_queue import HITLQueue

PAST_SLA = 999


def test_hitl_priority_and_aging_alert():
    q = HITLQueue()
    low = HITLTask(task_id="t1", candidate_id="c1", usage_freq=0.1, imminent=False, sla_due_day=10)
    high_imminent = HITLTask(task_id="t2", candidate_id="c2", usage_freq=0.8, imminent=True, sla_due_day=3)
    q.add(low)
    q.add(high_imminent)
    assert q.next().priority == Priority.HIGH
    assert q.aging_alerts(now=PAST_SLA)


def test_hitl_approve_activates_candidate():
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t3", candidate_id="c3", usage_freq=0.9, imminent=True))
    cand = RuleCandidate(candidate_id="c3", status=CandidateStatus.DRAFT)
    activated = q.approve(task.task_id, cand, approver="reviewer-1")
    assert activated.status == CandidateStatus.ACTIVE


def test_hitl_approve_requires_approver_kwarg():
    """approver 없는 호출은 시그니처상 불가(키워드 전용 필수 인자)."""
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t4", candidate_id="c4"))
    cand = RuleCandidate(candidate_id="c4", status=CandidateStatus.DRAFT)
    with pytest.raises(TypeError):
        q.approve(task.task_id, cand)  # type: ignore[call-arg]


def test_hitl_approve_rejects_empty_approver():
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t5", candidate_id="c5"))
    cand = RuleCandidate(candidate_id="c5", status=CandidateStatus.DRAFT)
    with pytest.raises(ValueError):
        q.approve(task.task_id, cand, approver="")


def test_hitl_approve_blocks_self_approval():
    """author == approver면 SelfApprovalError로 차단(동일인 작성·승인 금지)."""
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t6", candidate_id="c6", author="alice"))
    cand = RuleCandidate(candidate_id="c6", status=CandidateStatus.DRAFT)
    with pytest.raises(SelfApprovalError):
        q.approve(task.task_id, cand, approver="alice")
    # 차단됐으므로 태스크 상태는 변이되지 않는다.
    assert task.status == "PENDING"
    assert task.approved_by is None


def test_hitl_approve_allows_different_author_and_approver():
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t7", candidate_id="c7", author="alice"))
    cand = RuleCandidate(candidate_id="c7", status=CandidateStatus.DRAFT)
    activated = q.approve(task.task_id, cand, approver="bob")
    assert activated.status == CandidateStatus.ACTIVE
    assert task.status == "APPROVED"
    assert task.approved_by == "bob"
    assert task.approved_at is not None
    assert task.sod_check == "passed"
    assert task.history[-1] == {
        "action": "approve", "actor": "bob", "at": task.approved_at.isoformat(), "sod_check": "passed",
    }


def test_hitl_approve_legacy_author_none_passes_with_skip_marker():
    """author 미기록(레거시)은 차단 불가 — 그러나 무언 통과 금지, sod_check에 명시 표식."""
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t8", candidate_id="c8"))  # author 미지정 -> None
    cand = RuleCandidate(candidate_id="c8", status=CandidateStatus.DRAFT)
    activated = q.approve(task.task_id, cand, approver="carol")
    assert activated.status == CandidateStatus.ACTIVE
    assert task.sod_check == "skipped(author 미기록)"
    assert task.approved_by == "carol"


def test_hitl_reject_records_identity_and_does_not_touch_candidate_activation():
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t9", candidate_id="c9", author="dave"))
    rejected = q.reject(task.task_id, approver="erin")
    assert rejected.status == "REJECTED"
    assert rejected.rejected_by == "erin"
    assert rejected.rejected_at is not None
    assert rejected.sod_check == "passed"
    assert rejected.history[-1]["action"] == "reject"


def test_hitl_reject_requires_approver():
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t10", candidate_id="c10"))
    with pytest.raises(ValueError):
        q.reject(task.task_id, approver="")
