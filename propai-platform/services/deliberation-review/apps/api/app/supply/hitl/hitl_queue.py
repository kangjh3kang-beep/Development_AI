"""R2 — HITL 우선순위 큐 + SLA. priority = 사용빈도 + 임박가중(파라미터). aging 알림.

승인 시 RuleCandidate.status=ACTIVE 전이(분석 활성). 임계/가중은 param 주입(하드코딩 금지).
'now'는 day-index로 주입(결정론, 시계 비의존).

SoD(직무분리, v4.0 Wave1 W1-B — 승인자 신원 dual-control): approve()/reject()는 approver(신원)를
필수 인자로 받는다. author(작성자)가 기록돼 있고 author == approver면 approve()는
SelfApprovalError로 거부한다(동일인 작성·승인 기술적 차단). author 미기록(레거시 데이터)은
차단할 근거가 없어 통과시키되, sod_check="skipped(author 미기록)" 표식으로 무언 통과를 방지한다.
reject()는 활성화(ACTIVE 전이)를 유발하지 않으므로 자기거부(author==approver)까지 차단하지는
않는다(설계 결정 — SoD는 신뢰 상승 행위인 승인에 한정) — 다만 approver 신원은 동일하게 필수·기록.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.contracts.hitl_task import HITLTask, Priority
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
from app.core.errors import SelfApprovalError
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

    def _find(self, task_id: str) -> HITLTask | None:
        for t in self._tasks:
            if t.task_id == task_id:
                return t
        return None

    @staticmethod
    def _sod_marker(task: HITLTask, approver: str) -> str:
        """SoD 판정 표식(무언 통과 금지). author 미기록이면 차단 불가 사실을 명시적으로 남긴다."""
        if task.author is None:
            return "skipped(author 미기록)"
        return "passed"

    def approve(self, task_id: str, candidate: RuleCandidate, *, approver: str) -> RuleCandidate:
        if not approver:
            raise ValueError("approver는 필수임(SoD — 승인자 신원 미기록 금지)")
        task = self._find(task_id)
        if task is not None:
            if task.author is not None and task.author == approver:
                raise SelfApprovalError(
                    f"SoD 위반 — 작성자와 승인자가 동일함(task_id={task_id}, actor={approver})"
                )
            sod_check = self._sod_marker(task, approver)
            now = datetime.now(timezone.utc)
            task.status = "APPROVED"
            task.approved_by = approver
            task.approved_at = now
            task.sod_check = sod_check
            task.history.append({
                "action": "approve", "actor": approver, "at": now.isoformat(), "sod_check": sod_check,
            })
        return candidate.model_copy(update={"status": CandidateStatus.ACTIVE})

    def reject(self, task_id: str, *, approver: str) -> HITLTask | None:
        if not approver:
            raise ValueError("approver는 필수임(SoD — 승인자 신원 미기록 금지)")
        task = self._find(task_id)
        if task is not None:
            sod_check = self._sod_marker(task, approver)
            now = datetime.now(timezone.utc)
            task.status = "REJECTED"
            task.rejected_by = approver
            task.rejected_at = now
            task.sod_check = sod_check
            task.history.append({
                "action": "reject", "actor": approver, "at": now.isoformat(), "sod_check": sod_check,
            })
        return task
