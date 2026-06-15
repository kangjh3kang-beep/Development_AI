"""제너릭 CRUD 베이스 — 전 sales 엔티티 공통 영속 로직."""

import uuid
from datetime import datetime, timezone, UTC
from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

M = TypeVar("M")


class CRUDBase(Generic[M]):
    def __init__(self, model: type[M]):
        self.model = model

    async def get(self, db: AsyncSession, id_: uuid.UUID, site_id=None) -> M | None:
        # site_id가 주어지고 모델에 site_id 컬럼이 있으면 '같은 현장' 것만 조회한다.
        # (멀티테넌트 격리: 다른 현장의 UUID를 알아도 그 현장 데이터를 못 보게 막는다.)
        q = select(self.model).where(self.model.id == id_)
        if site_id is not None and hasattr(self.model, "site_id"):
            q = q.where(self.model.site_id == site_id)
        if hasattr(self.model, "deleted_at"):
            q = q.where(self.model.deleted_at.is_(None))
        return (await db.execute(q)).scalar_one_or_none()

    async def list(self, db: AsyncSession, site_id=None, limit=100, offset=0, **filters):
        q = select(self.model)
        if site_id is not None and hasattr(self.model, "site_id"):
            q = q.where(self.model.site_id == site_id)
        if hasattr(self.model, "deleted_at"):
            q = q.where(self.model.deleted_at.is_(None))
        for k, v in filters.items():
            if v is not None and hasattr(self.model, k):
                q = q.where(getattr(self.model, k) == v)
        q = q.limit(limit).offset(offset)
        return list((await db.execute(q)).scalars().all())

    async def create(self, db: AsyncSession, data: dict) -> M:
        obj = self.model(**data)
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def update(self, db: AsyncSession, id_: uuid.UUID, data: dict, site_id=None) -> M | None:
        obj = await self.get(db, id_, site_id=site_id)  # 같은 현장 것만 수정 허용
        if not obj:
            return None
        for k, v in data.items():
            if v is not None:
                setattr(obj, k, v)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def delete(self, db: AsyncSession, id_: uuid.UUID, site_id=None) -> bool:
        obj = await self.get(db, id_, site_id=site_id)  # 같은 현장 것만 삭제 허용
        if not obj:
            return False
        if hasattr(obj, "deleted_at"):
            obj.deleted_at = datetime.now(UTC)  # soft-delete
        else:
            await db.delete(obj)
        await db.flush()
        return True
