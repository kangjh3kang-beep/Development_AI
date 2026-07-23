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

from app.core.audit import audit_admin_action
from app.services.billing.billing_service import is_super_admin
from app.services.secrets import secret_store
from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.database.session import get_db

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


@router.get("/llm-health")
async def llm_health(
    provider: str = "anthropic",
    model: str | None = None,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 LLM 연결 진단 — 키 유효성·계정 상태를 '실호출(PONG)'로 확인한다(평문 키 비노출).

    'AI 해석이 생성되지 않음'의 진짜 원인을 1회 호출로 식별: 키 미설정 / 키 무효(401) /
    크레딧·레이트(402·429) / 모델 거부. 인터프리터가 실패를 삼켜 '지연'으로만 보이던 문제를
    관리자가 즉시 진단할 수 있게 한다. 반환에 키 값은 절대 포함하지 않는다(길이·존재여부만).
    """
    await _require_admin(current, db)
    import asyncio
    import os as _os

    from app.services.ai.key_sanitizer import get_clean_env_key

    env_map = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GOOGLE_API_KEY"}
    env_name = env_map.get(provider, "ANTHROPIC_API_KEY")
    key = get_clean_env_key(env_name)
    raw_present = bool((_os.environ.get(env_name) or "").strip())
    out: dict = {
        "provider": provider, "env_name": env_name,
        "key_present": bool(key), "key_len": len(key or ""),
        "raw_env_present": raw_present,  # sanitize 전 원본 env 존재여부(오버레이 적용 확인용)
    }
    if not key:
        out["ok"] = False
        out["error_type"] = "key_not_configured"
        out["error"] = (f"{env_name}가 실행 환경(os.environ)에 비어 있습니다. 키 입력 후에도 비어 있으면 "
                        "시크릿 오버레이 미적용/복호화 실패 — 백엔드 재시작 또는 SECRET_STORE_KEY 점검 필요.")
        return out
    try:
        from langchain_core.messages import HumanMessage

        from app.services.ai.llm_provider import get_llm
        llm = get_llm(provider=provider, model=model, timeout=20, max_tokens=16) if model \
            else get_llm(provider=provider, timeout=20, max_tokens=16)
        out["model"] = getattr(llm, "model", getattr(llm, "model_name", None))
        r = await asyncio.wait_for(
            llm.ainvoke([HumanMessage(content="Reply with one word: PONG")]), timeout=25
        )
        out["ok"] = True
        out["reply"] = str(getattr(r, "content", r))[:40]
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:260]
        if key:
            msg = msg.replace(key, "***")  # 만일을 대비해 키 값 스크럽(에러에 키 echo 방지)
        out["ok"] = False
        out["error_type"] = type(e).__name__
        out["error"] = msg
    return out


@router.get("/image-health")
async def image_health(
    provider: str = "openai",
    model: str | None = None,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """관리자 이미지 생성 진단 — 키+SDK패키지 존재 + 실제 소형 1회 생성으로 모델 ID 유효성을 확정.

    'Gemini 나노바나나/ gpt-image가 되나?'를 1회 호출로 식별: 키 미설정 / SDK 미설치 /
    모델 ID 무효(빈응답·404) / 정상(generated>0). 무날조 — 실제 API 응답으로만 ok 판정.
    """
    await _require_admin(current, db)
    import os as _os

    from app.services.ai.image_provider import (
        _IMAGE_PACKAGE,
        IMAGE_PROVIDERS,
        ImageGenerationError,
        _image_package_available,
        generate_image,
        resolve_model,
    )
    from app.services.ai.key_sanitizer import get_clean_env_key

    cfg = IMAGE_PROVIDERS.get(provider)
    if not cfg:
        return {"provider": provider, "ok": False, "error_type": "unknown_provider",
                "valid": list(IMAGE_PROVIDERS.keys())}
    env_name = cfg["env_key"]
    key = get_clean_env_key(env_name)
    pkg_ok = _image_package_available(provider)
    out: dict = {
        "provider": provider, "env_name": env_name,
        "key_present": bool(key), "key_len": len(key or ""),
        "raw_env_present": bool((_os.environ.get(env_name) or "").strip()),
        "package": _IMAGE_PACKAGE.get(provider), "package_installed": pkg_ok,
        "model": model or resolve_model(provider),
    }
    if not key:
        out["ok"] = False
        out["error_type"] = "key_not_configured"
        out["error"] = f"{env_name}가 os.environ에 비어 있음(시크릿 오버레이/복호화 점검)."
        return out
    if not pkg_ok:
        out["ok"] = False
        out["error_type"] = "package_missing"
        out["error"] = f"{_IMAGE_PACKAGE.get(provider)} SDK 미설치 — requirements(+oracle) 추가 후 재배포 필요."
        return out
    try:
        import asyncio
        res = await asyncio.wait_for(
            generate_image(provider=provider, prompt="a small solid blue square on white, minimal",
                           model=model, size="1024x1024", n=1, timeout=90),
            timeout=100,
        )
        imgs = res.get("images") or res.get("image_urls") or []
        out["ok"] = bool(imgs)
        out["generated"] = len(imgs)
        out["model"] = res.get("model")
        if not imgs:
            out["error_type"] = "empty_response"
    except ImageGenerationError as e:
        out["ok"] = False
        out["error_type"] = e.error_type
        out["error"] = str(e)[:260].replace(key, "***")
    except Exception as e:  # noqa: BLE001
        out["ok"] = False
        out["error_type"] = type(e).__name__
        out["error"] = str(e)[:260].replace(key, "***")
    return out


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
        if name in {"HYPHEN_HKEY", "HYPHEN_USER_ID", "REGISTRY_PROVIDER", "TILKO_API_KEY"}:
            from app.services.registry.registry_service import RegistryService
            st = RegistryService().status()
            return {"ok": bool(st.get("register_ready") or st.get("configured")),
                    "message": st.get("message") or f"등기 공급자: {st.get('provider')}",
                    "detail": st}
        return {"ok": True, "message": "값이 설정되어 있습니다(전용 테스트 미지원 키)."}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"테스트 실패: {str(e)[:120]}"}
