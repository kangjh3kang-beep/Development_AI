from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr
from app.core.config import settings
from app.core.database import get_db
from app.core.rbac import require_role, Role
from app.services.auth.auth_service import (
    hash_password, verify_password, create_access_token, create_refresh_token, get_current_user
)
from app.models.auth import User, Organization
from sqlalchemy import select
import uuid

require_admin = require_role(Role.ADMIN)

router = APIRouter(prefix="/api/v1/auth", tags=["인증"])

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    organization_name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 등록된 이메일")
    org = Organization(name=req.organization_name, slug=str(uuid.uuid4())[:8])
    db.add(org)
    await db.flush()
    user = User(organization_id=org.id, email=req.email,
                hashed_password=hash_password(req.password), full_name=req.full_name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)})
    )

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호 오류")
    return TokenResponse(
        access_token=create_access_token({"sub": str(user.id)}),
        refresh_token=create_refresh_token({"sub": str(user.id)})
    )

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    """리프레시 토큰으로 새 액세스 토큰 발급."""
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(req.refresh_token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
        return TokenResponse(
            access_token=create_access_token({"sub": sub}),
            refresh_token=create_refresh_token({"sub": sub}),
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")

# 관리자군 role(관리자 시크릿/설정 메뉴 노출 기준 — admin_secrets._ADMIN_ROLES와 동기화)
_ADMIN_ROLES = {"admin", "manager", "superadmin", "super_admin", "owner", "총괄관리자", "platform_admin"}


class MeResponse(BaseModel):
    """현재 사용자 정보."""
    id: str
    email: str
    full_name: str
    role: str = "viewer"
    is_admin: bool = False


class AdminUserItem(BaseModel):
    """관리자용 사용자 항목."""
    id: str
    email: str
    full_name: str


@router.get("/me", response_model=MeResponse)
async def me(current_user: User = Depends(get_current_user)):
    role = (getattr(current_user, "role", None) or "viewer")
    return {
        "id": str(current_user.id), "email": current_user.email,
        "full_name": getattr(current_user, "full_name", "") or "",
        "role": role,
        "is_admin": role.strip().lower() in {r.lower() for r in _ADMIN_ROLES},
    }

@router.get("/admin/users", response_model=list[AdminUserItem])
async def admin_list_users(
    db: AsyncSession = Depends(get_db),
    _role=Depends(require_admin),
):
    """관리자 전용: 전체 사용자 목록 (RBAC require_role 적용 예시)."""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": str(u.id), "email": u.email, "full_name": u.full_name} for u in users]
