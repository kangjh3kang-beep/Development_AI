"""관리자 편집 가능 옵션목록(현장유형 등) — DB jsonb 저장.

화면의 고정 드롭다운(현장유형 등)을 관리자가 추가/삭제할 수 있게 한다.
GET(인증 사용자) / PUT(관리자) — 키별 [{value,label}] 목록.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

router = APIRouter(prefix="/admin/option-lists", tags=["관리자 편집목록"])

# 기본값(테이블/행 부재 시) — 키별 시드
_DEFAULTS: dict[str, list[dict[str, str]]] = {
    "sales_site_types": [
        {"value": "APT", "label": "아파트"},
        {"value": "OFFICETEL", "label": "오피스텔"},
        {"value": "KNOWLEDGE_CENTER", "label": "지식산업센터"},
        {"value": "HOTEL", "label": "생활숙박시설/호텔"},
        {"value": "RETAIL", "label": "상가"},
    ],
}

_ADMIN_ROLES = {"admin", "manager", "owner", "super_admin"}

_DDL = (
    "CREATE TABLE IF NOT EXISTS app_option_lists ("
    "key text PRIMARY KEY, items jsonb NOT NULL DEFAULT '[]'::jsonb, "
    "updated_at timestamptz DEFAULT now())"
)


class OptionItem(BaseModel):
    value: str
    label: str


class OptionListBody(BaseModel):
    items: list[OptionItem]


async def _ensure(db: AsyncSession) -> None:
    await db.execute(text(_DDL))
    await db.commit()


@router.get("/{key}")
async def get_option_list(
    key: str,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """옵션목록 조회. 저장값 없으면 기본 시드 반환."""
    _ = current_user
    try:
        await _ensure(db)
        row = (
            await db.execute(
                text("SELECT items FROM app_option_lists WHERE key = :k"), {"k": key}
            )
        ).first()
        if row and row[0]:
            return {"key": key, "items": row[0]}
    except Exception:  # noqa: BLE001
        pass
    return {"key": key, "items": _DEFAULTS.get(key, [])}


@router.put("/{key}")
async def put_option_list(
    key: str,
    body: OptionListBody,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """옵션목록 저장(관리자 전용). 빈 value/label·중복 value 제거."""
    from app.services.billing.billing_service import is_super_admin
    if not await is_super_admin(db, current_user.user_id):
        raise HTTPException(403, "관리자만 편집할 수 있습니다.")
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for it in body.items:
        v = it.value.strip()
        lbl = it.label.strip()
        if not v or not lbl or v in seen:
            continue
        seen.add(v)
        items.append({"value": v, "label": lbl})
    await _ensure(db)
    await db.execute(
        text(
            "INSERT INTO app_option_lists(key, items) VALUES (:k, CAST(:v AS jsonb)) "
            "ON CONFLICT (key) DO UPDATE SET items = EXCLUDED.items, updated_at = now()"
        ),
        {"k": key, "v": json.dumps(items)},
    )
    await db.commit()
    return {"key": key, "items": items}
