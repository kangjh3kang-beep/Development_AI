"""Authentication router."""

from __future__ import annotations

from datetime import datetime, timezone
UTC = timezone.utc
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.enums import UserRole
from packages.schemas.models import TokenResponse, UserResponse
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from apps.api.auth.kakao_handler import KakaoOAuthError, process_kakao_callback
from apps.api.config import Settings, get_settings
from apps.api.database.models.tenant import Tenant
from apps.api.database.models.user import User
from apps.api.database.session import get_db

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class LogoutResponse(BaseModel):
    success: bool
    message: str
    logged_out_at: datetime


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    company_name: str = Field(min_length=1, max_length=200)


def _slugify_tenant_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        return "tenant"
    return slug[:84].strip("-") or "tenant"


async def _build_unique_tenant_slug(db: AsyncSession, base_value: str) -> str:
    base_slug = _slugify_tenant_name(base_value)
    candidate = base_slug
    suffix = 2

    while True:
        result = await db.execute(select(Tenant).where(Tenant.slug == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        candidate = f"{base_slug[:80]}-{suffix}"
        suffix += 1


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Issue JWT credentials for an existing user."""
    import traceback
    try:
        result = await db.execute(select(User).where(User.email == body.email))
        user = result.scalar_one_or_none()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 쿼리 오류: {str(e)[:200]}")

    if user is None:
        raise HTTPException(status_code=401, detail="등록되지 않은 이메일입니다.")

    try:
        if not pwd_context.verify(body.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="비밀번호가 일치하지 않습니다.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"비밀번호 검증 오류: {str(e)[:200]}")

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The account is inactive.",
        )

    access = create_access_token(user.id, user.tenant_id, user.role, settings)
    refresh = create_refresh_token(user.id, user.tenant_id, user.role, settings)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Create a tenant admin account and return JWT credentials."""
    existing_user_result = await db.execute(select(User).where(User.email == body.email))
    if existing_user_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with that email already exists.",
        )

    tenant = Tenant(
        name=body.company_name,
        slug=await _build_unique_tenant_slug(db, body.company_name),
        plan="free",
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        name=body.name,
        hashed_password=pwd_context.hash(body.password),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access = create_access_token(user.id, user.tenant_id, user.role, settings)
    refresh = create_refresh_token(user.id, user.tenant_id, user.role, settings)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Exchange a refresh token for a fresh access token pair."""
    payload = decode_token(body.refresh_token, settings)
    if payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The supplied token is not a refresh token.",
        )

    access = create_access_token(
        UUID(payload.sub),
        UUID(payload.tenant_id),
        payload.role,
        settings,
    )
    refresh = create_refresh_token(
        UUID(payload.sub),
        UUID(payload.tenant_id),
        payload.role,
        settings,
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    body: LogoutRequest,
    settings: Settings = Depends(get_settings),
) -> LogoutResponse:
    """Acknowledge browser logout and validate the supplied refresh token shape."""
    payload = decode_token(body.refresh_token, settings)
    if payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The supplied token is not a refresh token.",
        )

    return LogoutResponse(
        success=True,
        message="Logout completed.",
        logged_out_at=datetime.now(UTC),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Return the current authenticated user profile."""
    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The authenticated user could not be found.",
        )

    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
    )


class KakaoCallbackRequest(BaseModel):
    """Request body for Kakao OAuth callback completion."""

    code: str
    redirect_uri: str | None = None
    tenant_id: UUID


@router.post("/kakao/callback", response_model=TokenResponse)
async def kakao_callback(
    body: KakaoCallbackRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Exchange a Kakao OAuth code for PropAI JWT credentials."""
    redirect_uri = body.redirect_uri or settings.kakao_redirect_uri
    try:
        result = await process_kakao_callback(
            code=body.code,
            redirect_uri=redirect_uri,
            tenant_id=body.tenant_id,
            db=db,
            settings=settings,
        )
    except KakaoOAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        ) from exc

    return TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ── 관리자 전용 엔드포인트 ──


@router.get("/admin/users")
async def get_admin_users(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자용: 테넌트의 모든 사용자 조회."""
    if current_user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")

    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id)
    )
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    }
