"""API 키 관리 라우터.

SHA-256 해시로 저장하며, 평문 키는 생성 시 1회만 노출한다.
"""

import hashlib
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import APIKeyCreateRequest, APIKeyCreateResponse, APIKeyResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.models.api_key import APIKey
from apps.api.database.session import get_db

router = APIRouter()


@router.post("", response_model=APIKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: APIKeyCreateRequest,
    current_user: CurrentUser = Depends(RequirePermission("api_keys", "write")),
    db: AsyncSession = Depends(get_db),
) -> APIKeyCreateResponse:
    """API 키를 생성한다. 평문 키는 이 응답에서만 확인 가능하다."""
    # 평문 키 생성 (48바이트 = 96자 hex)
    raw_key = f"pk_{secrets.token_hex(32)}"
    key_prefix = raw_key[:10]
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    api_key = APIKey(
        tenant_id=current_user.tenant_id,
        name=body.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return APIKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=key_prefix,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
    )


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys(
    current_user: CurrentUser = Depends(RequirePermission("api_keys", "read")),
    db: AsyncSession = Depends(get_db),
) -> list[APIKeyResponse]:
    """테넌트의 API 키 목록을 조회한다."""
    result = await db.execute(
        select(APIKey)
        .where(APIKey.tenant_id == current_user.tenant_id)
        .order_by(APIKey.created_at.desc())
    )
    keys = list(result.scalars().all())

    return [
        APIKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes,
            is_active=k.is_active,
            last_used_at=k.last_used_at,
            expires_at=k.expires_at,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("api_keys", "delete")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """API 키를 비활성화(폐기)한다."""
    result = await db.execute(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.tenant_id == current_user.tenant_id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API 키를 찾을 수 없습니다",
        )

    api_key.is_active = False
    await db.commit()
