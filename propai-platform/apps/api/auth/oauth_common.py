"""소셜 로그인(OAuth) 공용 로직 — 카카오·구글·네이버 공통.

제공자(provider)에 무관하게 다음을 공용으로 처리한다.
1. 프로필(provider_id/email/nickname)로 사용자 조회/생성 (oauth_provider+oauth_id 매핑, 이메일 병합)
2. 신규 사용자용 개인 테넌트 자동 생성 (slug 유일화)
3. JWT 액세스/리프레시 토큰 발급 + 리프레시 토큰 DB 저장

★신규 소셜가입 기본값: 일반 이메일 가입(`/register`)과 동일하게 role='admin'(개인 테넌트 owner 의미),
  plan='free'. (/register는 tier 컬럼을 설정하지 않으므로 여기서도 설정하지 않는다 — 정합 유지.)
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import create_access_token, create_refresh_token
from apps.api.config import Settings
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.tenant import Tenant
from apps.api.database.models.user import User

logger = structlog.get_logger(__name__)
UTC = UTC

# ★신규 소셜가입 기본 role — 일반 이메일 가입(/register)과 동일하게 통일.
#   /register는 UserRole.ADMIN.value('admin')을 부여하므로 소셜도 동일하게 맞춘다.
_DEFAULT_SOCIAL_ROLE = "admin"


class OAuthError(Exception):
    """소셜 OAuth 처리 중 발생하는 공용 예외."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


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


async def get_or_create_oauth_user(
    db: AsyncSession,
    provider: str,
    profile: dict,
) -> User:
    """소셜 프로필로 사용자를 조회하거나 새로 생성한다(제공자 무관 공용).

    Args:
        provider: 소셜 제공자 ("kakao" | "google" | "naver")
        profile: {"provider_id": str, "email": str|None, "nickname": str}

    동작:
    - oauth_provider + oauth_id(=provider_id) 기반 매핑 사용자 우선 조회
    - email 기반 기존 계정 매칭 시 해당 계정에 소셜 식별자 연결(병합)
    - 신규 사용자는 개인 테넌트를 자동 생성(plan=free, role=admin)
    """
    provider_id = profile["provider_id"]
    nickname = profile.get("nickname") or f"{provider}_{provider_id}"

    # 1. OAuth 매핑 사용자 우선 조회
    result = await db.execute(
        select(User).where(
            User.oauth_provider == provider,
            User.oauth_id == provider_id,
        )
    )
    oauth_user = result.scalar_one_or_none()
    if oauth_user is not None:
        return oauth_user

    # 2. 기존 사용자 조회 (이메일 기반) — 동일 이메일이면 기존 계정에 소셜 식별자 연결(병합)
    if profile.get("email"):
        result = await db.execute(
            select(User).where(User.email == profile["email"])
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.oauth_provider = provider
            existing.oauth_id = provider_id
            await db.flush()
            return existing

    # 3. 신규 사용자용 개인 테넌트 생성
    tenant_name = f"{nickname} 워크스페이스"
    tenant = Tenant(
        name=tenant_name,
        slug=await _build_unique_tenant_slug(db, tenant_name),
        plan="free",
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    # 4. 신규 사용자 생성 — role/plan은 일반 이메일 가입(/register)과 동일하게 통일.
    new_user = User(
        tenant_id=tenant.id,
        email=profile.get("email") or f"{provider}_{provider_id}@propai.local",
        name=nickname,
        hashed_password="",  # 소셜 로그인이므로 비밀번호 없음
        role=_DEFAULT_SOCIAL_ROLE,
        is_active=True,
        oauth_provider=provider,
        oauth_id=provider_id,
    )
    db.add(new_user)
    await db.flush()
    return new_user


async def finalize_oauth_login(
    db: AsyncSession,
    user: User,
    settings: Settings,
    *,
    provider: str,
    provider_id: str,
) -> dict:
    """JWT 발급 + 리프레시 토큰 DB 저장 → 표준 토큰 응답을 반환한다(제공자 무관 공용).

    Returns:
        {"access_token", "refresh_token", "token_type", "user"}
    """
    access = create_access_token(user.id, user.tenant_id, user.role, settings)
    refresh = create_refresh_token(user.id, user.tenant_id, user.role, settings)

    token_hash = hashlib.sha256(refresh.encode()).hexdigest()
    db_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        device_info=f"{provider}_oauth:{provider_id}",
    )
    db.add(db_token)
    await db.commit()

    logger.info("소셜 로그인 성공", provider=provider, user_id=str(user.id), provider_id=provider_id)

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
        },
    }
