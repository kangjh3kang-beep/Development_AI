"""JWT 토큰 발급 및 검증.

Bearer 토큰 기반 인증. Authorization: Bearer <token> 헤더를 사용한다.
멀티테넌트 격리를 위해 토큰 페이로드에 tenant_id를 포함한다.
"""

from datetime import UTC, datetime, timedelta

UTC = UTC
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from apps.api.config import Settings, get_settings

# auto_error=False: Authorization 헤더 누락 시 HTTPBearer 기본동작(403)을 따르지 않고,
# get_current_user 본문에서 표준 의미(무인증=401)로 직접 거부한다(라우터 계약 "무인증 401" 준수).
# ★app/services/auth/auth_service.py 와 동일 계약 — 실사용 모듈에도 전역 전파.
_bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """JWT 토큰 페이로드"""
    sub: str               # 사용자 ID
    tenant_id: str          # 테넌트 ID
    role: str               # 사용자 역할
    exp: datetime           # 만료 시각
    iat: datetime           # 발급 시각
    token_type: str = "access"  # access | refresh


class CurrentUser(BaseModel):
    """인증된 현재 사용자 컨텍스트"""
    user_id: UUID
    tenant_id: UUID
    role: str


def create_access_token(
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    settings: Settings | None = None,
) -> str:
    """액세스 토큰을 생성한다."""
    if settings is None:
        settings = get_settings()

    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "token_type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def create_refresh_token(
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    settings: Settings | None = None,
) -> str:
    """리프레시 토큰을 생성한다."""
    if settings is None:
        settings = get_settings()

    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "token_type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        # 고유 nonce — 동일(user,tenant,role,초)로 동일 JWT가 생성되어 token_hash UNIQUE
        # 제약을 위반(refresh 500)하던 문제 방지. 매 발급마다 토큰을 유일하게 만든다.
        "jti": uuid4().hex,
    }
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def decode_token(token: str, settings: Settings | None = None) -> TokenPayload:
    """토큰을 검증하고 페이로드를 반환한다."""
    if settings is None:
        settings = get_settings()

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**payload)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"유효하지 않은 토큰: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


async def _get_auth_settings() -> Settings:
    """인증 의존성에서 설정을 비동기 경로로 제공한다.

    일부 환경에서 동기 Depends(get_settings)가 threadpool 경로에서 블로킹되어
    인증 요청 전체가 지연/정지될 수 있어, 이벤트루프 컨텍스트에서 직접 반환한다.
    """
    return get_settings()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    settings: Settings = Depends(_get_auth_settings),
) -> CurrentUser:
    """요청에서 현재 사용자를 추출한다. FastAPI Depends로 사용."""
    # Authorization 헤더 누락 → 무인증(401). (HTTPBearer auto_error=False로 None 전달됨)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 정보가 없습니다",
        )
    token_data = decode_token(credentials.credentials, settings)

    if token_data.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="액세스 토큰이 아닙니다",
        )

    return CurrentUser(
        user_id=UUID(token_data.sub),
        tenant_id=UUID(token_data.tenant_id),
        role=token_data.role,
    )
