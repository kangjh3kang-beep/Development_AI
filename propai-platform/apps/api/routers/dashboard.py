"""Dashboard endpoints backed by current tenant data."""

from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from packages.schemas.models import (
    DashboardActivityItem,
    DashboardRecentActivityResponse,
    DashboardStatsResponse,
    DashboardTimelinePoint,
    DashboardTimelineResponse,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.ai_usage_log import AIUsageLog
from apps.api.database.models.api_key import APIKey
from apps.api.database.models.project import Project
from apps.api.database.models.webhook import Webhook
from apps.api.database.session import get_db

router = APIRouter()


def _month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(RequirePermission("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
) -> DashboardStatsResponse:
    start_of_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    project_rows = (
        await db.execute(
            select(Project.status, func.count())
            .where(Project.tenant_id == current_user.tenant_id, Project.is_deleted.is_(False))
            .group_by(Project.status)
        )
    ).all()
    projects_by_status = {status: count for status, count in project_rows}

    active_webhooks = await db.scalar(
        select(func.count())
        .select_from(Webhook)
        .where(Webhook.tenant_id == current_user.tenant_id, Webhook.is_active.is_(True))
    )
    active_api_keys = await db.scalar(
        select(func.count())
        .select_from(APIKey)
        .where(APIKey.tenant_id == current_user.tenant_id, APIKey.is_active.is_(True))
    )
    ai_cost_month_usd, ai_tokens_month = (
        await db.execute(
            select(
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0),
                func.coalesce(
                    func.sum(
                        func.coalesce(AIUsageLog.input_tokens, 0)
                        + func.coalesce(AIUsageLog.output_tokens, 0)
                    ),
                    0,
                ),
            ).where(
                AIUsageLog.tenant_id == current_user.tenant_id,
                AIUsageLog.created_at >= start_of_month,
            )
        )
    ).one()

    return DashboardStatsResponse(
        total_projects=sum(projects_by_status.values()),
        projects_by_status=projects_by_status,
        active_webhooks=int(active_webhooks or 0),
        active_api_keys=int(active_api_keys or 0),
        ai_cost_month_usd=round(float(ai_cost_month_usd or 0.0), 6),
        ai_tokens_month=int(ai_tokens_month or 0),
    )


@router.get("/portfolio/timeline", response_model=DashboardTimelineResponse)
async def get_portfolio_timeline(
    current_user: CurrentUser = Depends(RequirePermission("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
) -> DashboardTimelineResponse:
    created_rows = (
        await db.execute(
            select(Project.created_at)
            .where(Project.tenant_id == current_user.tenant_id, Project.is_deleted.is_(False))
            .order_by(Project.created_at.desc())
            .limit(120)
        )
    ).scalars().all()

    month_counts = Counter(_month_key(created_at) for created_at in created_rows if created_at is not None)
    items = [
        DashboardTimelinePoint(period=period, project_count=count)
        for period, count in sorted(month_counts.items())
    ]
    return DashboardTimelineResponse(items=items)


@router.get("/activity/recent", response_model=DashboardRecentActivityResponse)
async def get_recent_activity(
    current_user: CurrentUser = Depends(RequirePermission("dashboard", "read")),
    db: AsyncSession = Depends(get_db),
) -> DashboardRecentActivityResponse:
    activities: list[DashboardActivityItem] = []

    project_rows = (
        await db.execute(
            select(Project.id, Project.name, Project.created_at)
            .where(Project.tenant_id == current_user.tenant_id, Project.is_deleted.is_(False))
            .order_by(Project.created_at.desc())
            .limit(5)
        )
    ).all()
    for row in project_rows:
        activities.append(
            DashboardActivityItem(
                category="project",
                action="created",
                resource_id=str(row.id),
                resource_name=row.name,
                occurred_at=row.created_at,
            )
        )

    webhook_rows = (
        await db.execute(
            select(Webhook.id, Webhook.url, Webhook.created_at)
            .where(Webhook.tenant_id == current_user.tenant_id)
            .order_by(Webhook.created_at.desc())
            .limit(5)
        )
    ).all()
    for row in webhook_rows:
        activities.append(
            DashboardActivityItem(
                category="webhook",
                action="created",
                resource_id=str(row.id),
                resource_name=row.url,
                occurred_at=row.created_at,
            )
        )

    api_key_rows = (
        await db.execute(
            select(APIKey.id, APIKey.name, APIKey.created_at)
            .where(APIKey.tenant_id == current_user.tenant_id)
            .order_by(APIKey.created_at.desc())
            .limit(5)
        )
    ).all()
    for row in api_key_rows:
        activities.append(
            DashboardActivityItem(
                category="api_key",
                action="created",
                resource_id=str(row.id),
                resource_name=row.name,
                occurred_at=row.created_at,
            )
        )

    activities.sort(key=lambda item: item.occurred_at, reverse=True)
    return DashboardRecentActivityResponse(items=activities[:10])
