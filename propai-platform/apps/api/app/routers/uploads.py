"""파일 업로드 라우터 — 현장(부지) 이미지 등 클라이언트 업로드를 서버 스토리지로 영속화.

base64를 localStorage에 보관하던 방식(용량초과·새로고침 소실)을 대체한다.
프론트는 반환된 짧은 public URL만 저장한다.
"""

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.services.storage_service import StorageError, upload_image

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/uploads", tags=["업로드"])

_MAX_BYTES = 10 * 1024 * 1024  # 10MB


def _sniff_image_type(data: bytes) -> str | None:
    """매직바이트로 실제 이미지 형식을 판별한다(선언된 content_type 위조 방지).

    JPEG/PNG/GIF/WebP만 허용. 불일치/미지원이면 None.
    """
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/image")
async def upload_image_endpoint(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, str]:
    """이미지를 업로드하고 public URL을 반환한다(인증 필수)."""
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드할 수 있습니다.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다(최대 10MB).")

    # 선언된 content_type과 무관하게 실제 바이트(매직바이트)로 형식 검증
    real_type = _sniff_image_type(data)
    if real_type is None:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 이미지 형식입니다(JPEG/PNG/GIF/WebP만 허용).",
        )

    try:
        url = await upload_image(data, real_type)
    except StorageError as exc:
        logger.warning("이미지 업로드 실패", error=str(exc))
        raise HTTPException(status_code=502, detail=f"스토리지 업로드 실패: {exc}") from exc

    return {"url": url}
