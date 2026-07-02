"""팀(공유 워크스페이스) API v2 — 다중 팀, 개인 로그인 + 팀 배정.

보안: 팀 생성=유료 구독자. 팀장만 자기 팀 관리(초대·승인·제거·한도·삭제).
팀원 추가 2경로 — ①팀장 초대(invited)→멤버 동의(accept) ②멤버 신청(pending)→팀장 승인.
강제 추가 불가(초대는 멤버 동의 필수).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.billing import is_metered_tier
from app.services.team import team_service
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

router = APIRouter(prefix="/api/v1/teams", tags=["팀"])


async def _user_tier(db: AsyncSession, user_id) -> str:
    from sqlalchemy import text
    r = (await db.execute(text("SELECT tier FROM users WHERE id::text=:i"), {"i": str(user_id)})).first()
    return str(r[0]) if r and r[0] else "free"


class CreateTeamReq(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class JoinReq(BaseModel):
    owner_email: EmailStr


class InviteReq(BaseModel):
    email: EmailStr


class LimitReq(BaseModel):
    user_id: str
    limit_krw: float = 0


async def _owner_team_or_403(db: AsyncSession, team_id: str, user_id) -> dict:
    team = await team_service.is_team_owner(db, team_id, user_id)
    if not team:
        raise HTTPException(status_code=403, detail="해당 팀의 팀장만 가능합니다.")
    return team


@router.get("/mine")
async def my_teams(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """내 팀 현황 — 소유 팀 목록(+멤버) + 내 소속/초대/신청."""
    await team_service.ensure_schema(db)
    owned = await team_service.list_owned_teams(db, current.user_id)
    teams_with_members = []
    for t in owned:
        teams_with_members.append({**t, "members": await team_service.list_members(db, t["id"])})
    memberships = await team_service.my_memberships(db, current.user_id)
    tier = await _user_tier(db, current.user_id)
    return {
        "can_create": is_metered_tier(tier),
        "owned": teams_with_members,
        "memberships": memberships,  # 내가 멤버/초대/신청한 팀들
    }


@router.post("/create")
async def create_team(
    req: CreateTeamReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """팀 생성(다중 가능) — 유료 구독자만. 팀별 전용 테넌트 생성."""
    tier = await _user_tier(db, current.user_id)
    if not is_metered_tier(tier):
        raise HTTPException(status_code=403, detail="팀 생성은 유료 구독(사업자/구독자)만 가능합니다.")
    team = await team_service.create_team(db, current.user_id, current.tenant_id, req.name)
    return {"ok": True, "team": team}


@router.delete("/{team_id}")
async def delete_team(
    team_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """팀 삭제(팀장만) — 멤버 개인 테넌트 복원 후 제거."""
    team = await _owner_team_or_403(db, team_id, current.user_id)
    return await team_service.delete_team(db, team, current.user_id)


@router.post("/{team_id}/invite")
async def invite(
    team_id: str, req: InviteReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """팀장이 ID(이메일)로 초대 → 멤버 동의(accept) 대기."""
    team = await _owner_team_or_403(db, team_id, current.user_id)
    return await team_service.invite_member(db, team, str(req.email))


@router.post("/join")
async def join(req: JoinReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """멤버가 팀장 ID(이메일)로 가입 신청 → 팀장 승인 대기."""
    return await team_service.request_join(db, current.user_id, current.tenant_id, str(req.owner_email))


@router.post("/{team_id}/accept")
async def accept(team_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """멤버가 초대 동의 → 팀 합류."""
    return await team_service.accept_invite(db, current.user_id, team_id)


@router.post("/{team_id}/decline")
async def decline(team_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await team_service.decline_invite(db, current.user_id, team_id)


@router.post("/{team_id}/members/{user_id}/approve")
async def approve(
    team_id: str, user_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    team = await _owner_team_or_403(db, team_id, current.user_id)
    return await team_service.approve_member(db, team, user_id, current.user_id)


@router.delete("/{team_id}/members/{user_id}")
async def remove(
    team_id: str, user_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    team = await _owner_team_or_403(db, team_id, current.user_id)
    return await team_service.remove_member(db, team, user_id)


@router.put("/{team_id}/members/limit")
async def set_limit(
    team_id: str, req: LimitReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await _owner_team_or_403(db, team_id, current.user_id)
    return await team_service.set_member_limit(db, team_id, req.user_id, req.limit_krw)


@router.get("/{team_id}/usage")
async def usage(
    team_id: str, days: int = 30, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    await _owner_team_or_403(db, team_id, current.user_id)
    return {"members": await team_service.member_usage(db, team_id, days)}
