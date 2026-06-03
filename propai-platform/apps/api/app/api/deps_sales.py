"""v62 sales — 테넌트/현장(site)/조직(ltree)/역할 컨텍스트 + RLS 세션변수 주입.

현장 격리는 1차로 app 계층(SalesCtx.site_id 필터)에서 강제하고,
set_config('app.site_id'|'app.org_path'|'app.role') 도 함께 주입해 RLS 활성화 시 즉시 적용되게 한다.
(RLS ENABLE 자체는 통합검증 후 별도 단계에서 적용)
"""

import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from apps.api.database.models.sales.site_org import SalesSite, SalesOrgNode

# 플랫폼 User.role → sales 역할 매핑(조직노드 없을 때 폴백)
_SUPERADMIN_ROLES = {"superadmin", "super_admin", "admin", "owner", "총괄관리자", "platform_admin"}
_DEVELOPER_ROLES = {"developer", "시행사", "dev"}


class SalesCtx:
    def __init__(self, site_id, org_path, role, user):
        self.site_id = site_id
        self.org_path = org_path
        self.role = role
        self.user = user


async def resolve_site(request: Request, db: AsyncSession) -> uuid.UUID:
    """우선순위: 경로변수 site_id → 헤더 X-Site-Code → 서브도메인(host). site_code 또는 UUID 허용."""
    site_code = request.path_params.get("site_id") or request.headers.get("x-site-code")
    if not site_code:
        host = request.headers.get("host", "")
        if ".sales." in host or ".desk." in host:
            site_code = host.split(".")[0]
    if not site_code:
        raise HTTPException(400, "site context missing (X-Site-Code 헤더 또는 경로 site_id 필요)")

    # UUID 우선 시도, 실패 시 site_code 로 조회
    try:
        site = (await db.execute(select(SalesSite).where(SalesSite.id == uuid.UUID(str(site_code))))).scalar_one_or_none()
    except (ValueError, TypeError):
        site = None
    if site is None:
        site = (await db.execute(select(SalesSite).where(SalesSite.site_code == str(site_code)))).scalar_one_or_none()
    if not site:
        raise HTTPException(404, "site not found")
    return site.id


async def sales_ctx(request: Request, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)) -> SalesCtx:
    site_id = await resolve_site(request, db)
    node = (await db.execute(
        select(SalesOrgNode).where(
            SalesOrgNode.site_id == site_id,
            SalesOrgNode.user_id == user.id,
            SalesOrgNode.active.is_(True),
        )
    )).scalar_one_or_none()

    role_lower = (getattr(user, "role", "") or "").lower()
    if node:
        org_path, role = str(node.path), node.node_type
    elif role_lower in _SUPERADMIN_ROLES:
        org_path, role = "", "SUPERADMIN"
    elif role_lower in _DEVELOPER_ROLES:
        org_path, role = "", "DEVELOPER"
    else:
        raise HTTPException(403, "이 현장에 대한 분양(sales) 권한이 없습니다")

    # RLS 세션변수 주입(트랜잭션 로컬) — 활성화 시 즉시 적용
    await db.execute(text("SELECT set_config('app.site_id', :s, true)"), {"s": str(site_id)})
    await db.execute(text("SELECT set_config('app.org_path', :p, true)"), {"p": org_path or "none"})
    await db.execute(text("SELECT set_config('app.role', :r, true)"), {"r": role})
    return SalesCtx(site_id, org_path, role, user)


def require_role(*allowed):
    async def _dep(ctx: SalesCtx = Depends(sales_ctx)):
        if ctx.role not in allowed and ctx.role != "SUPERADMIN":
            raise HTTPException(403, f"role {ctx.role} not permitted")
        return ctx
    return _dep
