"""관리자 전용 — 분양(sales)/모델하우스(mh) RLS 부트스트랩 운영 엔드포인트.

엔드포인트(prefix=/api/v1/admin/sales-rls):
- GET  /status   : sales_/mh_ 테이블 rowsecurity·force·정책수 집계.
- POST /apply    : RLS ENABLE+FORCE + p_site/p_org 멱등 적용(only_table 카나리·dry_run 지원).
- POST /rollback : 전 sales_/mh_ 테이블 RLS DISABLE + 정책 DROP(1콜 롤백).

권한: role ∈ 관리자군(JWT). ★ENABLE+FORCE 적용. 멱등·무파괴.
★실효 전제: 앱 DB 접속 role 이 'BYPASSRLS 아님'이어야 FORCE 가 의미를 가진다
(앱 전용 non-bypassrls role 분리는 인프라 = deploy-pending).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.sales import sales_rls_bootstrap
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

router = APIRouter(prefix="/api/v1/admin/sales-rls", tags=["관리자·분양RLS"])

_ADMIN_ROLES = {"admin", "superadmin", "super_admin", "owner", "총괄관리자", "platform_admin"}


async def _require_admin(current: CurrentUser, db: AsyncSession) -> None:
    # ★tier(super_admin)로만 판별 — 가입 시 모두 role='admin'이라 role 게이트는 누출.
    from app.services.billing.billing_service import is_super_admin
    if not await is_super_admin(db, current.user_id):
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
    await _require_admin(current, db)
    return await sales_rls_bootstrap.rls_status(db)


@router.post("/apply")
async def sales_rls_apply(
    req: ApplyRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """RLS ENABLE+FORCE + p_site/p_org 멱등 적용. only_table(카나리)·dry_run 지원.

    ★권한거부 응답계약 구분 신호: 이 관리자 엔드포인트는 app 계층(_require_admin)에서
    권한 미달 시 403 을 반환한다. 반면 일반 sales 업무 엔드포인트의 '데이터 거부'는
    RLS 정책이 0행(빈 결과)으로 fail-closed 시킨다(403 아님). 즉 403=app계층 권한거부,
    0행=RLS 격리거부 로 신호가 다르다(둘을 혼동하지 말 것).
    """
    await _require_admin(current, db)
    return await sales_rls_bootstrap.ensure_sales_rls(
        db, only_table=req.only_table, dry_run=req.dry_run
    )


@router.post("/rollback")
async def sales_rls_rollback(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """롤백: 전 sales_/mh_ 테이블 RLS DISABLE + 정책 DROP(1콜)."""
    await _require_admin(current, db)
    return await sales_rls_bootstrap.disable_sales_rls(db)
