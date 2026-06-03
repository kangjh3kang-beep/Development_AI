"""제너릭 CRUD 라우터 팩토리 — (model, schema) → 표준 REST 엔드포인트."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.deps_sales import SalesCtx, sales_ctx
from app.crud.base import CRUDBase

DEFAULT_WRITE_ROLES = ("AGENCY", "SUBAGENCY", "DIRECTOR", "GM_DIRECTOR", "DEVELOPER")


def make_crud_router(*, model, create_schema: type[BaseModel], update_schema: type[BaseModel],
                     read_schema: type[BaseModel], prefix: str, tags: list[str],
                     write_roles: tuple = DEFAULT_WRITE_ROLES) -> APIRouter:
    r = APIRouter(prefix=prefix, tags=tags)
    crud = CRUDBase(model)

    @r.get("", response_model=list[read_schema])
    async def _list(limit: int = 100, offset: int = 0, db: AsyncSession = Depends(get_db),
                    ctx: SalesCtx = Depends(sales_ctx)):
        return await crud.list(db, site_id=getattr(ctx, "site_id", None), limit=limit, offset=offset)

    @r.get("/{id_}", response_model=read_schema)
    async def _get(id_: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: SalesCtx = Depends(sales_ctx)):
        obj = await crud.get(db, id_)
        if not obj:
            raise HTTPException(404)
        return obj

    @r.post("", response_model=read_schema, status_code=201)
    async def _create(body: create_schema, db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(sales_ctx)):
        if ctx.role not in write_roles and ctx.role != "SUPERADMIN":
            raise HTTPException(403)
        data = body.model_dump(exclude_unset=True)
        if hasattr(model, "site_id") and "site_id" not in data:
            data["site_id"] = ctx.site_id
        obj = await crud.create(db, data)
        await db.commit()
        return obj

    @r.patch("/{id_}", response_model=read_schema)
    async def _update(id_: uuid.UUID, body: update_schema, db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(sales_ctx)):
        if ctx.role not in write_roles and ctx.role != "SUPERADMIN":
            raise HTTPException(403)
        obj = await crud.update(db, id_, body.model_dump(exclude_unset=True))
        if not obj:
            raise HTTPException(404)
        await db.commit()
        return obj

    @r.delete("/{id_}", status_code=204)
    async def _delete(id_: uuid.UUID, db: AsyncSession = Depends(get_db),
                      ctx: SalesCtx = Depends(sales_ctx)):
        if ctx.role not in write_roles and ctx.role != "SUPERADMIN":
            raise HTTPException(403)
        ok = await crud.delete(db, id_)
        if not ok:
            raise HTTPException(404)
        await db.commit()

    return r
