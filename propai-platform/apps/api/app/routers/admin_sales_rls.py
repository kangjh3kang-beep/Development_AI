"""관리자 전용 — 분양(sales)/모델하우스(mh) RLS 부트스트랩 운영 엔드포인트.

엔드포인트(prefix=/api/v1/admin/sales-rls):
- GET  /status   : sales_/mh_ 테이블 rowsecurity·정책수 집계.
- POST /apply    : RLS ENABLE + p_site/p_org 멱등 적용(only_table 카나리·dry_run 지원).
- POST /rollback : 전 sales_/mh_ 테이블 RLS DISABLE + 정책 DROP(1콜 롤백).

권한: role ∈ 관리자군(JWT). ★FORCE 미적용. 멱등·무파괴.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales import sales_rls_bootstrap

router = APIRouter(prefix="/api/v1/admin/sales-rls", tags=["관리자·분양RLS"])

_ADMIN_ROLES = {"admin", "superadmin", "super_admin", "owner", "총괄관리자", "platform_admin"}


def _require_admin(current: CurrentUser) -> None:
    if (current.role or "").strip().lower() not in {r.lower() for r in _ADMIN_ROLES}:
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")


class ApplyRequest(BaseModel):
    only_table: str | None = None
    dry_run: bool = False


@router.get("/status")
async def sales_rls_status(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """sales_/mh_ 테이블별 RLS 활성화·정책수 집계."""
    _require_admin(current)
    return await sales_rls_bootstrap.rls_status(db)


@router.post("/apply")
async def sales_rls_apply(
    req: ApplyRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RLS ENABLE + p_site/p_org 멱등 적용. only_table(카나리)·dry_run 지원."""
    _require_admin(current)
    return await sales_rls_bootstrap.ensure_sales_rls(
        db, only_table=req.only_table, dry_run=req.dry_run
    )


@router.post("/rollback")
async def sales_rls_rollback(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """롤백: 전 sales_/mh_ 테이블 RLS DISABLE + 정책 DROP(1콜)."""
    _require_admin(current)
    return await sales_rls_bootstrap.disable_sales_rls(db)
