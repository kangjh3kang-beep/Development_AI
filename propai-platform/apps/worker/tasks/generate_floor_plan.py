"""SDXL 평면도 이미지 생성 태스크.

Replicate API를 통해 SDXL로 평면도를 생성하고 MinIO에 저장한다.
"""

import io
from typing import Any
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)

# 건축 평면도 전문 프롬프트 템플릿
_FLOOR_PLAN_TEMPLATE = (
    "architectural floor plan, top-down view, clean white background, "
    "professional CAD drawing style, precise measurements, "
    "{rooms} rooms, {extra}. "
    "Walls shown as thick black lines, doors as arcs, windows as thin lines. "
    "Room labels in Korean. Minimal furniture layout."
)


async def run_generate_floor_plan(
    ctx: dict[str, Any],
    project_id: str,
    prompt: str,
    rooms: int = 3,
) -> dict[str, Any]:
    """평면도 이미지 생성.

    1. SDXL 프롬프트 구성 (건축 평면도 전문 템플릿)
    2. Replicate API로 이미지 생성
    3. MinIO에 결과 이미지 업로드
    4. DB에 이미지 URL 저장
    """
    import httpx
    import replicate
    from miniopy_async import Minio
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    logger.info("평면도 생성 시작", project_id=project_id, rooms=rooms)

    settings = ctx["settings"]
    db: AsyncSession = ctx["db"]

    # 1. SDXL 프롬프트 구성
    full_prompt = _FLOOR_PLAN_TEMPLATE.format(rooms=rooms, extra=prompt)

    # 2. Replicate API 호출 (SDXL)
    output = await replicate.async_run(
        "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
        input={
            "prompt": full_prompt,
            "negative_prompt": "blurry, low quality, 3d render, photograph, realistic",
            "width": 1024,
            "height": 1024,
            "num_outputs": 1,
            "scheduler": "K_EULER",
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
        },
    )

    if not output:
        logger.warning("이미지 생성 실패 — 빈 응답")
        return {
            "status": "failed",
            "project_id": project_id,
            "image_url": "",
            "error": "Replicate 빈 응답",
        }

    image_url_remote = output[0] if isinstance(output, list) else str(output)

    # 3. MinIO에 업로드
    async with httpx.AsyncClient(timeout=60.0) as client:
        img_response = await client.get(image_url_remote)
        img_response.raise_for_status()
        image_data = img_response.content

    file_name = f"floor-plans/{project_id}/{uuid4().hex}.png"
    minio_client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
    )

    bucket = "propai-designs"
    if not await minio_client.bucket_exists(bucket):
        await minio_client.make_bucket(bucket)

    await minio_client.put_object(
        bucket,
        file_name,
        io.BytesIO(image_data),
        length=len(image_data),
        content_type="image/png",
    )

    minio_url = f"{settings.minio_endpoint}/{bucket}/{file_name}"

    # 4. DB에 이미지 URL 저장
    await db.execute(
        text(
            "UPDATE designs SET image_url = :url, updated_at = NOW() "
            "WHERE project_id = :pid"
        ),
        {"url": minio_url, "pid": project_id},
    )
    await db.commit()

    logger.info("평면도 생성 완료", project_id=project_id, url=minio_url)
    return {
        "status": "completed",
        "project_id": project_id,
        "image_url": minio_url,
    }
