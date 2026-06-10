"""Authentication router."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
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
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.tenant import Tenant
from apps.api.database.models.user import User
from apps.api.database.session import get_db

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
UTC = timezone.utc


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
    # 회사명은 선택 — 무구독 일반(개인) 회원도 가입 가능. 비우면 개인 워크스페이스로 생성.
    company_name: str = Field(default="", max_length=200)


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


def _refresh_expires_at(expire_days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=expire_days)


async def _persist_refresh_token(
    db: AsyncSession,
    *,
    refresh_token: str,
    user_id: UUID,
    tenant_id: UUID,
    expire_days: int,
    device_info: str,
) -> None:
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    db.add(
        RefreshToken(
            user_id=user_id,
            tenant_id=tenant_id,
            token_hash=token_hash,
            expires_at=_refresh_expires_at(expire_days),
            device_info=device_info,
        )
    )
    await db.commit()


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Issue JWT credentials for an existing user."""
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
    await _persist_refresh_token(
        db,
        refresh_token=refresh,
        user_id=user.id,
        tenant_id=user.tenant_id,
        expire_days=settings.jwt_refresh_token_expire_days,
        device_info="auth:login",
    )

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

    # 회사명 미입력(개인/무료 일반회원) → 본인 이름 기반 개인 워크스페이스로 생성.
    workspace_name = (body.company_name or "").strip() or f"{body.name}님의 워크스페이스"
    tenant = Tenant(
        name=workspace_name,
        slug=await _build_unique_tenant_slug(db, workspace_name),
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
    await _persist_refresh_token(
        db,
        refresh_token=refresh,
        user_id=user.id,
        tenant_id=user.tenant_id,
        expire_days=settings.jwt_refresh_token_expire_days,
        device_info="auth:register",
    )

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    settings: Settings = Depends(get_settings),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Exchange a refresh token for a fresh access token pair."""
    payload = decode_token(body.refresh_token, settings)
    if payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The supplied token is not a refresh token.",
        )

    # DB에서 토큰 해시를 조회하여 revoke 여부 확인
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored_token = result.scalar_one_or_none()

    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found.",
        )
    if stored_token.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked.",
        )
    expires_at = stored_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        stored_token.is_revoked = True
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired.",
        )

    # 기존 토큰 무효화 (토큰 로테이션)
    stored_token.is_revoked = True

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
    await _persist_refresh_token(
        db,
        refresh_token=refresh,
        user_id=UUID(payload.sub),
        tenant_id=UUID(payload.tenant_id),
        expire_days=settings.jwt_refresh_token_expire_days,
        device_info="auth:refresh",
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
    db: AsyncSession = Depends(get_db),
) -> LogoutResponse:
    """Acknowledge browser logout and revoke the refresh token in DB."""
    payload = decode_token(body.refresh_token, settings)
    if payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The supplied token is not a refresh token.",
        )

    # DB에서 해당 리프레시 토큰을 revoke 처리
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored_token = result.scalar_one_or_none()
    if stored_token is not None:
        stored_token.is_revoked = True
        await db.commit()

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


@router.get("/is-admin")
async def is_admin_check(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """플랫폼 총괄관리자 여부(클라이언트 관리자 메뉴·페이지 가드용).

    ★tier(super_admin)로만 판별 — role은 가입 시 전원 'admin'이라 신뢰 불가.
    """
    from app.services.billing.billing_service import is_super_admin
    return {"is_admin": await is_super_admin(db, current_user.user_id)}


class KakaoCallbackRequest(BaseModel):
    """Request body for Kakao OAuth callback completion."""

    code: str
    redirect_uri: str | None = None


@router.get("/kakao/login-url")
async def kakao_login_url(
    redirect_uri: str | None = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """카카오 인가 페이지 URL을 생성해 반환한다(REST API 키 비노출 — 서버에서 조립).

    프론트 '카카오 로그인' 버튼이 이 URL로 이동하면 카카오 동의→콜백(code)→/kakao/callback 교환.
    redirect_uri 미지정 시 서버 설정값(kakao_redirect_uri) 사용. authorize/callback의 redirect_uri는
    반드시 동일해야 하므로 기본은 서버 설정값으로 통일한다.
    """
    import os
    from urllib.parse import urlencode

    # ★관리자 키화면(secret_store)은 저장 시 os.environ을 즉시 갱신하나, settings는 캐시되어
    #  재시작 전까지 반영 안 됨 → os.environ을 라이브로 우선 읽어 '재배포 불필요'를 보장한다.
    client_id = (os.environ.get("KAKAO_REST_API_KEY") or settings.kakao_client_id or "").strip()
    # 플레이스홀더(your-kakao-key 등)도 '미설정'으로 취급(깨진 인가URL 생성·카카오 거부 방지).
    _PLACEHOLDERS = {"your-kakao-key", "your-kakao-rest-api-key", "changeme", "dummy"}
    if not client_id or client_id.lower() in _PLACEHOLDERS:
        raise HTTPException(status_code=503, detail="카카오 로그인 미설정(KAKAO_REST_API_KEY) — 관리자 키 설정이 필요합니다.")
    ruri = redirect_uri or os.environ.get("KAKAO_REDIRECT_URI") or settings.kakao_redirect_uri
    params = {
        "client_id": client_id,
        "redirect_uri": ruri,
        "response_type": "code",
    }
    url = f"https://kauth.kakao.com/oauth/authorize?{urlencode(params)}"
    return {"url": url, "redirect_uri": ruri}


@router.post("/kakao/callback", response_model=TokenResponse)
async def kakao_callback(
    body: KakaoCallbackRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Exchange a Kakao OAuth code for PropAI JWT credentials."""
    import os
    redirect_uri = body.redirect_uri or os.environ.get("KAKAO_REDIRECT_URI") or settings.kakao_redirect_uri
    try:
        result = await process_kakao_callback(
            code=body.code,
            redirect_uri=redirect_uri,
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


class AdminUserItem(BaseModel):
    """관리자용 사용자 항목."""
    id: str
    email: str
    name: str
    role: str
    tier: str | None = None  # 구독 등급(super_admin/power/free 등)
    is_active: bool
    created_at: str | None = None


class AdminUsersResponse(BaseModel):
    """관리자용 사용자 목록 응답."""
    users: list[AdminUserItem]


@router.get("/admin/users", response_model=AdminUsersResponse)
async def get_admin_users(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자 조회. 총괄관리자(tier=super_admin)는 전체, 테넌트 관리자는 자기 테넌트만."""
    if current_user.role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")

    # ★총괄관리자는 플랫폼 전체 사용자를 본다. 일반(테넌트) 관리자는 자기 테넌트만(격리).
    from app.services.billing.billing_service import is_super_admin
    is_super = await is_super_admin(db, current_user.user_id)
    stmt = select(User) if is_super else select(User).where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "tier": getattr(u, "tier", None),
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ]
    }
