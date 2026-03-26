"""카카오 OAuth 2.0 핸들러.

카카오 REST API를 이용한 소셜 로그인 흐름:
1. 인가 코드 수신 → 토큰 교환
2. 토큰으로 사용자 정보 조회
3. DB 사용자 조회 또는 자동 생성
4. JWT 액세스/리프레시 토큰 발급
"""

from __future__ import annotations

import hashlib
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import create_access_token, create_refresh_token
from apps.api.config import Settings
from apps.api.database.models.refresh_token import RefreshToken
from apps.api.database.models.user import User

logger = structlog.get_logger(__name__)

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
        logger.warning("카카오 사용자 정보 조회 실패", status=resp.status_code)
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


async def get_or_create_user(
    db: AsyncSession,
    profile: dict,
    tenant_id: UUID,
) -> User:
    """카카오 프로필로 사용자를 조회하거나 새로 생성한다.

    - kakao_id 기반 매칭 (oauth_provider + oauth_id)
    - 미존재 시 자동 생성 (role=viewer)
    """
    # 1. 기존 사용자 조회 (이메일 기반)
    if profile.get("email"):
        result = await db.execute(
            select(User).where(
                User.email == profile["email"],
                User.tenant_id == tenant_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    # 2. 신규 사용자 생성
    new_user = User(
        tenant_id=tenant_id,
        email=profile.get("email") or f"kakao_{profile['kakao_id']}@propai.local",
        name=profile["nickname"],
        hashed_password="",  # 소셜 로그인이므로 비밀번호 없음
        role="viewer",
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
    tenant_id: UUID,
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
    kakao_tokens = await exchange_code_for_token(
        code=code,
        redirect_uri=redirect_uri,
        client_id=settings.kakao_client_id,
        client_secret=settings.kakao_client_secret or None,
    )

    # 2. 사용자 정보 조회
    kakao_user = await fetch_kakao_user_info(kakao_tokens["access_token"])
    profile = extract_user_profile(kakao_user)

    # 3. DB 사용자 조회/생성
    user = await get_or_create_user(db, profile, tenant_id)

    # 4. JWT 발급
    access = create_access_token(user.id, user.tenant_id, user.role, settings)
    refresh = create_refresh_token(user.id, user.tenant_id, user.role, settings)

    # 5. 리프레시 토큰 DB 저장
    token_hash = hashlib.sha256(refresh.encode()).hexdigest()
    db_token = RefreshToken(
        user_id=user.id,
        tenant_id=user.tenant_id,
        token_hash=token_hash,
        expires_at=settings.jwt_refresh_token_expire_days,
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
