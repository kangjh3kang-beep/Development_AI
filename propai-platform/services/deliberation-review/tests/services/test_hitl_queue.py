"""AT-5 — HITL 큐 우선순위(임박 사업 가중) + SLA aging 알림."""
from app.contracts.hitl_task import HITLTask, Priority
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
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
    activated = q.approve(task.task_id, cand)
    assert activated.status == CandidateStatus.ACTIVE
