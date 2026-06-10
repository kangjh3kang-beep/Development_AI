"""관리자 전용 — 플랫폼 연동 API 키 관리(입력/수정/삭제 + 사용자 임의추가).

엔드포인트(prefix=/api/v1/admin/secrets):
- GET  /                       : 분류별·항목별 키 상태(설정여부·마스킹·출처). 평문 미노출.
- PUT  /{name}                 : 키 입력/수정(카탈로그 키 또는 사용자추가 키 갱신).
- POST /                       : 사용자 임의추가(name+value+분류/라벨) — 향후 코드수정 불필요.
- DELETE /{name}               : 키 삭제(.env 원본 복원/제거).
- POST /{name}/test            : 등기/공공데이터 키 간이 연결 테스트(선택).
- GET  /{name}/backups         : 그 키의 백업(버전) 이력(마스킹, 평문 미노출).
- POST /backups/{id}/restore   : 백업 한 건을 현재 값으로 복구.

권한: role ∈ 관리자군(JWT). 단일 워커라 변경 즉시 반영(재배포 불필요).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db
from app.core.audit import audit_admin_action
from app.services.secrets import secret_store
from app.services.billing.billing_service import is_super_admin

router = APIRouter(prefix="/api/v1/admin/secrets", tags=["관리자·API키"])


async def _require_admin(current: CurrentUser, db: AsyncSession) -> None:
    """플랫폼 총괄관리자(users.tier='super_admin')만 허용.

    ★role 기반 금지: 가입 시 모든 사용자가 '자기 테넌트의' role='admin'이 되므로
      role로 판별하면 전원 통과(플랫폼 키 금고 누출)된다. 반드시 tier로 판별한다.
    """
    if not await is_super_admin(db, current.user_id):
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다.")


class SecretSetRequest(BaseModel):
    value: str = Field(..., min_length=1)
    label: str | None = None
    group: str | None = None
    secret: bool | None = None


class SecretAddRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=64)
    value: str = Field(..., min_length=1)
    label: str | None = None
    group: str | None = None
    secret: bool | None = True


@router.get("")
async def list_secrets(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """분류별·항목별 키 상태. (값은 마스킹, 평문 절대 미반환)"""
    await _require_admin(current, db)
    items = await secret_store.list_status(db)
    groups: list[str] = []
    for it in items:
        if it["group"] not in groups:
            groups.append(it["group"])
    return {"groups": groups, "items": items}


@router.put("/{name}")
async def set_secret(
    name: str,
    req: SecretSetRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """키 입력/수정 — 즉시 반영."""
    await _require_admin(current, db)
    try:
        await secret_store.set_secret(
            db, name, req.value, str(current.user_id),
            label=req.label, group=req.group, secret=req.secret,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 감사기록(누가·언제·어떤키 변경) — 값은 절대 기록하지 않음.
    await audit_admin_action(
        actor_id=str(current.user_id), actor_role=current.role,
        action="secret.set", target=name,
    )
    return {"status": "ok", "name": name}


@router.post("")
async def add_secret(
    req: SecretAddRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사용자 임의추가 — 새 네임+값으로 키 등록(분류/라벨 선택)."""
    await _require_admin(current, db)
    try:
        await secret_store.set_secret(
            db, req.name, req.value, str(current.user_id),
            label=req.label, group=req.group, secret=req.secret,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_admin_action(
        actor_id=str(current.user_id), actor_role=current.role,
        action="secret.add", target=req.name.strip(),
    )
    return {"status": "ok", "name": req.name.strip()}


@router.delete("/{name}")
async def delete_secret(
    name: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """키 삭제 — .env 원본 복원(없으면 제거)."""
    await _require_admin(current, db)
    try:
        await secret_store.delete_secret(db, name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_admin_action(
        actor_id=str(current.user_id), actor_role=current.role,
        action="secret.delete", target=name,
    )
    return {"status": "ok", "name": name}


@router.get("/{name}/backups")
async def list_secret_backups(
    name: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """그 키의 백업(버전) 이력 — 마스킹값·동작·시점·작업자. 평문 절대 미반환."""
    await _require_admin(current, db)
    items = await secret_store.list_backups(db, name)
    return {"name": name, "items": items}


@router.post("/backups/{backup_id}/restore")
async def restore_secret_backup(
    backup_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """백업 한 건을 현재 값으로 복구 — 현재 값은 복구 전 자동 백업됨. 평문 미반환."""
    await _require_admin(current, db)
    try:
        await secret_store.restore_secret(db, backup_id, str(current.user_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit_admin_action(
        actor_id=str(current.user_id), actor_role=current.role,
        action="secret.restore", target=backup_id,
    )
    return {"status": "ok", "backup_id": backup_id}


@router.post("/{name}/test")
async def test_secret(
    name: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """간이 연결 테스트 — 등기(registry)/공공데이터 일부 키에 한해 동작 확인."""
    await _require_admin(current, db)
    import os

    name = (name or "").strip()
    val = os.getenv(name) or ""
    if not val:
        return {"ok": False, "message": "값이 설정되지 않았습니다."}

    try:
        if name in {"APICK_CL_AUTH_KEY", "REGISTRY_PROVIDER", "CODEF_CLIENT_ID",
                    "CODEF_CLIENT_SECRET", "TILKO_API_KEY"}:
            from app.services.registry.registry_service import RegistryService
            st = RegistryService().status()
            return {"ok": bool(st.get("register_ready") or st.get("configured")),
                    "message": st.get("message") or f"등기 공급자: {st.get('provider')}",
                    "detail": st}
        return {"ok": True, "message": "값이 설정되어 있습니다(전용 테스트 미지원 키)."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"테스트 실패: {str(e)[:120]}"}
