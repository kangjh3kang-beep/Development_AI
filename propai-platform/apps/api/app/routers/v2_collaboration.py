"""SP2 프로젝트 회의방(F3) 협업 API — 멤버 조회 + 외부 협력업체 초대(발급/수락/회수).

접근제어는 require_project_member(멤버십 DB조회, app-level 1차)가 담당. 초대 생성/회수는 owner/
manager만. 수락은 토큰 기반(수락자는 아직 멤버가 아닐 수 있음 → 로그인만 요구). 결정 로직은
collaboration_service, DB I/O는 collaboration_repo로 분리.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_collaboration import require_project_member
from app.core.database import get_db
from app.models.collaboration import PROJECT_ROLES, REVIEW_CATEGORIES
from app.schemas.collaboration import (
    InviteActionResult,
    InviteCreate,
    InviteOut,
    MemberOut,
)
from app.services.auth.auth_service import get_current_user
from app.services.collaboration import collaboration_repo as repo
from app.services.collaboration.collaboration_service import (
    accept_invite_result,
    build_invite_fields,
)

router = APIRouter(prefix="/api/v2/collaboration", tags=["collaboration"])

# 모듈레벨 의존성(테스트가 dependency_overrides로 정확히 대체 가능하도록).
_require_member = require_project_member(*PROJECT_ROLES)        # 활성 멤버 누구나
_require_admin = require_project_member("owner", "manager")     # 초대 발급/회수


def _member_out(m) -> MemberOut:
    return MemberOut(
        id=str(m.id),
        project_id=str(m.project_id),
        user_id=str(m.user_id) if m.user_id is not None else None,
        project_role=m.project_role,
        status=m.status,
        created_at=getattr(m, "created_at", None),
    )


def _invite_out(inv, *, with_token: bool) -> InviteOut:
    return InviteOut(
        id=str(inv.id) if getattr(inv, "id", None) is not None else None,
        project_id=str(inv.project_id),
        email=inv.email,
        project_role=inv.project_role,
        scope_categories=list(inv.scope_categories or []),
        status=inv.status,
        expires_at=inv.expires_at,
        invite_token=inv.invite_token if with_token else None,
    )


@router.get("/projects/{project_id}/members", response_model=list[MemberOut])
async def list_members(
    project_id: str,
    _member=Depends(_require_member),
    db: AsyncSession = Depends(get_db),
):
    """프로젝트 팀 멤버(내부+외부 게스트) 목록 — 활성 멤버만 조회 가능."""
    members = await repo.list_members(db, uuid.UUID(project_id))
    return [_member_out(m) for m in members]


@router.post("/projects/{project_id}/invites", response_model=InviteOut)
async def create_invite(
    project_id: str,
    body: InviteCreate,
    member=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """외부 협력업체(게스트) 초대 발급 — owner/manager만. scope는 6 심의카테고리로 화이트리스트 필터."""
    try:
        fields = build_invite_fields(
            project_id=str(project_id),
            organization_id=str(member.organization_id),
            email=body.email,
            project_role=body.project_role,
            requested_categories=body.scope_categories,
            allowed_categories=list(REVIEW_CATEGORIES),
            invited_by=str(user.id),
            now=datetime.utcnow(),
            token_factory=lambda: secrets.token_urlsafe(32),
            ttl_days=body.ttl_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    inv = await repo.insert_invite(db, fields)
    return _invite_out(inv, with_token=True)  # 생성 직후 1회만 토큰 노출(공유용)


@router.post("/invites/{token}/accept", response_model=InviteActionResult)
async def accept_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """초대 수락 — 토큰 기반(수락자는 로그인만 필요). pending·미만료일 때만 멤버 생성."""
    inv = await repo.get_invite_by_token(db, token)
    if inv is None:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다")
    ok, reason = accept_invite_result(inv.status, inv.expires_at, datetime.utcnow())
    if not ok:
        raise HTTPException(status_code=409, detail=reason)
    await repo.accept_invite_persist(db, inv, user.id, datetime.utcnow())
    return InviteActionResult(ok=True, status="accepted")


@router.post("/projects/{project_id}/invites/{invite_id}/revoke", response_model=InviteActionResult)
async def revoke_invite(
    project_id: str,
    invite_id: str,
    _member=Depends(_require_admin),
    db: AsyncSession = Depends(get_db),
):
    """초대 회수 — owner/manager만. invite revoked + 연결 멤버 removed(소프트)."""
    inv = await repo.get_invite_by_id(db, uuid.UUID(invite_id))
    if inv is None:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없습니다")
    if str(inv.project_id) != str(uuid.UUID(project_id)):
        raise HTTPException(status_code=403, detail="해당 프로젝트의 초대가 아닙니다")
    await repo.revoke_invite_persist(db, inv)
    return InviteActionResult(ok=True, status="revoked")
