"""R2 — HITL 우선순위 큐 + SLA. priority = 사용빈도 + 임박가중(파라미터). aging 알림.

승인 시 RuleCandidate.status=ACTIVE 전이(분석 활성). 임계/가중은 param 주입(하드코딩 금지).
'now'는 day-index로 주입(결정론, 시계 비의존).
"""
from __future__ import annotations

from app.contracts.hitl_task import HITLTask, Priority
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
from app.core.parameters import param


class HITLQueue:
    def __init__(self) -> None:
        self._tasks: list[HITLTask] = []

    def _priority(self, task: HITLTask) -> Priority:
        weight = float(param("hitl_imminent_weight")) if task.imminent else 0.0
        score = task.usage_freq + weight
        if score >= float(param("hitl_priority_high_threshold")):
            return Priority.HIGH
        if score >= float(param("hitl_priority_medium_threshold")):
            return Priority.MEDIUM
        return Priority.LOW

    def add(self, task: HITLTask) -> HITLTask:
        task.priority = self._priority(task)
        self._tasks.append(task)
        return task

    def next(self) -> HITLTask | None:
        pending = [t for t in self._tasks if t.status == "PENDING"]
        if not pending:
            return None
        # 우선순위 높은 순, 동률이면 SLA 임박(작은 due) 순.
        return max(pending, key=lambda t: (int(t.priority), -t.sla_due_day))

    def aging_alerts(self, now: int) -> list[HITLTask]:
        """SLA 경과(now > sla_due_day) PENDING 태스크 알림."""
        return [t for t in self._tasks if t.status == "PENDING" and t.sla_due_day < now]

    def approve(self, task_id: str, candidate: RuleCandidate) -> RuleCandidate:
        for t in self._tasks:
            if t.task_id == task_id:
                t.status = "APPROVED"
                break
        return candidate.model_copy(update={"status": CandidateStatus.ACTIVE})
