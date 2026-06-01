"""Supabase Storage 업로드 서비스.

기존 인프라(서버 .env의 SUPABASE_URL/SERVICE_ROLE_KEY + config의 storage 버킷)를
재사용한다. 신규 파이썬 의존성 없이 httpx REST로 업로드한다.

흐름: 바이트 업로드 → 버킷 자동 보장(없으면 public 생성) → public URL 반환.
프론트는 base64(수 MB) 대신 짧은 URL만 보관하므로 localStorage 용량 문제도 해소된다.
"""

import uuid

import httpx
import structlog

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

# 허용 이미지 형식 → 확장자
_ALLOWED_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


class StorageError(Exception):
    """스토리지 업로드 실패."""


async def _ensure_bucket(
    client: httpx.AsyncClient, base: str, bucket: str, headers: dict[str, str]
) -> None:
    """버킷 존재를 보장한다. 없으면 public 버킷으로 생성한다(멱등)."""
    resp = await client.get(f"{base}/storage/v1/bucket/{bucket}", headers=headers)
    if resp.status_code == 200:
        return
    create = await client.post(
        f"{base}/storage/v1/bucket",
        headers=headers,
        json={"id": bucket, "name": bucket, "public": True},
    )
    if create.status_code in (200, 201):
        logger.info("Supabase Storage 버킷 생성", bucket=bucket)
        return
    # 동시성/기존 존재 등은 정상으로 간주
    if "already exists" in create.text.lower() or create.status_code == 409:
        return
    raise StorageError(f"버킷 생성 실패: {create.status_code} {create.text[:200]}")


async def upload_image(
    data: bytes, content_type: str, prefix: str = "site-images"
) -> str:
    """이미지 바이트를 Supabase Storage에 업로드하고 public URL을 반환한다.

    Args:
        data: 이미지 바이트
        content_type: MIME 타입 (image/png 등)
        prefix: 버킷 내 경로 프리픽스
    """
    settings = get_settings()
    base = (getattr(settings, "supabase_url", "") or "").rstrip("/")
    key = getattr(settings, "supabase_service_role_key", "") or ""
    bucket = getattr(settings, "supabase_storage_bucket", "") or "propai-uploads"

    if not base or not key:
        raise StorageError(
            "Supabase Storage가 설정되지 않았습니다(SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY)."
        )

    ext = _ALLOWED_TYPES.get(content_type.lower())
    if not ext:
        raise StorageError(f"지원하지 않는 이미지 형식: {content_type}")

    path = f"{prefix}/{uuid.uuid4().hex}.{ext}"
    auth = {"Authorization": f"Bearer {key}", "apikey": key}

    async with httpx.AsyncClient(timeout=60.0) as client:
        await _ensure_bucket(client, base, bucket, auth)
        resp = await client.post(
            f"{base}/storage/v1/object/{bucket}/{path}",
            headers={**auth, "Content-Type": content_type, "x-upsert": "true"},
            content=data,
        )
        if resp.status_code not in (200, 201):
            raise StorageError(f"업로드 실패: {resp.status_code} {resp.text[:200]}")

    public_url = f"{base}/storage/v1/object/public/{bucket}/{path}"
    logger.info("이미지 업로드 완료", path=path, bytes=len(data))
    return public_url
