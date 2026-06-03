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
