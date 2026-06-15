"""네이버 OAuth 2.0 핸들러.

네이버 OAuth 흐름(카카오 패턴 + state CSRF 검증):
1. 인가 코드 + state 수신 → 토큰 교환
2. 토큰으로 사용자 정보(/v1/nid/me) 조회
3. DB 사용자 조회 또는 자동 생성(공용 oauth_common)
4. JWT 액세스/리프레시 토큰 발급

★네이버는 인가/콜백에 state(CSRF 방지) 전달이 필수다.
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

NAVER_TOKEN_URL = "https://nid.naver.com/oauth2.0/token"
NAVER_USER_INFO_URL = "https://openapi.naver.com/v1/nid/me"


class NaverOAuthError(OAuthError):
    """네이버 OAuth 처리 중 발생하는 예외."""


async def exchange_code_for_token(
    code: str,
    state: str,
    client_id: str,
    client_secret: str,
) -> dict:
    """인가 코드를 네이버 액세스 토큰으로 교환한다(state 포함)."""
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "state": state,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(NAVER_TOKEN_URL, data=payload)

    if resp.status_code != 200:
        logger.warning("네이버 토큰 교환 실패", status=resp.status_code, body=resp.text[:500])
        raise NaverOAuthError(
            f"네이버 토큰 교환 실패: {resp.status_code}",
            status_code=resp.status_code,
        )

    data = dict(resp.json())
    # 네이버는 HTTP 200이어도 본문에 error 필드로 실패를 알릴 수 있다.
    if data.get("error"):
        logger.warning("네이버 토큰 응답 오류", error=data.get("error"), desc=data.get("error_description"))
        raise NaverOAuthError(
            f"네이버 토큰 교환 실패: {data.get('error_description') or data.get('error')}",
            status_code=400,
        )
    return data


async def fetch_naver_user_info(access_token: str) -> dict:
    """네이버 액세스 토큰으로 사용자 정보를 조회한다.

    Returns:
        네이버 응답 (resultcode, message, response.{id,email,name,nickname})
    """
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(NAVER_USER_INFO_URL, headers=headers)

    if resp.status_code != 200:
        logger.warning("네이버 사용자 정보 조회 실패", status=resp.status_code, body=resp.text[:500])
        raise NaverOAuthError(
            f"네이버 사용자 정보 조회 실패: {resp.status_code}",
            status_code=resp.status_code,
        )

    return dict(resp.json())


def extract_user_profile(naver_data: dict) -> dict:
    """네이버 응답에서 공용 프로필을 추출한다.

    Returns:
        {"provider_id": str(response.id), "email": str|None, "nickname": str}
    """
    response = naver_data.get("response", {}) or {}
    provider_id = str(response.get("id", ""))
    email = response.get("email")
    nickname = response.get("name") or response.get("nickname") or email or f"naver_{provider_id}"

    return {
        "provider_id": provider_id,
        "email": email,
        "nickname": nickname,
    }


async def process_naver_callback(
    code: str,
    state: str,
    redirect_uri: str,
    db: AsyncSession,
    settings: Settings,
) -> dict:
    """네이버 OAuth 콜백 전체 흐름을 처리한다.

    redirect_uri는 네이버 토큰 교환 파라미터엔 불필요하나, 라우트 시그니처 정합을 위해 받는다.

    Returns:
        {"access_token", "refresh_token", "token_type", "user"}
    """
    import os

    # ★관리자 키화면(secret_store)이 os.environ을 즉시 갱신하나 settings는 캐시됨 →
    #   os.environ을 라이브 우선 읽어 재시작 없이 반영(키 불일치 방지).
    _client_id = (os.environ.get("NAVER_CLIENT_ID") or settings.naver_client_id or "").strip()
    _client_secret = (os.environ.get("NAVER_CLIENT_SECRET") or settings.naver_client_secret or "").strip()

    tokens = await exchange_code_for_token(
        code=code,
        state=state,
        client_id=_client_id,
        client_secret=_client_secret,
    )

    naver_user = await fetch_naver_user_info(tokens["access_token"])
    profile = extract_user_profile(naver_user)

    user = await get_or_create_oauth_user(db, "naver", profile)

    return await finalize_oauth_login(
        db, user, settings, provider="naver", provider_id=profile["provider_id"],
    )
