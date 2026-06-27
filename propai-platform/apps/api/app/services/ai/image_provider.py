"""이미지 생성 멀티 프로바이더 관리 (llm_provider.py의 이미지 버전).

지원 프로바이더:
- openai:  gpt-image (ChatGPT 이미지) — DALL-E 3 후속, 지시 준수·텍스트 렌더링 향상.
- google:  Gemini 이미지 ("나노바나나") — Gemini 네이티브 이미지 생성/편집.
- replicate: SDXL/ControlNet 등 (img2img 구조보존 렌더).

★프로바이더 노출은 'API 키 설정 + SDK 패키지 설치' 둘 다 충족 시에만(get_available_image_providers).
  키만 있고 SDK 미설치면 노출하지 않는다(선택 시 ModuleNotFoundError로 깨지는 반쪽출하 방지).
★무목업: 생성 실패/미설정 시 가짜 이미지를 만들지 않고 정직하게 예외를 던진다(호출처가 정직 강등).
★모델 ID는 공급사가 빠르게 갱신(예 Nano Banana Pro)하므로 env로 덮어쓸 수 있다
  (OPENAI_IMAGE_MODEL / GEMINI_IMAGE_MODEL / REPLICATE_IMAGE_VERSION).

사용법:
    from app.services.ai.image_provider import generate_image, get_available_image_providers
    providers = get_available_image_providers()
    result = await generate_image(provider="openai", prompt="...", size="1024x1024")
    # result = {"provider","model","images":[<base64 png>...],"mime"}
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any

from app.services.ai.key_sanitizer import get_clean_env_key


class ImageGenerationError(RuntimeError):
    """이미지 생성 실패(미설정/SDK부재/API오류). 호출처는 정직 강등(가짜 이미지 금지)."""

    def __init__(self, message: str, *, error_type: str = "generation_failed"):
        super().__init__(message)
        self.error_type = error_type


# ── 등록된 이미지 프로바이더 ──
# default_model은 env(model_env)로 덮어쓸 수 있다(신모델 ID 대응).
IMAGE_PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI gpt-image",
        "models": [
            {"id": "gpt-image-1", "name": "GPT Image 1", "tier": "standard"},
        ],
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-image-1",
        "model_env": "OPENAI_IMAGE_MODEL",
        "supports_edit": True,
    },
    "google": {
        "name": "Google Gemini Image (나노바나나)",
        "models": [
            {"id": "gemini-2.5-flash-image", "name": "Gemini 2.5 Flash Image (Nano Banana)", "tier": "standard"},
        ],
        "env_key": "GOOGLE_API_KEY",
        "default_model": "gemini-2.5-flash-image",
        "model_env": "GEMINI_IMAGE_MODEL",
        "supports_edit": True,
    },
    "replicate": {
        "name": "Replicate (SDXL/ControlNet)",
        "models": [
            {"id": "sdxl", "name": "Stable Diffusion XL", "tier": "economy"},
        ],
        "env_key": "REPLICATE_API_TOKEN",
        "default_model": "sdxl",
        "model_env": "REPLICATE_IMAGE_VERSION",
        "supports_edit": True,
    },
}

# 프로바이더 키 → 이미지 SDK 패키지 임포트명(노출 가드용).
_IMAGE_PACKAGE = {
    "openai": "openai",
    "google": "google.genai",
    "replicate": "replicate",
}


def _image_package_available(provider_key: str) -> bool:
    """이미지 SDK 패키지 설치 여부. ★미설치면 노출 금지(반쪽출하/dead-channel 방지)."""
    import importlib.util

    pkg = _IMAGE_PACKAGE.get(provider_key)
    if not pkg:
        return False
    try:
        return importlib.util.find_spec(pkg) is not None
    except (ImportError, ValueError):
        return False


def resolve_model(provider_key: str) -> str:
    """프로바이더 기본 모델 ID 반환(env 오버라이드 우선 — 신모델 ID 대응)."""
    cfg = IMAGE_PROVIDERS.get(provider_key, {})
    env_name = cfg.get("model_env")
    override = (os.environ.get(env_name, "").strip() if env_name else "")
    return override or cfg.get("default_model", "")


def get_available_image_providers() -> list[dict[str, Any]]:
    """API 키 + SDK 패키지가 모두 갖춰진 사용 가능 이미지 프로바이더 목록.

    키만 있고 SDK 미설치면 제외(반쪽출하 방지). env로 덮어쓴 기본 모델도 함께 표기.
    """
    available: list[dict[str, Any]] = []
    for key, provider in IMAGE_PROVIDERS.items():
        api_key = get_clean_env_key(provider["env_key"])
        if api_key and _image_package_available(key):
            available.append({
                "provider": key,
                "name": provider["name"],
                "models": provider["models"],
                "default_model": resolve_model(key),
                "supports_edit": provider.get("supports_edit", False),
            })
    return available


def _require(provider: str) -> tuple[dict[str, Any], str]:
    """프로바이더 설정 + 정상화된 키 반환. 미설정/미설치면 ImageGenerationError."""
    cfg = IMAGE_PROVIDERS.get(provider)
    if not cfg:
        valid = ", ".join(IMAGE_PROVIDERS.keys())
        raise ImageGenerationError(
            f"알 수 없는 이미지 프로바이더: {provider}. 가능: {valid}", error_type="unknown_provider"
        )
    if not _image_package_available(provider):
        raise ImageGenerationError(
            f"{provider} 이미지 SDK 미설치({_IMAGE_PACKAGE.get(provider)}). requirements에 추가 후 재배포 필요.",
            error_type="package_missing",
        )
    api_key = get_clean_env_key(cfg["env_key"])
    if not api_key:
        raise ImageGenerationError(
            f"{provider} 키 미설정({cfg['env_key']}). 관리자 시크릿/환경변수 설정 필요.",
            error_type="key_not_configured",
        )
    return cfg, api_key


async def generate_image(
    provider: str,
    prompt: str,
    *,
    model: str | None = None,
    size: str = "1024x1024",
    n: int = 1,
    input_image_b64: str | None = None,
    timeout: float = 120.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """프로바이더로 이미지를 생성(텍스트→이미지, input_image_b64 주면 이미지 편집/변형).

    Returns: {"provider","model","images":[<base64(png)>...],"image_urls":[<url>...],"mime"}
        ★통일 계약: openai/google은 images(base64) 채움·image_urls=[], replicate는 image_urls(URL) 채움·images=[].
        소비처는 `res["images"]` 우선, 없으면 `res["image_urls"]`를 쓰면 모든 프로바이더 처리됨.
    Raises: ImageGenerationError (미설정/SDK부재/API오류 — 가짜 이미지 금지·정직 강등용).
    """
    cfg, api_key = _require(provider)
    model_id = model or resolve_model(provider)

    if provider == "openai":
        return await _gen_openai(api_key, model_id, prompt, size, n, input_image_b64, timeout)
    if provider == "google":
        # google(Gemini)은 generate_content 단건 — n 미지원(요청당 1장). size→aspect_ratio 매핑은 후속.
        return await _gen_google(api_key, model_id, prompt, input_image_b64, timeout)
    if provider == "replicate":
        return await _gen_replicate(api_key, model_id, prompt, input_image_b64, timeout, kwargs)
    raise ImageGenerationError(f"지원하지 않는 프로바이더: {provider}", error_type="unknown_provider")


async def _gen_openai(
    api_key: str, model_id: str, prompt: str, size: str, n: int,
    input_image_b64: str | None, timeout: float,
) -> dict[str, Any]:
    """OpenAI gpt-image — images.generate(텍스트) / images.edit(이미지 입력). 응답은 b64_json."""
    try:
        from openai import AsyncOpenAI
    except ImportError as e:  # pragma: no cover - 가드에서 선차단
        raise ImageGenerationError(f"openai SDK 임포트 실패: {e}", error_type="package_missing") from e

    client = AsyncOpenAI(api_key=api_key, timeout=timeout)
    try:
        if input_image_b64:
            import io

            raw = base64.b64decode(_strip_data_uri(input_image_b64))
            buf = io.BytesIO(raw)
            buf.name = "input.png"
            resp = await client.images.edit(model=model_id, image=buf, prompt=prompt, size=size, n=n)
        else:
            resp = await client.images.generate(model=model_id, prompt=prompt, size=size, n=n)
    except Exception as e:  # noqa: BLE001 - 외부 API 오류를 정직하게 표면화
        raise ImageGenerationError(f"OpenAI 이미지 생성 실패: {str(e)[:200]}", error_type="api_error") from e

    images = [d.b64_json for d in (resp.data or []) if getattr(d, "b64_json", None)]
    if not images:
        raise ImageGenerationError("OpenAI가 이미지를 반환하지 않음(빈 응답).", error_type="empty_response")
    return {"provider": "openai", "model": model_id, "images": images, "image_urls": [], "mime": "image/png"}


async def _gen_google(
    api_key: str, model_id: str, prompt: str,
    input_image_b64: str | None, timeout: float,
) -> dict[str, Any]:
    """Gemini 이미지(나노바나나) — google-genai generate_content(response_modalities=[IMAGE]).

    동기 SDK라 to_thread로 호출. 입력 이미지를 주면 편집/변형(이미지+프롬프트 contents).
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:  # pragma: no cover - 가드에서 선차단
        raise ImageGenerationError(f"google-genai SDK 임포트 실패: {e}", error_type="package_missing") from e

    def _call() -> list[str]:
        client = genai.Client(api_key=api_key)
        contents: list[Any] = [prompt]
        if input_image_b64:
            raw = base64.b64decode(_strip_data_uri(input_image_b64))
            contents.append(types.Part.from_bytes(data=raw, mime_type="image/png"))
        resp = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
        out: list[str] = []
        for cand in (resp.candidates or []):
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    out.append(base64.b64encode(inline.data).decode("ascii"))
        return out

    try:
        images = await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout)
    except ImageGenerationError:
        raise
    except Exception as e:  # noqa: BLE001 - 외부 API 오류 정직 표면화
        raise ImageGenerationError(f"Gemini 이미지 생성 실패: {str(e)[:200]}", error_type="api_error") from e

    if not images:
        raise ImageGenerationError(
            "Gemini가 이미지를 반환하지 않음(모델 ID가 이미지 비대응이거나 안전필터). "
            "GEMINI_IMAGE_MODEL을 이미지 생성 모델로 설정하세요.",
            error_type="empty_response",
        )
    return {"provider": "google", "model": model_id, "images": images, "image_urls": [], "mime": "image/png"}


async def _gen_replicate(
    api_key: str, model_version: str, prompt: str,
    input_image_b64: str | None, timeout: float, kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Replicate — 모델 버전(env REPLICATE_IMAGE_VERSION 또는 kwargs['version'])로 생성. URL 반환."""
    try:
        import replicate
    except ImportError as e:  # pragma: no cover
        raise ImageGenerationError(f"replicate SDK 임포트 실패: {e}", error_type="package_missing") from e

    version = kwargs.get("version") or (model_version if model_version != "sdxl" else "") or os.environ.get(
        "REPLICATE_IMAGE_VERSION", ""
    )
    if not version:
        raise ImageGenerationError(
            "Replicate 모델 버전 미설정(REPLICATE_IMAGE_VERSION 또는 version 인자 필요).",
            error_type="model_not_configured",
        )
    inputs: dict[str, Any] = {"prompt": prompt}
    if input_image_b64:
        inputs["image"] = _ensure_data_uri(input_image_b64)

    def _call() -> list[str]:
        client = replicate.Client(api_token=api_key)
        out = client.run(version, input=inputs)
        if isinstance(out, str):
            return [out]
        return [str(u) for u in (out or [])]

    try:
        urls = await asyncio.wait_for(asyncio.to_thread(_call), timeout=timeout)
    except Exception as e:  # noqa: BLE001
        raise ImageGenerationError(f"Replicate 생성 실패: {str(e)[:200]}", error_type="api_error") from e
    if not urls:
        raise ImageGenerationError("Replicate가 결과를 반환하지 않음.", error_type="empty_response")
    # ★통일 계약: 모든 프로바이더가 images(base64)+image_urls(URL) 키를 함께 반환(소비처 분기 불요).
    #   replicate는 URL만 반환하므로 images=[](소비처는 image_urls 사용). mime은 URL 콘텐츠 타입 추정.
    return {"provider": "replicate", "model": version, "images": [], "image_urls": urls, "mime": "image/png"}


def _strip_data_uri(b64: str) -> str:
    """'data:image/png;base64,...' 접두사를 제거해 순수 base64만 반환."""
    if b64.startswith("data:") and "," in b64:
        return b64.split(",", 1)[1]
    return b64


def _ensure_data_uri(b64: str) -> str:
    """순수 base64면 data URI로 감싼다(Replicate 입력용)."""
    if b64.startswith("data:"):
        return b64
    return f"data:image/png;base64,{b64}"
