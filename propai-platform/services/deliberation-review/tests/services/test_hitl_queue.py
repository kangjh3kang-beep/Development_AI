"""AT-5 — HITL 큐 우선순위(임박 사업 가중) + SLA aging 알림.

W1-B: SoD(직무분리) dual-control — approver 신원 필수·author==approver 차단.
R1 봉합(R2): activation은 "task 발견 + candidate-task 결속 + SoD 통과"를 모두 게이팅.
"""
import pytest

from app.contracts.hitl_task import HITLHistoryEvent, HITLTask, Priority
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
from app.core.errors import DataInsufficientError, RuleContractError, SelfApprovalError
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


def test_hitl_approve_rejects_whitespace_only_approver():
    """F3 — approver가 공백뿐이면 strip 후 빈값 취급, ValueError."""
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t5b", candidate_id="c5b"))
    cand = RuleCandidate(candidate_id="c5b", status=CandidateStatus.DRAFT)
    with pytest.raises(ValueError):
        q.approve(task.task_id, cand, approver="   ")


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


def test_hitl_approve_blocks_self_approval_with_whitespace_padding():
    """F3 재현 — author/approver 앞뒤 공백 차이만으로 자기승인 우회 금지(strip 후 비교)."""
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t6b", candidate_id="c6b", author="alice"))
    cand = RuleCandidate(candidate_id="c6b", status=CandidateStatus.DRAFT)
    with pytest.raises(SelfApprovalError):
        q.approve(task.task_id, cand, approver=" alice ")
    assert task.status == "PENDING"


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
    assert task.history[-1] == HITLHistoryEvent(
        action="approve", actor="bob", at=task.approved_at, sod_check="passed",
    )


def test_hitl_approve_author_none_passes_with_skip_marker_pending_wiring():
    """author 기입 경로 미배선 상태의 기본 케이스 — 차단 불가지만 무언 통과 금지, 명시 표식."""
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t8", candidate_id="c8"))  # author 미지정 -> None(배선 전 기본)
    cand = RuleCandidate(candidate_id="c8", status=CandidateStatus.DRAFT)
    activated = q.approve(task.task_id, cand, approver="carol")
    assert activated.status == CandidateStatus.ACTIVE
    assert task.sod_check == "skipped(author 미기록)"
    assert task.approved_by == "carol"


def test_hitl_approve_blocks_activation_when_task_not_found():
    """BYPASS-A 재현(F1) — 존재하지 않는 task_id로 후보 활성화 시도는 전면 차단."""
    q = HITLQueue()
    cand = RuleCandidate(candidate_id="ghost-cand", status=CandidateStatus.DRAFT)
    with pytest.raises(DataInsufficientError):
        q.approve("no-such-task", cand, approver="mallory")
    assert cand.status == CandidateStatus.DRAFT  # 활성화되지 않음(원본 그대로)


def test_hitl_approve_blocks_candidate_task_binding_mismatch():
    """BYPASS-B 재현(F2b) — author=None 무관 태스크를 방패로 다른 candidate_id 활성화 시도 차단."""
    q = HITLQueue()
    unrelated_task = q.add(HITLTask(task_id="shield", candidate_id="other-cand"))  # author=None
    attacker_cand = RuleCandidate(candidate_id="mine", status=CandidateStatus.DRAFT)
    with pytest.raises(RuleContractError):
        q.approve(unrelated_task.task_id, attacker_cand, approver="mallory")
    assert attacker_cand.status == CandidateStatus.DRAFT
    assert unrelated_task.status == "PENDING"  # 방패로 쓰인 태스크도 변이되지 않음


def test_hitl_add_accepts_author_kwarg_for_future_wiring():
    """F4 — add()의 author kwarg로 SoD 실질 적용 배선 가능(기본 경로는 author=None -> skip)."""
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t-auth", candidate_id="c-auth"), author="alice")
    assert task.author == "alice"


def test_hitl_reject_records_identity_and_does_not_touch_candidate_activation():
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t9", candidate_id="c9", author="dave"))
    rejected = q.reject(task.task_id, approver="erin")
    assert rejected.status == "REJECTED"
    assert rejected.rejected_by == "erin"
    assert rejected.rejected_at is not None
    # reject는 실제 차단을 수행하지 않으므로 "passed"를 참칭하지 않는다(LOW 봉합).
    assert rejected.sod_check == "n/a(reject)"
    assert rejected.history[-1].action == "reject"


def test_hitl_reject_requires_approver():
    q = HITLQueue()
    task = q.add(HITLTask(task_id="t10", candidate_id="c10"))
    with pytest.raises(ValueError):
        q.reject(task.task_id, approver="")


def test_hitl_reject_missing_task_returns_none():
    q = HITLQueue()
    assert q.reject("no-such-task", approver="erin") is None
