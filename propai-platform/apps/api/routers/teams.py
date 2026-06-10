"""팀(공유 워크스페이스) API — 개인 로그인 + 팀 배정.

보안: 팀 생성=유료 구독자(사업자/구독자)만. 가입=신청→팀장 승인. 팀장만 관리.
멤버는 자기 계정으로 로그인하되 팀 테넌트에 배정돼 팀 자원·quota를 공유한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from app.services.team import team_service
from app.core.billing import is_metered_tier

router = APIRouter(prefix="/api/v1/teams", tags=["팀"])


async def _user_tier(db: AsyncSession, user_id) -> str:
    from sqlalchemy import text
    r = (await db.execute(text("SELECT tier FROM users WHERE id::text=:i"), {"i": str(user_id)})).first()
    return str(r[0]) if r and r[0] else "free"


class CreateTeamReq(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class JoinReq(BaseModel):
    owner_email: EmailStr


class LimitReq(BaseModel):
    user_id: str
    limit_krw: float = 0


@router.get("/mine")
async def my_team(current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """내 팀 상황 — 소유(팀장)/소속(멤버)/미소속 + 멤버 목록(팀장)."""
    await team_service.ensure_schema(db)
    owned = await team_service.get_team_owned(db, current.user_id)
    if owned:
        members = await team_service.list_members(db, owned["id"])
        return {"role": "owner", "team": owned, "members": members}
    # 소속 멤버 여부
    from sqlalchemy import text
    r = (await db.execute(
        text("SELECT t.id, t.name, m.status FROM team_members m JOIN teams t ON t.id=m.team_id "
             "WHERE m.user_id=:u ORDER BY m.requested_at DESC LIMIT 1"),
        {"u": str(current.user_id)},
    )).first()
    if r:
        return {"role": "member", "team": {"id": str(r[0]), "name": r[1]}, "status": r[2]}
    return {"role": "none"}


@router.post("/create")
async def create_team(req: CreateTeamReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """팀 생성 — 유료 구독자(사업자/구독자)만. 본인 테넌트가 팀 공유 테넌트가 된다."""
    tier = await _user_tier(db, current.user_id)
    if not is_metered_tier(tier):
        raise HTTPException(status_code=403, detail="팀 생성은 유료 구독(사업자/구독자)만 가능합니다.")
    team = await team_service.create_team(db, current.user_id, current.tenant_id, req.name)
    return {"ok": True, "team": team}


@router.post("/join")
async def join_team(req: JoinReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """팀장 이메일(ID)로 가입 신청 → 팀장 승인 대기."""
    return await team_service.request_join(db, current.user_id, current.tenant_id, str(req.owner_email))


def _require_owner(team):
    if not team:
        raise HTTPException(status_code=403, detail="팀장만 가능합니다.")


@router.post("/members/{user_id}/approve")
async def approve(user_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    team = await team_service.get_team_owned(db, current.user_id)
    _require_owner(team)
    return await team_service.approve_member(db, team, user_id, current.user_id)


@router.delete("/members/{user_id}")
async def remove(user_id: str, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    team = await team_service.get_team_owned(db, current.user_id)
    _require_owner(team)
    return await team_service.remove_member(db, team, user_id)


@router.put("/members/limit")
async def set_limit(req: LimitReq, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    team = await team_service.get_team_owned(db, current.user_id)
    _require_owner(team)
    return await team_service.set_member_limit(db, team["id"], req.user_id, req.limit_krw)


@router.get("/usage")
async def usage(days: int = 30, current: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """팀장: 멤버별 사용량 모니터링."""
    team = await team_service.get_team_owned(db, current.user_id)
    _require_owner(team)
    return {"team": team, "members": await team_service.member_usage(db, team["id"], days)}
