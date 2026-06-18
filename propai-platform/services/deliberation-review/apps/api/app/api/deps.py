"""P2 — API 의존성: async 세션 + 베어러 토큰 인증.

require_token: settings.API_TOKEN 미설정(빈 값) = 개방(dev). 설정 시 'Bearer <token>' 일치 요구.
"""
from __future__ import annotations

import hmac
import uuid
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.settings import settings


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session() as session:
        yield session


def get_tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")) -> uuid.UUID | None:
    """BFF가 전달한 테넌트 컨텍스트(#8a 심층방어). 미설정=레거시/직접호출(격리 미적용, 후방호환).
    설정 시 save_analysis가 organization_id로 적재, get_analysis가 소유 필터(교차테넌트 차단). hex/하이픈 모두 수용."""
    if not x_tenant_id:
        return None
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid X-Tenant-Id") from exc


def require_token(authorization: str | None = Header(default=None)) -> None:
    token = settings.API_TOKEN
    if not token:
        return  # 미설정 = 개방(개발/로컬). production fail-closed는 settings 부팅 검증에서.
    # scheme 분리 + 상수시간 비교(타이밍 사이드채널로 토큰 바이트복원 차단).
    scheme, _, tok = (authorization or "").partition(" ")
    if scheme != "Bearer" or not hmac.compare_digest(tok, token):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")
