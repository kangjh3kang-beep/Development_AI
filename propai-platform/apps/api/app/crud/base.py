"""제너릭 CRUD 베이스 — 전 sales 엔티티 공통 영속 로직."""

import uuid
from datetime import datetime, timezone
from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

M = TypeVar("M")


class CRUDBase(Generic[M]):
    def __init__(self, model: Type[M]):
        self.model = model

    async def get(self, db: AsyncSession, id_: uuid.UUID) -> M | None:
        return (await db.execute(select(self.model).where(self.model.id == id_))).scalar_one_or_none()

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

    async def update(self, db: AsyncSession, id_: uuid.UUID, data: dict) -> M | None:
        obj = await self.get(db, id_)
        if not obj:
            return None
        for k, v in data.items():
            if v is not None:
                setattr(obj, k, v)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def delete(self, db: AsyncSession, id_: uuid.UUID) -> bool:
        obj = await self.get(db, id_)
        if not obj:
            return False
        if hasattr(obj, "deleted_at"):
            obj.deleted_at = datetime.now(timezone.utc)  # soft-delete
        else:
            await db.delete(obj)
        await db.flush()
        return True
