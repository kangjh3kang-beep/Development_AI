"""Domain agents router for G87."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import (
    DomainAgentApprovalBatchDecisionRequest,
    DomainAgentApprovalBatchDecisionResponse,
    DomainAgentApprovalDecisionRequest,
    DomainAgentApprovalQueueItemResponse,
    DomainAgentApprovalQueueResponse,
    DomainAgentHistoryItemResponse,
    DomainAgentHistoryResponse,
    DomainAgentRunRequest,
    DomainAgentRunResponse,
    DomainMultiAnalysisRequest,
    DomainMultiAnalysisResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.domain_agents_service import DomainAgentsService

router = APIRouter()


def _serialize_result(task, approval) -> DomainAgentRunResponse:
    return DomainAgentRunResponse(
        task_id=task.id,
        project_id=task.project_id,
        domain=task.domain,
        status=task.status,
        confidence_score=task.confidence_score,
        recommendation=task.recommendation,
        findings=list((task.output_summary_json or {}).get("findings", [])),
        approval_required=task.requires_approval,
        approval_status=approval.status if approval is not None else "not-required",
    )


def _serialize_history_item(task, approval) -> DomainAgentHistoryItemResponse:
    return DomainAgentHistoryItemResponse(
        task_id=task.id,
        project_id=task.project_id,
        domain=task.domain,
        status=task.status,
        confidence_score=task.confidence_score,
        recommendation=task.recommendation,
        findings=list((task.output_summary_json or {}).get("findings", [])),
        approval_required=task.requires_approval,
        approval_status=approval.status if approval is not None else "not-required",
        approver_role=approval.approver_role if approval is not None else None,
        narrative=task.narrative,
        created_at=task.created_at,
    )


def _serialize_approval_item(approval, task) -> DomainAgentApprovalQueueItemResponse:
    return DomainAgentApprovalQueueItemResponse(
        approval_id=approval.id,
        task_id=task.id,
        project_id=task.project_id,
        domain=task.domain,
        approver_role=approval.approver_role,
        status=approval.status,
        rationale=approval.rationale,
        recommendation=task.recommendation,
        confidence_score=task.confidence_score,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
    )


@router.post("/run", response_model=DomainAgentRunResponse)
async def run_domain_agent(
    body: DomainAgentRunRequest,
    current_user: CurrentUser = Depends(RequirePermission("domain_agents", "write")),
    db: AsyncSession = Depends(get_db),
) -> DomainAgentRunResponse:
    """Run a single domain-specific analysis."""
    service = DomainAgentsService(db)
    task, approval = await service.run_domain(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        domain=body.domain,
        question=body.question,
        context=body.context,
        approval_role=body.approval_role,
    )
    return _serialize_result(task, approval)


@router.post("/multi-analysis", response_model=DomainMultiAnalysisResponse)
async def run_multi_domain_analysis(
    body: DomainMultiAnalysisRequest,
    current_user: CurrentUser = Depends(RequirePermission("domain_agents", "write")),
    db: AsyncSession = Depends(get_db),
) -> DomainMultiAnalysisResponse:
    """Run multiple domain-specific analyses."""
    service = DomainAgentsService(db)
    domains = body.domains or ["asset", "development", "transaction", "finance"]

    items: list[DomainAgentRunResponse] = []
    for domain in domains:
        task, approval = await service.run_domain(
            tenant_id=current_user.tenant_id,
            project_id=body.project_id,
            domain=domain,
            question=body.question,
            context=body.context,
            approval_role=body.approval_role,
        )
        items.append(_serialize_result(task, approval))

    proceed_count = sum(1 for item in items if item.recommendation == "proceed")
    summary = (
        f"{len(items)} domain analyses completed. "
        f"{proceed_count} recommend proceed and {len(items) - proceed_count} require conditions or escalation."
    )
    return DomainMultiAnalysisResponse(items=items, portfolio_summary=summary)


@router.get("/history", response_model=DomainAgentHistoryResponse)
async def get_domain_agent_history(
    project_id: UUID | None = None,
    limit: int = 8,
    current_user: CurrentUser = Depends(RequirePermission("domain_agents", "read")),
    db: AsyncSession = Depends(get_db),
) -> DomainAgentHistoryResponse:
    """Return persisted domain-agent execution history."""
    service = DomainAgentsService(db)
    rows = await service.list_history(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
        limit=limit,
    )
    return DomainAgentHistoryResponse(
        items=[_serialize_history_item(task, approval) for task, approval in rows]
    )


@router.get("/approvals", response_model=DomainAgentApprovalQueueResponse)
async def get_domain_agent_approval_queue(
    project_id: UUID | None = None,
    limit: int = 8,
    status: str | None = "pending",
    approver_role: str | None = None,
    current_user: CurrentUser = Depends(RequirePermission("domain_agents", "read")),
    db: AsyncSession = Depends(get_db),
) -> DomainAgentApprovalQueueResponse:
    """Return the persisted approval queue for domain-agent tasks."""
    service = DomainAgentsService(db)
    normalized_status = None if status in {None, "all"} else status
    rows = await service.list_approval_queue(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
        limit=limit,
        status=normalized_status,
        approver_role=approver_role,
    )
    return DomainAgentApprovalQueueResponse(
        items=[_serialize_approval_item(approval, task) for approval, task in rows]
    )


@router.post(
    "/approvals/decision-batch",
    response_model=DomainAgentApprovalBatchDecisionResponse,
)
async def decide_domain_agent_approvals_batch(
    body: DomainAgentApprovalBatchDecisionRequest,
    current_user: CurrentUser = Depends(RequirePermission("domain_agents", "write")),
    db: AsyncSession = Depends(get_db),
) -> DomainAgentApprovalBatchDecisionResponse:
    """Approve or reject multiple pending domain-agent approval items."""
    service = DomainAgentsService(db)
    try:
        rows = await service.decide_approvals_batch(
            tenant_id=current_user.tenant_id,
            project_id=body.project_id,
            approval_ids=body.approval_ids,
            decision=body.decision,
            rationale=body.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    items = [_serialize_approval_item(approval, task) for approval, task in rows]
    return DomainAgentApprovalBatchDecisionResponse(
        items=items,
        updated_count=len(items),
    )


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=DomainAgentApprovalQueueItemResponse,
)
async def decide_domain_agent_approval(
    approval_id: UUID,
    body: DomainAgentApprovalDecisionRequest,
    current_user: CurrentUser = Depends(RequirePermission("domain_agents", "write")),
    db: AsyncSession = Depends(get_db),
) -> DomainAgentApprovalQueueItemResponse:
    """Approve or reject a persisted domain-agent approval item."""
    service = DomainAgentsService(db)
    try:
        approval, task = await service.decide_approval(
            tenant_id=current_user.tenant_id,
            approval_id=approval_id,
            decision=body.decision,
            rationale=body.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return _serialize_approval_item(approval, task)
