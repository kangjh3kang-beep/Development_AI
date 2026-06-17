"""멀티모달 비전 입력 — image_ref(파일경로/URL/data-uri) → Anthropic messages image 블록.

이미지가 아니면(단순 텍스트 참조) None 반환 → 상위가 텍스트 프롬프트 폴백(날조 금지).
로컬 파일은 base64 인코딩, http(s)는 url source, data-uri는 파싱.
"""
from __future__ import annotations

import base64
import os

_MEDIA = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}


def build_image_block(image_ref: str | None) -> dict | None:
    """image_ref → Anthropic content image 블록(또는 None=이미지 아님)."""
    if not image_ref:
        return None
    s = image_ref.strip()
    if s.startswith(("http://", "https://")):
        return {"type": "image", "source": {"type": "url", "url": s}}
    if s.startswith("data:"):
        try:
            header, data = s.split(",", 1)
            media = header[5:].split(";")[0] or "image/png"
            return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
        except ValueError:
            return None
    if os.path.isfile(s):
        media = _MEDIA.get(os.path.splitext(s)[1].lower(), "image/png")
        try:
            with open(s, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            return None
        return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
    return None  # 이미지 아님 → 텍스트 폴백


def build_content(image_ref: str | None, prompt: str) -> list | str:
    """멀티모달 content 구성 — 이미지 있으면 [image, text], 없으면 텍스트(참조 명시)."""
    block = build_image_block(image_ref)
    if block is not None:
        return [block, {"type": "text", "text": prompt}]
    ref = f" (이미지 참조: {image_ref})" if image_ref else ""
    return prompt + ref
