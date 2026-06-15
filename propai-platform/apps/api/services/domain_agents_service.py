"""Domain agent analysis service for Part F."""

from datetime import datetime, timezone
UTC = timezone.utc
from uuid import UUID

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_f_domain_agents import DomainAgentApproval, DomainAgentTask

logger = structlog.get_logger(__name__)

_DOMAIN_LABELS = {
    "asset": "asset management",
    "development": "development execution",
    "transaction": "transaction strategy",
    "finance": "capital structure",
}


class DomainAgentsService:
    """Run deterministic domain analyses and capture approval state."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _score(question: str, context: dict) -> tuple[float, str, list[dict]]:
        score = 0.7
        findings: list[dict] = []

        text = question.lower()
        if "risk" in text or "downside" in text:
            score -= 0.06
            findings.append({"factor": "risk-focus", "impact": "caution"})
        if context.get("occupancy_rate", 0) >= 0.9:
            score += 0.08
            findings.append({"factor": "occupancy", "impact": "positive"})
        if context.get("ltv", 0) >= 0.7:
            score -= 0.1
            findings.append({"factor": "ltv", "impact": "negative"})
        if context.get("schedule_buffer_months", 0) >= 3:
            score += 0.05
            findings.append({"factor": "schedule-buffer", "impact": "positive"})
        if context.get("pre_leasing_ratio", 0) >= 0.5:
            score += 0.06
            findings.append({"factor": "pre-leasing", "impact": "positive"})

        bounded = round(max(0.35, min(0.95, score)), 4)
        if bounded >= 0.8:
            recommendation = "proceed"
        elif bounded >= 0.65:
            recommendation = "proceed-with-conditions"
        else:
            recommendation = "escalate"
        return bounded, recommendation, findings

    async def run_domain(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        domain: str,
        question: str,
        context: dict,
        approval_role: str,
    ) -> tuple[DomainAgentTask, DomainAgentApproval | None]:
        label = _DOMAIN_LABELS.get(domain, domain)
        confidence_score, recommendation, findings = self._score(question, context)
        requires_approval = recommendation != "proceed"

        task = DomainAgentTask(
            tenant_id=tenant_id,
            project_id=project_id,
            domain=domain,
            task_type="analysis",
            status="completed",
            confidence_score=confidence_score,
            requires_approval=requires_approval,
            input_summary_json={"question": question, "context": context},
            output_summary_json={"findings": findings, "label": label},
            recommendation=recommendation,
            narrative=(
                f"{label.capitalize()} analysis completed with confidence {confidence_score:.0%}. "
                f"Recommendation: {recommendation}."
            ),
        )
        self.db.add(task)
        await self.db.flush()

        approval: DomainAgentApproval | None = None
        if requires_approval:
            approval = DomainAgentApproval(
                tenant_id=tenant_id,
                project_id=project_id,
                task_id=task.id,
                approver_role=approval_role,
                status="pending",
                rationale=f"{label.capitalize()} analysis requires human review before release.",
            )
            self.db.add(approval)

        await self.db.commit()
        await self.db.refresh(task)
        if approval is not None:
            await self.db.refresh(approval)

        # Phase 0 unit d: 산출물 요약을 원장 단일 SSOT에 best-effort 일원화(실패 무중단).
        try:
            from app.services.ledger.ledger_adapters import record_domain_agent_task

            await record_domain_agent_task(
                task={
                    "domain": task.domain, "task_type": task.task_type,
                    "status": task.status, "confidence_score": task.confidence_score,
                    "recommendation": task.recommendation,
                    "requires_approval": task.requires_approval,
                    "id": str(task.id),
                },
                tenant_id=str(tenant_id), project_id=str(project_id),
                created_by=None,
            )
        except Exception as e:  # noqa: BLE001 — 원장 적재 실패가 도메인 분석을 막지 않음
            logger.warning("원장 배선 append 실패(domain_agent)", err=str(e)[:160])

        return task, approval

    async def list_history(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID | None = None,
        limit: int = 8,
    ) -> list[tuple[DomainAgentTask, DomainAgentApproval | None]]:
        query = (
            select(DomainAgentTask, DomainAgentApproval)
            .outerjoin(
                DomainAgentApproval,
                and_(
                    DomainAgentApproval.task_id == DomainAgentTask.id,
                    DomainAgentApproval.tenant_id == tenant_id,
                ),
            )
            .where(
                DomainAgentTask.tenant_id == tenant_id,
                DomainAgentTask.task_type == "analysis",
            )
            .order_by(DomainAgentTask.created_at.desc())
            .limit(limit)
        )
        if project_id is not None:
            query = query.where(DomainAgentTask.project_id == project_id)

        return list((await self.db.execute(query)).all())

    async def list_approval_queue(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID | None = None,
        limit: int = 8,
        status: str | None = "pending",
        approver_role: str | None = None,
    ) -> list[tuple[DomainAgentApproval, DomainAgentTask]]:
        query = (
            select(DomainAgentApproval, DomainAgentTask)
            .join(
                DomainAgentTask,
                and_(
                    DomainAgentTask.id == DomainAgentApproval.task_id,
                    DomainAgentTask.tenant_id == tenant_id,
                ),
            )
            .where(DomainAgentApproval.tenant_id == tenant_id)
            .order_by(DomainAgentApproval.created_at.desc())
            .limit(limit)
        )
        if project_id is not None:
            query = query.where(DomainAgentApproval.project_id == project_id)
        if status is not None:
            query = query.where(DomainAgentApproval.status == status)
        if approver_role is not None:
            query = query.where(DomainAgentApproval.approver_role == approver_role)

        return list((await self.db.execute(query)).all())

    async def decide_approval(
        self,
        *,
        tenant_id: UUID,
        approval_id: UUID,
        decision: str,
        rationale: str | None,
    ) -> tuple[DomainAgentApproval, DomainAgentTask]:
        query = (
            select(DomainAgentApproval, DomainAgentTask)
            .join(
                DomainAgentTask,
                and_(
                    DomainAgentTask.id == DomainAgentApproval.task_id,
                    DomainAgentTask.tenant_id == tenant_id,
                ),
            )
            .where(
                DomainAgentApproval.tenant_id == tenant_id,
                DomainAgentApproval.id == approval_id,
            )
            .limit(1)
        )
        row = (await self.db.execute(query)).first()
        if row is None:
            raise ValueError("Approval not found")

        approval, task = row
        approval.status = decision
        approval.rationale = rationale or approval.rationale
        approval.decided_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(approval)
        await self.db.refresh(task)
        return approval, task

    async def decide_approvals_batch(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        approval_ids: list[UUID],
        decision: str,
        rationale: str | None,
    ) -> list[tuple[DomainAgentApproval, DomainAgentTask]]:
        if not approval_ids:
            raise ValueError("At least one approval ID is required")

        ordered_approval_ids = list(dict.fromkeys(approval_ids))
        query = (
            select(DomainAgentApproval, DomainAgentTask)
            .join(
                DomainAgentTask,
                and_(
                    DomainAgentTask.id == DomainAgentApproval.task_id,
                    DomainAgentTask.tenant_id == tenant_id,
                ),
            )
            .where(
                DomainAgentApproval.tenant_id == tenant_id,
                DomainAgentApproval.project_id == project_id,
                DomainAgentApproval.status == "pending",
                DomainAgentApproval.id.in_(ordered_approval_ids),
            )
        )
        rows = list((await self.db.execute(query)).all())
        if len(rows) != len(ordered_approval_ids):
            raise LookupError("One or more pending approvals were not found")

        rows_by_id = {approval.id: (approval, task) for approval, task in rows}
        decided_at = datetime.now(UTC)

        for approval_id in ordered_approval_ids:
            approval, _task = rows_by_id[approval_id]
            approval.status = decision
            approval.rationale = rationale or approval.rationale
            approval.decided_at = decided_at

        await self.db.commit()

        ordered_rows: list[tuple[DomainAgentApproval, DomainAgentTask]] = []
        for approval_id in ordered_approval_ids:
            approval, task = rows_by_id[approval_id]
            await self.db.refresh(approval)
            await self.db.refresh(task)
            ordered_rows.append((approval, task))
        return ordered_rows
