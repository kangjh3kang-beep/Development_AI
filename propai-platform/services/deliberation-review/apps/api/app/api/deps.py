"""P2 — API 의존성: async 세션 + 베어러 토큰 인증.

require_token: settings.API_TOKEN 미설정(빈 값) = 개방(dev). 설정 시 'Bearer <token>' 일치 요구.
"""
from __future__ import annotations

import hmac
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.settings import settings


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


def require_token(authorization: str | None = Header(default=None)) -> None:
    token = settings.API_TOKEN
    if not token:
        return  # 미설정 = 개방(개발/로컬). production fail-closed는 settings 부팅 검증에서.
    # scheme 분리 + 상수시간 비교(타이밍 사이드채널로 토큰 바이트복원 차단).
    scheme, _, tok = (authorization or "").partition(" ")
    if scheme != "Bearer" or not hmac.compare_digest(tok, token):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")
