"""카카오 OAuth 2.0 핸들러.

카카오 REST API를 이용한 소셜 로그인 흐름:
1. 인가 코드 수신 → 토큰 교환
2. 토큰으로 사용자 정보 조회
3. DB 사용자 조회 또는 자동 생성
4. JWT 액세스/리프레시 토큰 발급
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import create_access_token, create_refresh_token
from apps.api.config import Settings
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.tenant import Tenant
from apps.api.database.models.user import User

logger = structlog.get_logger(__name__)
UTC = timezone.utc

KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USER_INFO_URL = "https://kapi.kakao.com/v2/user/me"


class KakaoOAuthError(Exception):
    """카카오 OAuth 처리 중 발생하는 예외."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def exchange_code_for_token(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str | None = None,
) -> dict:
    """인가 코드를 카카오 액세스 토큰으로 교환한다.

    Args:
        code: 카카오 인가 코드
        redirect_uri: 리다이렉트 URI
        client_id: 카카오 앱 REST API 키
        client_secret: 카카오 앱 시크릿 (선택)

    Returns:
        카카오 토큰 응답 (access_token, refresh_token 등)
    """
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(KAKAO_TOKEN_URL, data=payload)

    if resp.status_code != 200:
        logger.warning("카카오 토큰 교환 실패", status=resp.status_code, body=resp.text)
        raise KakaoOAuthError(
            f"카카오 토큰 교환 실패: {resp.status_code}",
            status_code=resp.status_code,
        )

    return dict(resp.json())


async def fetch_kakao_user_info(access_token: str) -> dict:
    """카카오 액세스 토큰으로 사용자 정보를 조회한다.

    Returns:
        카카오 사용자 프로필 (id, kakao_account.email, properties.nickname 등)
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(KAKAO_USER_INFO_URL, headers=headers)

    if resp.status_code != 200:
        # ★카카오가 주는 정확한 에러코드(body의 code/msg)를 남겨야 원인 확정 가능
        #  (예: code -401=토큰무효, code -2=파라미터, 동의항목/스코프 문제 등).
        logger.warning(
            "카카오 사용자 정보 조회 실패",
            status=resp.status_code,
            body=resp.text[:500],
        )
        raise KakaoOAuthError(
            f"카카오 사용자 정보 조회 실패: {resp.status_code}",
            status_code=resp.status_code,
        )

    return dict(resp.json())


def extract_user_profile(kakao_data: dict) -> dict:
    """카카오 응답에서 사용자 프로필을 추출한다.

    Returns:
        {"kakao_id": str, "email": str|None, "nickname": str}
    """
    kakao_id = str(kakao_data.get("id", ""))
    account = kakao_data.get("kakao_account", {})
    properties = kakao_data.get("properties", {})

    email = account.get("email")
    nickname = properties.get("nickname", account.get("profile", {}).get("nickname", ""))

    return {
        "kakao_id": kakao_id,
        "email": email,
        "nickname": nickname or f"kakao_{kakao_id}",
    }


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


async def get_or_create_user(
    db: AsyncSession,
    profile: dict,
) -> User:
    """카카오 프로필로 사용자를 조회하거나 새로 생성한다.

    - kakao_id 기반 매칭 (oauth_provider + oauth_id)
    - email 기반 기존 계정 매칭
    - 신규 사용자는 개인 테넌트를 자동 생성
    """
    # 1. OAuth 매핑 사용자 우선 조회
    result = await db.execute(
        select(User).where(
            User.oauth_provider == "kakao",
            User.oauth_id == profile["kakao_id"],
        )
    )
    oauth_user = result.scalar_one_or_none()
    if oauth_user is not None:
        return oauth_user

    # 2. 기존 사용자 조회 (이메일 기반)
    if profile.get("email"):
        result = await db.execute(
            select(User).where(
                User.email == profile["email"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            # 기존 계정에 Kakao 식별자를 연결한다.
            existing.oauth_provider = "kakao"
            existing.oauth_id = profile["kakao_id"]
            await db.flush()
            return existing

    # 3. 신규 사용자용 개인 테넌트 생성
    tenant_name = f"{profile['nickname']} 워크스페이스"
    tenant = Tenant(
        name=tenant_name,
        slug=await _build_unique_tenant_slug(db, tenant_name),
        plan="free",
        is_active=True,
    )
    db.add(tenant)
    await db.flush()

    # 4. 신규 사용자 생성
    new_user = User(
        tenant_id=tenant.id,
        email=profile.get("email") or f"kakao_{profile['kakao_id']}@propai.local",
        name=profile["nickname"],
        hashed_password="",  # 소셜 로그인이므로 비밀번호 없음
        role="admin",
        is_active=True,
        oauth_provider="kakao",
        oauth_id=profile["kakao_id"],
    )
    db.add(new_user)
    await db.flush()
    return new_user


async def process_kakao_callback(
    code: str,
    redirect_uri: str,
    db: AsyncSession,
    settings: Settings,
) -> dict:
    """카카오 OAuth 콜백 전체 흐름을 처리한다.

    1. 인가 코드 → 카카오 토큰 교환
    2. 카카오 토큰 → 사용자 정보 조회
    3. DB 사용자 조회/생성
    4. JWT 발급 + 리프레시 토큰 DB 저장

    Returns:
        {"access_token": str, "refresh_token": str, "user": dict}
    """
    # 1. 토큰 교환
    # ★관리자 키화면(secret_store)이 os.environ을 즉시 갱신하나 settings는 캐시됨 →
    #   login-url과 동일하게 os.environ을 라이브 우선 읽어 재시작 없이 반영(키 불일치 방지).
    import os
    _client_id = (os.environ.get("KAKAO_REST_API_KEY") or settings.kakao_client_id or "").strip()
    _client_secret = (os.environ.get("KAKAO_CLIENT_SECRET") or settings.kakao_client_secret or "").strip() or None
    kakao_tokens = await exchange_code_for_token(
        code=code,
        redirect_uri=redirect_uri,
        client_id=_client_id,
        client_secret=_client_secret,
    )

    # 2. 사용자 정보 조회
    kakao_user = await fetch_kakao_user_info(kakao_tokens["access_token"])
    profile = extract_user_profile(kakao_user)

    # 3. DB 사용자 조회/생성
    user = await get_or_create_user(db, profile)

    # 4. JWT 발급
    access = create_access_token(user.id, user.tenant_id, user.role, settings)
    refresh = create_refresh_token(user.id, user.tenant_id, user.role, settings)

    # 5. 리프레시 토큰 DB 저장
    token_hash = hashlib.sha256(refresh.encode()).hexdigest()
    db_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days),
        device_info=f"kakao_oauth:{profile['kakao_id']}",
    )
    db.add(db_token)
    await db.commit()

    logger.info("카카오 로그인 성공", user_id=str(user.id), kakao_id=profile["kakao_id"])

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
