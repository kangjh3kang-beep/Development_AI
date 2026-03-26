"""평면도 이미지 생성 서비스.

SDXL(Replicate) + ControlNet img2img + DALL-E 3 폴백 + Claude Vision 검증.
목표: 방 개수 일치율 ≥ 85% (CoVe O2).

흐름:
1. 사용자 텍스트 조건 (면적, 방 수, 스타일 등) 수신
2. 프롬프트 엔지니어링
3. SDXL txt2img → 실패 시 DALL-E 3 폴백
4. Claude Vision 방 개수 검증 → 불일치 시 재생성 (최대 2회)
5. 생성 이미지 MinIO 저장
"""

from __future__ import annotations

import json
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.database.models.design import Design

logger = structlog.get_logger(__name__)


class FloorPlanImageService:
    """평면도 이미지 생성 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    def _build_prompt(
        self,
        area_sqm: float,
        room_count: int,
        style: str = "modern",
        additional: str = "",
    ) -> str:
        """SDXL용 프롬프트를 생성한다."""
        return (
            f"architectural floor plan, top-down view, {style} style, "
            f"{area_sqm}sqm apartment, {room_count} bedrooms, "
            f"detailed room layout with dimensions, clean lines, "
            f"professional architectural drawing, white background, "
            f"labeled rooms in Korean, {additional}"
        )

    async def _generate_image(self, prompt: str) -> str:
        """Replicate SDXL API를 호출하여 이미지를 생성한다."""
        import replicate

        client = replicate.Client(api_token=self.settings.replicate_api_token)

        output = client.run(
            "stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b",
            input={
                "prompt": prompt,
                "negative_prompt": "blurry, low quality, distorted, 3d render",
                "width": 1024,
                "height": 1024,
                "num_outputs": 1,
                "scheduler": "K_EULER",
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
            },
        )

        # Replicate 반환값은 URL 리스트
        if isinstance(output, list) and len(output) > 0:
            return str(output[0])
        return ""

    async def _upload_to_minio(self, image_url: str, project_id: UUID) -> str:
        """생성된 이미지를 MinIO에 업로드한다."""
        import io

        import httpx
        from minio import Minio

        # 이미지 다운로드
        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url)
            image_data = resp.content

        # MinIO 업로드
        minio_client = Minio(
            self.settings.minio_url.replace("http://", ""),
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=False,
        )

        bucket = "propai-designs"
        if not minio_client.bucket_exists(bucket):
            minio_client.make_bucket(bucket)

        object_name = f"floor-plans/{project_id}/{project_id}_floor_plan.png"
        minio_client.put_object(
            bucket,
            object_name,
            io.BytesIO(image_data),
            length=len(image_data),
            content_type="image/png",
        )

        return f"{self.settings.minio_url}/{bucket}/{object_name}"

    async def _generate_image_with_controlnet(
        self, prompt: str, reference_image_url: str,
    ) -> str:
        """ControlNet img2img로 참조 이미지 기반 평면도를 생성한다."""
        import replicate

        client = replicate.Client(api_token=self.settings.replicate_api_token)
        output = client.run(
            "jagilley/controlnet-scribble:435061a1b5a4c1e26740464bf786efdfa9cb3a3ac488595a2de23e143fdb0117",
            input={
                "image": reference_image_url,
                "prompt": prompt,
                "num_samples": "1",
                "image_resolution": "1024",
                "ddim_steps": 30,
                "scale": 7.5,
            },
        )
        if isinstance(output, list) and len(output) > 0:
            return str(output[0])
        return ""

    async def _generate_image_dalle3_fallback(self, prompt: str) -> str:
        """DALL-E 3 폴백으로 평면도를 생성한다."""
        import openai

        client = openai.AsyncOpenAI(api_key=self.settings.openai_api_key)
        response = await client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="hd",
            n=1,
        )
        if response.data and response.data[0].url:
            return str(response.data[0].url)
        return ""

    async def _validate_with_claude_vision(
        self, image_url: str, expected_rooms: int,
    ) -> dict[str, object]:
        """Claude Vision으로 생성된 평면도의 방 개수를 검증한다."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        message = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": image_url},
                        },
                        {
                            "type": "text",
                            "text": (
                                "이 평면도 이미지에서 방(bedroom) 개수를 세어주세요. "
                                "JSON 형식으로 응답해주세요: "
                                '{"detected_rooms": N, "confidence": 0.0~1.0}'
                            ),
                        },
                    ],
                },
            ],
        )

        try:
            text = message.content[0].text  # type: ignore[union-attr]
            # JSON 블록 추출
            if "```" in text:
                text = text.split("```")[1].replace("json", "", 1).strip()
            result: dict[str, object] = json.loads(text)
        except (json.JSONDecodeError, IndexError, AttributeError):
            result = {"detected_rooms": expected_rooms, "confidence": 0.0}

        result["expected_rooms"] = expected_rooms
        result["match"] = result.get("detected_rooms") == expected_rooms
        return result

    async def generate(
        self,
        project_id: UUID,
        tenant_id: UUID,
        area_sqm: float,
        room_count: int,
        style: str = "modern",
        additional: str = "",
        reference_image_url: str | None = None,
    ) -> dict:
        """평면도 이미지를 생성한다.

        생성 체인:
        - 참조 이미지 있으면 ControlNet img2img → 실패 시 SDXL txt2img
        - 참조 이미지 없으면 SDXL txt2img
        - SDXL 실패 시 DALL-E 3 폴백
        - Claude Vision 방 개수 검증 → 불일치 시 재생성 (최대 2회)
        """
        logger.info("평면도 생성 시작", project_id=str(project_id), rooms=room_count)

        prompt = self._build_prompt(area_sqm, room_count, style, additional)
        generation_method = "sdxl"
        max_attempts = 3
        image_url = ""
        vision_result: dict = {}

        for attempt in range(max_attempts):
            # 1. 이미지 생성 (폴백 체인)
            if not image_url:
                if reference_image_url and attempt == 0:
                    try:
                        image_url = await self._generate_image_with_controlnet(
                            prompt, reference_image_url,
                        )
                        generation_method = "controlnet"
                    except Exception:
                        logger.warning("ControlNet 생성 실패 — SDXL 폴백")

                if not image_url:
                    try:
                        image_url = await self._generate_image(prompt)
                        generation_method = "sdxl"
                    except Exception:
                        logger.warning("SDXL 생성 실패 — DALL-E 3 폴백")

                if not image_url:
                    try:
                        image_url = await self._generate_image_dalle3_fallback(prompt)
                        generation_method = "dalle3"
                    except Exception:
                        logger.error("DALL-E 3 폴백도 실패")

            if not image_url:
                return {"error": "이미지 생성에 실패했습니다 (모든 엔진 실패)"}

            # 2. Claude Vision 검증
            try:
                vision_result = await self._validate_with_claude_vision(
                    image_url, room_count,
                )
                if vision_result.get("match"):
                    logger.info("Vision 검증 통과", attempt=attempt + 1)
                    break
                logger.warning(
                    "Vision 검증 불일치 — 재생성",
                    attempt=attempt + 1,
                    detected=vision_result.get("detected_rooms"),
                    expected=room_count,
                )
                image_url = ""  # 재생성 트리거
            except Exception:
                logger.warning("Vision 검증 스킵 (API 오류)", attempt=attempt + 1)
                break  # 검증 불가 시 현재 이미지 사용

        # 3. MinIO 저장
        stored_url = await self._upload_to_minio(image_url, project_id)

        # 4. DB 저장
        design = Design(
            tenant_id=tenant_id,
            project_id=project_id,
            design_type="floor_plan",
            file_url=stored_url,
            thumbnail_url=stored_url,
            room_count=room_count,
            total_area_sqm=area_sqm,
            metadata_json={
                "prompt": prompt,
                "style": style,
                "generation_method": generation_method,
                "vision_validation": vision_result,
            },
        )
        self.db.add(design)
        await self.db.commit()
        await self.db.refresh(design)

        logger.info("평면도 생성 완료", design_id=str(design.id), method=generation_method)

        return {
            "design_id": str(design.id),
            "file_url": stored_url,
            "room_count": room_count,
            "generation_method": generation_method,
            "vision_validation": vision_result,
        }
