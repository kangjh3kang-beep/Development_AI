"""구글 OAuth 2.0 핸들러.

구글 OAuth 흐름(카카오 패턴과 동일):
1. 인가 코드 수신 → 토큰 교환
2. 토큰으로 사용자 정보(userinfo) 조회
3. DB 사용자 조회 또는 자동 생성(공용 oauth_common)
4. JWT 액세스/리프레시 토큰 발급
"""

from __future__ import annotations

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.oauth_common import (
    OAuthError,
    finalize_oauth_login,
    get_or_create_oauth_user,
)
from apps.api.config import Settings

logger = structlog.get_logger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USER_INFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthError(OAuthError):
    """구글 OAuth 처리 중 발생하는 예외."""


async def exchange_code_for_token(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """인가 코드를 구글 액세스 토큰으로 교환한다."""
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=payload)

    if resp.status_code != 200:
        logger.warning("구글 토큰 교환 실패", status=resp.status_code, body=resp.text[:500])
        raise GoogleOAuthError(
            f"구글 토큰 교환 실패: {resp.status_code}",
            status_code=resp.status_code,
        )

    return dict(resp.json())


async def fetch_google_user_info(access_token: str) -> dict:
    """구글 액세스 토큰으로 사용자 정보를 조회한다.

    Returns:
        구글 userinfo (sub, email, name 등)
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GOOGLE_USER_INFO_URL, headers=headers)

    if resp.status_code != 200:
        logger.warning("구글 사용자 정보 조회 실패", status=resp.status_code, body=resp.text[:500])
        raise GoogleOAuthError(
            f"구글 사용자 정보 조회 실패: {resp.status_code}",
            status_code=resp.status_code,
        )

    return dict(resp.json())


def extract_user_profile(google_data: dict) -> dict:
    """구글 응답에서 공용 프로필을 추출한다.

    Returns:
        {"provider_id": str(sub), "email": str|None, "nickname": str}
    """
    provider_id = str(google_data.get("sub", ""))
    email = google_data.get("email")
    nickname = google_data.get("name") or email or f"google_{provider_id}"

    return {
        "provider_id": provider_id,
        "email": email,
        "nickname": nickname,
    }


async def process_google_callback(
    code: str,
    redirect_uri: str,
    db: AsyncSession,
    settings: Settings,
) -> dict:
    """구글 OAuth 콜백 전체 흐름을 처리한다.

    Returns:
        {"access_token", "refresh_token", "token_type", "user"}
    """
    import os

    # ★관리자 키화면(secret_store)이 os.environ을 즉시 갱신하나 settings는 캐시됨 →
    #   os.environ을 라이브 우선 읽어 재시작 없이 반영(키 불일치 방지).
    _client_id = (os.environ.get("GOOGLE_CLIENT_ID") or settings.google_client_id or "").strip()
    _client_secret = (os.environ.get("GOOGLE_CLIENT_SECRET") or settings.google_client_secret or "").strip()

    tokens = await exchange_code_for_token(
        code=code,
        redirect_uri=redirect_uri,
        client_id=_client_id,
        client_secret=_client_secret,
    )

    google_user = await fetch_google_user_info(tokens["access_token"])
    profile = extract_user_profile(google_user)

    user = await get_or_create_oauth_user(db, "google", profile)

    return await finalize_oauth_login(
        db, user, settings, provider="google", provider_id=profile["provider_id"],
    )
