"""R2 — HITL 우선순위 큐 + SLA. priority = 사용빈도 + 임박가중(파라미터). aging 알림.

승인 시 RuleCandidate.status=ACTIVE 전이(분석 활성). 임계/가중은 param 주입(하드코딩 금지).
'now'는 day-index로 주입(결정론, 시계 비의존).

SoD(직무분리, v4.0 Wave1 W1-B — 승인자 신원 dual-control): approve()/reject()는 approver(신원)를
필수 인자로 받는다(공백 strip 후 빈값이면 ValueError — approver/author는 정규화된 principal ID
라는 계약을 전제하되 방어적으로 strip만 적용, casefold는 ID 체계 확정 전이라 과도).

approve()는 반드시 "①task 발견 ②candidate-task 결속 일치 ③SoD 통과"를 모두 게이팅한 뒤에만
후보를 ACTIVE로 전이한다 — 이 중 하나라도 실패하면 예외를 던지고 후보는 비활성 그대로다:
- task_id가 큐에 없으면 DataInsufficientError(활성화 근거 데이터 결손).
- candidate.candidate_id != task.candidate_id면 RuleContractError(엉뚱한 task를 방패로 삼는
  candidate 활성화 차단 — author=None 태스크를 골라 결속 없이 승인 호출하는 우회 경로 봉쇄).
- author가 기록돼 있고(strip 후) author == approver면 SelfApprovalError(동일인 작성·승인 차단).

정직 표기: author를 채우는 생성 경로가 아직 없어 신규 태스크는 기본 author=None → SoD 사실상
skip(레거시 데이터 문제가 아니라 배선 미완료). add()가 author를 받으면 그 태스크부터 SoD 실질
적용(후속 배선 지점). skip 상태는 sod_check="skipped(author 미기록)"으로 명시(무언 통과 금지).

reject()는 활성화(ACTIVE 전이·신뢰 상승)를 유발하지 않으므로 자기거부(author==approver)까지
차단하지는 않는다(설계 결정 — SoD는 신뢰 상승 행위인 승인에 한정) — approver 신원은 동일하게
필수·기록하되, sod_check는 실제 차단이 수행되지 않았음을 "n/a(reject)"로 정직하게 표기한다
("passed"로 과대표기하지 않음).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.contracts.hitl_task import HITLHistoryEvent, HITLTask, Priority
from app.contracts.rule_candidate import CandidateStatus, RuleCandidate
from app.core.errors import DataInsufficientError, RuleContractError, SelfApprovalError
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

    def add(self, task: HITLTask, *, author: str | None = None) -> HITLTask:
        """큐에 태스크 등록. author kwarg는 SoD 배선용(생략 시 task.author 그대로 — 기본 None)."""
        if author is not None:
            task.author = author
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
    def _require_approver(approver: str) -> str:
        """approver 필수·공백 strip(경량 정규화). 빈 문자열/공백뿐이면 ValueError."""
        normalized = (approver or "").strip()
        if not normalized:
            raise ValueError("approver는 필수임(SoD — 승인자 신원 미기록 금지)")
        return normalized

    @staticmethod
    def _sod_marker(task: HITLTask, *, enforce: bool) -> str:
        """SoD 판정 표식(무언 통과 금지).

        author 기입 경로 부재로 신규 태스크는 author=None이 기본 — 이 경우 차단 근거가
        없어 "skipped(author 미기록)"으로 명시(레거시 문제 아님, 배선 미완료).
        enforce=False(reject)는 애초에 자기거부 차단을 수행하지 않으므로 "passed"를
        참칭하지 않고 "n/a(reject)"로 표기한다.
        """
        if task.author is None:
            return "skipped(author 미기록)"
        return "passed" if enforce else "n/a(reject)"

    @staticmethod
    def _append_history(task: HITLTask, *, action: str, actor: str, at: datetime, sod_check: str) -> None:
        """이력 append 전용(list.append만 — 과거 원소 변경 금지 관례).

        한계: HITLHistoryEvent(pydantic)의 immutability(frozen) 강제는 구조 변경이 필요해
        이번 스코프 밖 — append-only는 이 헬퍼를 유일한 기입 경로로 강제하는 관례로 보장한다.
        """
        task.history.append(HITLHistoryEvent(action=action, actor=actor, at=at, sod_check=sod_check))

    def approve(self, task_id: str, candidate: RuleCandidate, *, approver: str) -> RuleCandidate:
        approver = self._require_approver(approver)
        task = self._find(task_id)
        if task is None:
            raise DataInsufficientError(
                f"HITL 태스크 결손 — 활성화 거부(task_id={task_id})"
            )
        if candidate.candidate_id != task.candidate_id:
            raise RuleContractError(
                "candidate-task 결속 불일치 — 활성화 거부"
                f"(task_id={task_id}, candidate.candidate_id={candidate.candidate_id}, "
                f"task.candidate_id={task.candidate_id})"
            )
        author_norm = task.author.strip() if task.author is not None else None
        if author_norm is not None and author_norm == approver:
            raise SelfApprovalError(
                f"SoD 위반 — 작성자와 승인자가 동일함(task_id={task_id}, actor={approver})"
            )
        sod_check = self._sod_marker(task, enforce=True)
        now = datetime.now(timezone.utc)
        task.status = "APPROVED"
        task.approved_by = approver
        task.approved_at = now
        task.sod_check = sod_check
        self._append_history(task, action="approve", actor=approver, at=now, sod_check=sod_check)
        return candidate.model_copy(update={"status": CandidateStatus.ACTIVE})

    def reject(self, task_id: str, *, approver: str) -> HITLTask | None:
        approver = self._require_approver(approver)
        task = self._find(task_id)
        if task is None:
            return None
        sod_check = self._sod_marker(task, enforce=False)
        now = datetime.now(timezone.utc)
        task.status = "REJECTED"
        task.rejected_by = approver
        task.rejected_at = now
        task.sod_check = sod_check
        self._append_history(task, action="reject", actor=approver, at=now, sod_check=sod_check)
        return task
