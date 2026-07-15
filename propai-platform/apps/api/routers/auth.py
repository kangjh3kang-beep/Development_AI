"""Authentication router."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt as _bcrypt
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from packages.schemas.enums import UserRole
from packages.schemas.models import TokenResponse, UserResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.google_handler import GoogleOAuthError, process_google_callback
from apps.api.auth.jwt_handler import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from apps.api.auth.kakao_handler import KakaoOAuthError, process_kakao_callback
from apps.api.auth.naver_handler import NaverOAuthError, process_naver_callback
from apps.api.auth.oauth_common import OAuthError
from apps.api.config import Settings, get_settings
from apps.api.database.models.member_auth import (
    EmailVerificationToken,
    PasswordResetToken,
    UserConsent,
)
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.tenant import Tenant
from apps.api.database.models.user import User
from apps.api.database.session import get_db
from apps.api.services.auth_tokens import (
    REJOIN_GRACE_DAYS,
    RESET_TOKEN_TTL,
    SOCIAL_REAUTH_WINDOW_SECONDS,
    VERIFY_TOKEN_TTL,
    consume_token,
    email_request_limiter,
    issue_token,
    peek_token,
    revoke_all_refresh_tokens,
    validate_password_policy,
)
from apps.api.services.notifications.email_service import (
    render_email_verification,
    render_password_reset_email,
    render_withdrawal_complete,
    send_email,
)

router = APIRouter()
logger = logging.getLogger(__name__)
# passlib 1.7.4는 bcrypt>=4.1과 비호환(백엔드 self-test가 ValueError로 크래시)이라
# bcrypt를 직접 사용한다. 해시 포맷($2b$)은 passlib 산출물과 동일해 기존 해시와 호환.
# bcrypt는 72바이트 초과 입력을 거부하므로 표준 관행대로 절단한다.
def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8")[:72], _bcrypt.gensalt()).decode("ascii")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("ascii"))
    except ValueError:
        # 잘못된 해시 포맷 등 — 인증 실패로 처리
        return False


UTC = UTC

# 계정 열거 방지(스펙 §3.2): 존재하지 않는 계정 경로에서도 bcrypt 1회를 수행해
# 응답시간을 평준화하기 위한 더미 해시. 모듈 로드 시 1회 생성(요청 경로 비용 0).
_TIMING_DUMMY_HASH = _hash_password("propai-timing-equalizer")

# 현재 시행 중인 약관·개인정보처리방침 버전(인앱 /legal 문서 시행일과 일치).
# 동의 이력에는 **서버 상수**를 스탬프한다 — 클라이언트가 보낸 값을 신뢰하면 법적 증빙
# 무결성이 약화되므로, 요청 필드는 호환용으로만 받고 저장은 이 값으로 고정한다.
CURRENT_POLICY_VERSION = "2026-06-15"

# 로그인 실패 통일 메시지(이메일 존재 여부 비노출 — 스펙 §3.2)
_LOGIN_FAILED_MSG = "이메일 또는 비밀번호가 올바르지 않습니다."
# 재설정 링크 검증 실패 통일 메시지(토큰 부재/만료/사용됨 구분 비노출)
_RESET_LINK_INVALID_MSG = "유효하지 않거나 만료된 링크입니다. 재설정을 다시 요청해 주세요."

# 회원 탈퇴 등 민감 작업의 소셜 재인증 확인용 — get_current_user와 동일 토큰을
# 다시 읽어 발급시각(iat)의 최근성(재로그인)을 확인한다.
_reauth_bearer = HTTPBearer(auto_error=False)


def _client_ip(request: Request) -> str:
    """감사 로그·레이트리밋용 클라이언트 IP.

    프로덕션은 nginx 프런트(블루그린) 뒤라 직결 소켓 IP가 프록시 하나로 수렴한다 →
    forgot 레이트리밋(IP당 분당3)이 전역 버킷화되어 복구 경로가 봉쇄되는 것을 막기 위해,
    신뢰 프록시 구성(WS_TRUST_XFF=true)에서는 X-Forwarded-For 첫 홉을 사용한다.
    기본(미신뢰)은 직결 소켓 IP — 직결 노출 서버에서 XFF 스푸핑으로 상한을 우회당하지 않도록.
    (WS 경로와 동일 스위치·동일 헬퍼를 재사용해 운영 설정을 일원화.)
    """
    from apps.api.rate_limit import ws_client_ip

    fallback = request.client.host if request.client else None
    return ws_client_ip(request.headers.get("x-forwarded-for"), fallback)


def _account_blocked_detail(user: User) -> str | None:
    """탈퇴/정지 계정 차단 사유(통상어). None=정상."""
    if user.deleted_at is not None:
        return "탈퇴한 계정입니다."
    if not user.is_active:
        return "이용이 제한된 계정입니다. 관리자에게 문의해 주세요."
    return None


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
    # 정책(스펙 §3.1): 10~128자 + 문자종 3종 이상(validator)
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    # 회사명은 선택 — 무구독 일반(개인) 회원도 가입 가능. 비우면 개인 워크스페이스로 생성.
    company_name: str = Field(default="", max_length=200)
    # ── 약관·개인정보 동의(개인정보보호법 §22 — 필수/선택 분리) ──
    agree_terms: bool = Field(description="이용약관 동의(필수)")
    agree_privacy: bool = Field(description="개인정보처리방침 동의(필수)")
    agree_marketing: bool = Field(default=False, description="마케팅 수신 동의(선택)")
    # 동의한 약관·방침 버전 — 인앱 /legal 문서 시행일과 일치(프론트가 명시 전송)
    policy_version: str = Field(default="2026-06-15", max_length=20)
    phone: str | None = Field(default=None, max_length=32, description="휴대전화(선택)")

    @field_validator("password")
    @classmethod
    def _password_policy(cls, v: str) -> str:
        reason = validate_password_policy(v)
        if reason is not None:
            raise ValueError(reason)
        return v

    @field_validator("agree_terms", "agree_privacy")
    @classmethod
    def _required_consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("필수 약관에 동의해야 가입할 수 있습니다.")
        return v

    @field_validator("phone")
    @classmethod
    def _phone_format(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        cleaned = v.strip()
        if not re.fullmatch(r"\+?[0-9\-\s]{8,31}", cleaned):
            raise ValueError("전화번호 형식이 올바르지 않습니다.")
        return cleaned


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
        # 재가입 정책상 동일 이메일의 탈퇴 행이 병존 가능 → 전 행 조회 후 활성 우선
        result = await db.execute(select(User).where(User.email == body.email))
        rows = list(result.scalars().all())
    except Exception:
        logger.exception("로그인 DB 조회 실패")
        raise HTTPException(status_code=500, detail="로그인 처리 중 오류가 발생했습니다.")

    user = next((u for u in rows if u.deleted_at is None), None)

    if user is None:
        # 탈퇴 계정 로그인 차단(스펙 §5.4). 탈퇴 사실은 **비밀번호 일치(본인 입증) 시에만**
        # 안내(스펙 §6 통상어) — 불일치면 통일 메시지(열거 방지 §3.2).
        withdrawn = next((u for u in rows if u.deleted_at is not None), None)
        # ★타이밍 평준화(열거 방지): 모든 분기에서 정확히 1회 bcrypt를 수행한다. 검증할 실제
        #   해시가 없으면(부재·소셜 전용 계정 등) 더미 해시로 연산해 응답시간을 일정하게 유지.
        verify_hash = (
            withdrawn.hashed_password
            if (withdrawn is not None and withdrawn.hashed_password)
            else _TIMING_DUMMY_HASH
        )
        password_ok = _verify_password(body.password, verify_hash)
        if withdrawn is not None and withdrawn.hashed_password and password_ok:
            logger.info("탈퇴 계정 로그인 시도 차단 user_id=%s", withdrawn.id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="탈퇴한 계정입니다."
            )
        raise HTTPException(status_code=401, detail=_LOGIN_FAILED_MSG)

    try:
        if not _verify_password(body.password, user.hashed_password):
            raise HTTPException(status_code=401, detail=_LOGIN_FAILED_MSG)
    except HTTPException:
        raise
    except Exception:
        logger.exception("로그인 비밀번호 검증 실패")
        raise HTTPException(status_code=500, detail="로그인 처리 중 오류가 발생했습니다.")

    blocked = _account_blocked_detail(user)
    if blocked is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=blocked)

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
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Create a tenant admin account and return JWT credentials."""
    existing_user_result = await db.execute(select(User).where(User.email == body.email))
    existing_rows = list(existing_user_result.scalars().all())
    if any(u.deleted_at is None for u in existing_rows):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 가입된 이메일입니다.",
        )
    # 탈퇴 후 재가입 유예(확정 정책 §7-1): deleted_at + 30일 경과 전이면 거절(정직 안내)
    now = datetime.now(UTC)
    for withdrawn in existing_rows:
        deleted_at = withdrawn.deleted_at
        if deleted_at is not None and deleted_at.tzinfo is None:
            deleted_at = deleted_at.replace(tzinfo=UTC)
        if deleted_at is not None and now < deleted_at + timedelta(days=REJOIN_GRACE_DAYS):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"탈퇴 후 {REJOIN_GRACE_DAYS}일이 지나야 동일 이메일로 재가입할 수 있습니다.",
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
        hashed_password=_hash_password(body.password),
        role=UserRole.ADMIN.value,
        is_active=True,
        phone=body.phone,
    )
    db.add(user)
    await db.flush()

    # 약관·개인정보 동의 이력 저장(개인정보보호법 §22 — 버전·IP·시각. 선택 동의는
    # 거부(False)도 명시 기록해 이후 분쟁 시 선택 사실을 증빙한다)
    client_ip = _client_ip(request)
    for consent_type, agreed in (
        ("terms_of_service", body.agree_terms),
        ("privacy_policy", body.agree_privacy),
        ("marketing", body.agree_marketing),
    ):
        db.add(
            UserConsent(
                user_id=user.id,
                consent_type=consent_type,
                agreed=agreed,
                # 서버 상수 스탬프(클라이언트 임의값 미신뢰 — 법적 증빙 무결성)
                policy_version=CURRENT_POLICY_VERSION,
                ip=client_ip,
            )
        )

    # 이메일 인증 토큰 발급(24h) — 발송은 백그라운드(가입 응답 지연·실패 비전파)
    verify_link: str | None = None
    try:
        raw_verify = await issue_token(
            db, EmailVerificationToken, user.id, VERIFY_TOKEN_TTL, client_ip
        )
        verify_link = f"{settings.frontend_base_url}/ko/verify-email?token={raw_verify}"
    except Exception:
        # 인증 토큰 발급 실패가 가입 자체를 막지 않는다(재발송 엔드포인트 존재) — 정직 로그
        logger.exception("가입 시 이메일 인증 토큰 발급 실패(가입은 계속)")

    await db.commit()
    await db.refresh(user)

    if verify_link is not None:
        subject, html, text = render_email_verification(verify_link)
        background_tasks.add_task(send_email, user.email, subject, html, text, settings)

    logger.info("회원가입 완료 user_id=%s tenant_id=%s ip=%s", user.id, tenant.id, client_ip)

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

    # 탈퇴·정지 계정 차단(스펙 §5.4 — refresh 경로 가드). 차단 시 해당 토큰도 즉시 revoke.
    user_result = await db.execute(select(User).where(User.id == UUID(payload.sub)))
    token_user = user_result.scalar_one_or_none()
    blocked = _account_blocked_detail(token_user) if token_user is not None else "탈퇴한 계정입니다."
    if blocked is not None:
        stored_token.is_revoked = True
        await db.commit()
        logger.info("차단 계정 refresh 시도 거부 user_id=%s (%s)", payload.sub, blocked)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=blocked)

    # 기존 토큰 무효화 (토큰 로테이션)
    stored_token.is_revoked = True

    # ★재발급 role은 구 토큰 payload가 아니라 **DB 최신 role**로 서명한다 — 관리자가 role을
    #   강등해도 회전마다 stale role이 무기한 유지되던 문제 방지(권한 변경 즉시 전파).
    # ★auth_time은 원래 인증 시각을 보존한다(/refresh는 재인증이 아니므로 갱신 금지) —
    #   소셜 계정 탈퇴 등 스텝업 판정이 refresh 반복으로 우회되지 않도록.
    current_role = token_user.role
    preserved_auth_time = payload.auth_time
    access = create_access_token(
        UUID(payload.sub),
        UUID(payload.tenant_id),
        current_role,
        settings,
        auth_time=preserved_auth_time,
    )
    refresh = create_refresh_token(
        UUID(payload.sub),
        UUID(payload.tenant_id),
        current_role,
        settings,
        auth_time=preserved_auth_time,
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
    # 탈퇴·정지 계정 차단(access 토큰 잔존 창 축소 — DB 조회가 이미 있는 경로라 무비용)
    blocked = _account_blocked_detail(user)
    if blocked is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=blocked)

    return UserResponse(
        id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
        email_verified=bool(user.email_verified),
        has_password=bool(user.hashed_password),
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
    except OAuthError as exc:
        # 공용 가드(탈퇴 유예·이용 제한 등) — oauth_common에서 발생
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ── 구글 OAuth ──

_OAUTH_PLACEHOLDERS = {
    "your-client-id", "your-google-client-id", "your-naver-client-id",
    "changeme", "dummy",
}


class GoogleCallbackRequest(BaseModel):
    """Request body for Google OAuth callback completion."""

    code: str
    redirect_uri: str | None = None


@router.get("/google/login-url")
async def google_login_url(
    redirect_uri: str | None = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """구글 인가 페이지 URL을 생성해 반환한다(client_id 서버에서 조립).

    프론트 '구글 로그인' 버튼이 이 URL로 이동 → 구글 동의 → 콜백(code) → /google/callback 교환.
    """
    import os
    from urllib.parse import urlencode

    # ★os.environ 라이브 우선(관리자 키화면 즉시 반영) → settings 폴백.
    client_id = (os.environ.get("GOOGLE_CLIENT_ID") or settings.google_client_id or "").strip()
    if not client_id or client_id.lower() in _OAUTH_PLACEHOLDERS:
        raise HTTPException(status_code=503, detail="구글 로그인 미설정(GOOGLE_CLIENT_ID) — 관리자 키 설정이 필요합니다.")
    ruri = redirect_uri or os.environ.get("GOOGLE_REDIRECT_URI") or settings.google_redirect_uri
    params = {
        "client_id": client_id,
        "redirect_uri": ruri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"url": url, "redirect_uri": ruri}


@router.post("/google/callback", response_model=TokenResponse)
async def google_callback(
    body: GoogleCallbackRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Exchange a Google OAuth code for PropAI JWT credentials."""
    import os
    redirect_uri = body.redirect_uri or os.environ.get("GOOGLE_REDIRECT_URI") or settings.google_redirect_uri
    try:
        result = await process_google_callback(
            code=body.code,
            redirect_uri=redirect_uri,
            db=db,
            settings=settings,
        )
    except GoogleOAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except OAuthError as exc:
        # 공용 가드(탈퇴 유예·이용 제한 등) — oauth_common에서 발생
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ── 네이버 OAuth (state CSRF 필수) ──


class NaverCallbackRequest(BaseModel):
    """Request body for Naver OAuth callback completion."""

    code: str
    state: str
    redirect_uri: str | None = None


@router.get("/naver/login-url")
async def naver_login_url(
    redirect_uri: str | None = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """네이버 인가 페이지 URL을 생성해 반환한다(state CSRF 토큰 생성·반환).

    프론트는 반환된 state를 보관했다가 콜백 시 그대로 /naver/callback에 전달해 위변조를 방지한다.
    """
    import os
    import secrets as _secrets
    from urllib.parse import urlencode

    # ★os.environ 라이브 우선(관리자 키화면 즉시 반영) → settings 폴백.
    client_id = (os.environ.get("NAVER_CLIENT_ID") or settings.naver_client_id or "").strip()
    if not client_id or client_id.lower() in _OAUTH_PLACEHOLDERS:
        raise HTTPException(status_code=503, detail="네이버 로그인 미설정(NAVER_CLIENT_ID) — 관리자 키 설정이 필요합니다.")
    ruri = redirect_uri or os.environ.get("NAVER_REDIRECT_URI") or settings.naver_redirect_uri
    state = _secrets.token_urlsafe(16)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": ruri,
        "state": state,
    }
    url = f"https://nid.naver.com/oauth2.0/authorize?{urlencode(params)}"
    return {"url": url, "redirect_uri": ruri, "state": state}


@router.post("/naver/callback", response_model=TokenResponse)
async def naver_callback(
    body: NaverCallbackRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    """Exchange a Naver OAuth code(+state) for PropAI JWT credentials."""
    import os
    redirect_uri = body.redirect_uri or os.environ.get("NAVER_REDIRECT_URI") or settings.naver_redirect_uri
    try:
        result = await process_naver_callback(
            code=body.code,
            state=body.state,
            redirect_uri=redirect_uri,
            db=db,
            settings=settings,
        )
    except NaverOAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except OAuthError as exc:
        # 공용 가드(탈퇴 유예·이용 제한 등) — oauth_common에서 발생
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return TokenResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ── 회원 계정 수명주기(비밀번호 재설정·변경, 이메일 인증, 탈퇴) — 2026-07 확정 스펙 ──


async def _load_current_active_user(db: AsyncSession, current_user: CurrentUser) -> User:
    """현재 인증 유저의 DB 행을 로드하고 탈퇴·정지 계정을 차단(민감 작업 공용 가드).

    참고: 전역 get_current_user는 JWT 검증만 수행(무 DB — 전 라우터 성능·CI 계약 보존).
    탈퇴 시 refresh 전량 revoke + 전 재발급 경로 차단으로 access 토큰 잔존 노출은
    최대 30분(만료)이며, 민감 엔드포인트는 본 가드로 즉시 차단한다.
    """
    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다.")
    blocked = _account_blocked_detail(user)
    if blocked is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=blocked)
    return user


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


@router.post("/password/forgot", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """비밀번호 재설정 메일 요청(비로그인) — 30분 유효 링크.

    계정 열거 방지(스펙 §3.2): 이메일 존재 여부와 무관하게 **항상 동일한 200 응답**.
    실제 발급·발송은 [활성 + 미탈퇴 + 비밀번호 계정]에만 수행하며, 발송은 백그라운드
    (응답시간 평준화). DB 오류도 응답 계약을 바꾸지 않는다(로그로 정직 관측).
    """
    generic = MessageResponse(message="입력하신 이메일로 재설정 안내를 보냈습니다.")
    ip = _client_ip(request)
    # 남용 방지(스펙 §3.3): IP·이메일별 분당 3회/시간당 10회
    if not email_request_limiter.allow(f"forgot-ip:{ip}") or not email_request_limiter.allow(
        f"forgot-email:{body.email.lower()}"
    ):
        raise HTTPException(status_code=429, detail="요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.")

    try:
        result = await db.execute(
            select(User).where(User.email == body.email, User.deleted_at.is_(None))
        )
        user = result.scalars().first()
        # 소셜 전용 계정(hashed_password="")은 재설정 대상이 아님(§7-4) — 동일 응답
        if user is not None and user.is_active and user.hashed_password:
            raw = await issue_token(db, PasswordResetToken, user.id, RESET_TOKEN_TTL, ip)
            await db.commit()
            reset_link = f"{settings.frontend_base_url}/ko/reset-password?token={raw}"
            subject, html, text = render_password_reset_email(
                reset_link, valid_minutes=int(RESET_TOKEN_TTL.total_seconds() // 60)
            )
            background_tasks.add_task(send_email, user.email, subject, html, text, settings)
            logger.info("비밀번호 재설정 요청 접수 user_id=%s ip=%s", user.id, ip)
        else:
            # 대상 없음/비활성/소셜 — 더미 해시로 타이밍 평준화 후 동일 응답
            _verify_password("timing-equalizer", _TIMING_DUMMY_HASH)
            logger.info("비밀번호 재설정 요청 — 발송 대상 아님(응답 동일) ip=%s", ip)
    except HTTPException:
        raise
    except Exception:
        # 인프라 오류도 열거방지 계약상 동일 200 — 침묵이 아니라 예외 스택을 로그로 남긴다
        logger.exception("비밀번호 재설정 요청 처리 실패(응답은 계약상 동일 200)")
    return generic


@router.get("/password/reset/validate")
async def validate_reset_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """재설정 링크 유효성 사전 확인(소모하지 않음 — 페이지 진입용).

    부재/만료/사용됨을 구분하지 않는다(열거 방지). 오류 시에도 valid=false(로그 관측).
    """
    try:
        return {"valid": await peek_token(db, PasswordResetToken, token)}
    except Exception:
        logger.exception("재설정 토큰 사전확인 실패(valid=false 반환)")
        return {"valid": False}


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password_policy(cls, v: str) -> str:
        reason = validate_password_policy(v)
        if reason is not None:
            raise ValueError(reason)
        return v


@router.post("/password/reset", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """재설정 링크로 새 비밀번호 설정(30분·1회용) → 전 기기 로그아웃."""
    user_id = await consume_token(db, PasswordResetToken, body.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail=_RESET_LINK_INVALID_MSG)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or _account_blocked_detail(user) is not None:
        # 토큰 발급 후 탈퇴/정지된 계정 — 사유 구분 비노출(통일 메시지) + 로그 관측
        logger.info("재설정 거부: 차단/부재 계정 user_id=%s", user_id)
        raise HTTPException(status_code=400, detail=_RESET_LINK_INVALID_MSG)

    user.hashed_password = _hash_password(body.new_password)
    user.password_changed_at = datetime.now(UTC)
    revoked = await revoke_all_refresh_tokens(db, user.id)
    await db.commit()
    logger.info("비밀번호 재설정 완료 user_id=%s refresh_revoked=%d", user.id, revoked)
    return MessageResponse(message="비밀번호가 변경되었습니다. 새 비밀번호로 로그인해 주세요.")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _password_policy(cls, v: str) -> str:
        reason = validate_password_policy(v)
        if reason is not None:
            raise ValueError(reason)
        return v


@router.post("/password/change", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """로그인 상태에서 비밀번호 변경(현재 비밀번호 확인) → 전 기기 로그아웃."""
    user = await _load_current_active_user(db, current_user)
    if not user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="소셜 로그인 계정은 비밀번호가 없습니다. 소셜 계정으로 로그인해 주세요.",
        )
    if not _verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="현재 비밀번호가 올바르지 않습니다.")
    if _verify_password(body.new_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="현재와 다른 비밀번호를 사용해 주세요.")

    user.hashed_password = _hash_password(body.new_password)
    user.password_changed_at = datetime.now(UTC)
    revoked = await revoke_all_refresh_tokens(db, user.id)
    await db.commit()
    logger.info("비밀번호 변경 완료 user_id=%s refresh_revoked=%d", user.id, revoked)
    return MessageResponse(
        message="비밀번호가 변경되었습니다. 보안을 위해 전 기기에서 로그아웃되었습니다."
    )


# ── 이메일 인증 ──


@router.post("/email/verify/request", response_model=MessageResponse)
async def request_email_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    """이메일 인증 메일 (재)발송 — 24시간 유효 링크. 레이트리밋 적용."""
    if not email_request_limiter.allow(f"verify:{current_user.user_id}"):
        raise HTTPException(status_code=429, detail="요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.")
    user = await _load_current_active_user(db, current_user)
    if user.email_verified:
        return MessageResponse(message="이미 인증이 완료된 이메일입니다.")

    ip = _client_ip(request)
    raw = await issue_token(db, EmailVerificationToken, user.id, VERIFY_TOKEN_TTL, ip)
    await db.commit()
    verify_link = f"{settings.frontend_base_url}/ko/verify-email?token={raw}"
    subject, html, text = render_email_verification(
        verify_link, valid_hours=int(VERIFY_TOKEN_TTL.total_seconds() // 3600)
    )
    background_tasks.add_task(send_email, user.email, subject, html, text, settings)
    logger.info("이메일 인증 메일 발송 요청 user_id=%s ip=%s", user.id, ip)
    return MessageResponse(message="인증 메일 발송을 요청했습니다. 메일함을 확인해 주세요.")


class VerifyEmailConfirmRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)


@router.post("/email/verify/confirm", response_model=MessageResponse)
async def confirm_email_verification(
    body: VerifyEmailConfirmRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """이메일 인증 링크 확인(24시간·1회용)."""
    user_id = await consume_token(db, EmailVerificationToken, body.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail=_RESET_LINK_INVALID_MSG)
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or _account_blocked_detail(user) is not None:
        logger.info("이메일 인증 거부: 차단/부재 계정 user_id=%s", user_id)
        raise HTTPException(status_code=400, detail=_RESET_LINK_INVALID_MSG)
    user.email_verified = True
    user.email_verified_at = datetime.now(UTC)
    await db.commit()
    logger.info("이메일 인증 완료 user_id=%s", user.id)
    return MessageResponse(message="이메일 인증이 완료되었습니다.")


# ── 회원탈퇴 ──


class WithdrawRequest(BaseModel):
    password: str | None = Field(default=None, max_length=128, description="비밀번호 계정 본인확인")
    reason: str | None = Field(default=None, max_length=500, description="탈퇴 사유(선택)")
    transfer_to_user_id: UUID | None = Field(
        default=None, description="조직 소유권 이관 대상(조직에 다른 이용자가 있을 때)"
    )


@router.post("/account/withdraw", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_account(
    body: WithdrawRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials | None = Depends(_reauth_bearer),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    """회원탈퇴(소프트 삭제) — 즉시 로그인 차단 + 전 기기 로그아웃(확정 정책 §7-2).

    본인확인: 비밀번호 계정=비밀번호 재확인 / 소셜 전용 계정=최근 재로그인
    (액세스 토큰 발급시각이 재인증 창 이내 — §7-4).
    조직 처리(§7-5): 다른 이용자가 있는 조직의 유일 관리자는 이관 후 탈퇴,
    1인 워크스페이스는 테넌트 비활성화.
    """
    user = await _load_current_active_user(db, current_user)

    # ── 본인확인 ──
    if user.hashed_password:
        if not body.password:
            raise HTTPException(status_code=400, detail="본인 확인을 위해 비밀번호를 입력해 주세요.")
        if not _verify_password(body.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    else:
        # 소셜 전용 계정 — 최근 재로그인(재인증) 확인(§7-4).
        # ★iat가 아니라 auth_time(실제 인증 시각)을 검사한다. iat는 /refresh로 갱신되므로
        #   refresh 토큰만 있으면 재로그인 없이 우회 가능하지만, auth_time은 refresh가 보존해
        #   실제 소셜 재로그인 없이는 신선해지지 않는다(스텝업 무결성).
        payload = decode_token(credentials.credentials, settings) if credentials else None
        authenticated_at = payload.auth_time if payload is not None else None
        if authenticated_at is not None and authenticated_at.tzinfo is None:
            authenticated_at = authenticated_at.replace(tzinfo=UTC)
        if authenticated_at is None or (
            (datetime.now(UTC) - authenticated_at).total_seconds() > SOCIAL_REAUTH_WINDOW_SECONDS
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인 확인을 위해 소셜 계정으로 다시 로그인한 뒤 탈퇴를 진행해 주세요.",
            )

    # ── 조직(테넌트) 처리 — §7-5 ──
    others_result = await db.execute(
        select(User).where(
            User.tenant_id == user.tenant_id,
            User.id != user.id,
            User.deleted_at.is_(None),
        )
    )
    others = list(others_result.scalars().all())
    if others:
        other_admins = [u for u in others if u.role == UserRole.ADMIN.value and u.is_active]
        if user.role == UserRole.ADMIN.value and not other_admins:
            # 이관 대상은 활성(미정지) 구성원만 허용 — 정지 계정을 관리자로 승격해
            # 정지를 우회하는 것을 방지한다.
            transfer_target = next(
                (
                    u for u in others
                    if body.transfer_to_user_id
                    and u.id == body.transfer_to_user_id
                    and u.is_active
                ),
                None,
            )
            if transfer_target is None:
                # 통상어 안내 — 원시 API 필드명을 사용자에게 노출하지 않는다.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "조직에 다른 구성원이 있어 바로 탈퇴할 수 없습니다. "
                        "관리자 권한을 넘겨받을 구성원을 지정한 뒤 다시 시도해 주세요. "
                        "구성원 지정이 어려우면 고객센터(k3880@kakao.com)로 문의해 주세요."
                    ),
                )
            transfer_target.role = UserRole.ADMIN.value
            logger.info(
                "탈퇴 전 조직 소유권 이관 tenant_id=%s %s→%s",
                user.tenant_id, user.id, transfer_target.id,
            )
    else:
        # 1인 워크스페이스 — 테넌트 비활성화(데이터는 파기정책 §7-2 준용)
        tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is not None:
            tenant.is_active = False

    # ── 소프트 삭제 + 세션 전량 무효화 ──
    user.deleted_at = datetime.now(UTC)
    user.is_active = False
    user.withdrawn_reason = (body.reason or "").strip()[:500] or None
    revoked = await revoke_all_refresh_tokens(db, user.id)
    withdrawn_email, withdrawn_name = user.email, user.name
    await db.commit()

    subject, html, text = render_withdrawal_complete(withdrawn_name)
    background_tasks.add_task(send_email, withdrawn_email, subject, html, text, settings)
    logger.info(
        "회원탈퇴 완료 user_id=%s tenant_id=%s refresh_revoked=%d ip=%s",
        user.id, user.tenant_id, revoked, _client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
