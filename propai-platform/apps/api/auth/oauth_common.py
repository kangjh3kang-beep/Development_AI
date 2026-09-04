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


# 탈퇴 후 재가입 유예일(확정 정책 §7-1) — services.auth_tokens.REJOIN_GRACE_DAYS와 동일값.
# (순환 import 방지를 위해 상수만 복제하지 않고 지연 import로 단일 출처를 유지한다.)
def _rejoin_grace_days() -> int:
    from apps.api.services.auth_tokens import REJOIN_GRACE_DAYS
    return REJOIN_GRACE_DAYS


def _raise_if_in_rejoin_grace(rows: list[User]) -> None:
    """탈퇴 유예(30일) 중인 계정이면 정직한 안내로 차단. 유예 경과면 통과(재가입 허용)."""
    grace_days = _rejoin_grace_days()
    now = datetime.now(UTC)
    for row in rows:
        deleted_at = row.deleted_at
        if deleted_at is None:
            continue
        if deleted_at.tzinfo is None:
            deleted_at = deleted_at.replace(tzinfo=UTC)
        if now < deleted_at + timedelta(days=grace_days):
            raise OAuthError(
                f"탈퇴한 계정입니다. 탈퇴 후 {grace_days}일이 지나야 다시 가입할 수 있습니다.",
                status_code=403,
            )


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

    # 1. OAuth 매핑 사용자 우선 조회 — 탈퇴(deleted_at) 행 제외.
    #    탈퇴 계정은 소셜 경로로도 로그인 불가(스펙 §5.4). 유예(30일) 중이면 정직 안내,
    #    유예 경과면 매칭에서 제외되어 신규 계정 생성 경로로 진행(재가입 허용 §7-1).
    result = await db.execute(
        select(User).where(
            User.oauth_provider == provider,
            User.oauth_id == provider_id,
        )
    )
    matched_rows = list(result.scalars().all())
    oauth_user = next((u for u in matched_rows if u.deleted_at is None), None)
    if oauth_user is not None:
        if not oauth_user.is_active:
            raise OAuthError("이용이 제한된 계정입니다. 관리자에게 문의해 주세요.", status_code=403)
        return oauth_user
    _raise_if_in_rejoin_grace(matched_rows)

    # 2. 기존 사용자 조회 (이메일 기반) — 동일 이메일이면 기존 계정에 소셜 식별자 연결(병합).
    #    ★계정 탈취 차단: provider가 **검증한 이메일**(email_verified)일 때만 병합한다.
    #    미검증 이메일로의 자동 병합을 허용하면, 공격자가 자신의 소셜 계정에 피해자 이메일을
    #    미검증 상태로 등록해 피해자 계정을 탈취할 수 있다(전형적 OAuth 미검증 이메일 취약점).
    #    탈퇴 행은 병합 대상에서 제외(유예 중이면 정직 안내).
    if profile.get("email"):
        result = await db.execute(
            select(User).where(User.email == profile["email"])
        )
        email_rows = list(result.scalars().all())
        existing = next((u for u in email_rows if u.deleted_at is None), None)
        if existing is not None:
            if not existing.is_active:
                raise OAuthError("이용이 제한된 계정입니다. 관리자에게 문의해 주세요.", status_code=403)
            if not profile.get("email_verified"):
                # 미검증 이메일 → 자동 병합 거부(계정 탈취 방지). 기존 방식 로그인 후 연동 유도.
                logger.warning(
                    "미검증 소셜 이메일의 기존계정 자동병합 차단",
                    provider=provider, provider_id=provider_id,
                )
                raise OAuthError(
                    "이미 가입된 이메일입니다. 기존 방식으로 로그인한 뒤 계정 설정에서 소셜 연동을 진행해 주세요.",
                    status_code=409,
                )
            existing.oauth_provider = provider
            existing.oauth_id = provider_id
            await db.flush()
            return existing
        _raise_if_in_rejoin_grace(email_rows)

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
