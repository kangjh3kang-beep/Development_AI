from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from bcrypt import hashpw, checkpw, gensalt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.database import get_db
from app.models.auth import User, AuditLog
import structlog

logger = structlog.get_logger()
security = HTTPBearer()

def hash_password(password: str) -> str:
    return hashpw(password.encode(), gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return checkpw(plain.encode(), hashed.encode())

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        # 로그인은 jwt_handler(token_type 클레임)로 토큰 발급 → type/token_type 둘 다 허용(이중 인증체계 호환)
        token_kind = payload.get("type") or payload.get("token_type")
        if not user_id or token_kind != "access":
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
    except JWTError:
        raise HTTPException(status_code=401, detail="토큰 검증 실패")
    # 정식 User 모델(tenant_id) 사용 — app.models.auth.User(stale, organization_id)는 실 스키마와 불일치(500).
    from apps.api.database.models.user import User as DBUser
    result = await db.execute(
        select(DBUser).where(DBUser.id == user_id, DBUser.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없음")
    return user


# 인증이 "있으면 사용, 없으면 None" — 무인증도 허용하되 로그인 시 사용자 식별(과금 등).
_optional_security = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_security),
    db: AsyncSession = Depends(get_db),
):
    """토큰이 없거나 만료/무효면 401을 던지지 않고 None을 반환한다.

    포토리얼 렌더처럼 '키 미설정이면 정직 안내(200)'가 핵심인 엔드포인트에서, 토큰 만료로
    401이 먼저 터져 'API 요청 거부'로 표시되던 문제를 막는다. 과금은 user가 있을 때만.
    """
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials=credentials, db=db)
    except HTTPException:
        return None
