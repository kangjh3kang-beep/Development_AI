"""멀티모달 비전 입력 — image_ref(파일경로/URL/data-uri) → Anthropic messages image 블록.

이미지가 아니면(단순 텍스트 참조) None 반환 → 상위가 텍스트 프롬프트 폴백(날조 금지).
로컬 파일은 base64 인코딩, http(s)는 url source, data-uri는 파싱.
"""
from __future__ import annotations

import base64
import ipaddress
import os
from urllib.parse import urlparse

_MEDIA = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}


def _allowed_dir() -> str | None:
    """로컬 이미지 허용 루트(ALLOWED_IMAGE_DIR). 미설정 시 로컬 파일 차단(fail-closed)."""
    d = os.environ.get("ALLOWED_IMAGE_DIR")
    return os.path.realpath(d) if d else None


def _is_safe_local(path: str) -> bool:
    """허용 디렉터리 하위만 허용(경로 탈출·임의 파일 유출 차단). 심볼릭/.. 정규화."""
    base = _allowed_dir()
    if not base:
        return False
    real = os.path.realpath(path)
    try:
        return os.path.commonpath([real, base]) == base
    except ValueError:  # 드라이브 상이 등
        return False


def _is_safe_url(url: str) -> bool:
    """사설/내부망 호스트 차단(SSRF). 공인 호스트만 외부 fetch 허용."""
    host = (urlparse(url).hostname or "").strip("[]")
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except ValueError:
        low = host.lower()
        return low != "localhost" and not (low.endswith(".local") or low.endswith(".internal"))


def build_image_block(image_ref: str | None) -> dict | None:
    """image_ref → Anthropic content image 블록(또는 None=이미지 아님/차단). 경로탈출·SSRF 차단."""
    if not image_ref:
        return None
    s = image_ref.strip()
    if s.startswith(("http://", "https://")):
        if not _is_safe_url(s):
            return None  # SSRF — 내부/사설 호스트 차단
        return {"type": "image", "source": {"type": "url", "url": s}}
    if s.startswith("data:"):
        try:
            header, data = s.split(",", 1)
            media = header[5:].split(";")[0] or "image/png"
            return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
        except ValueError:
            return None
    # 로컬 파일 — 허용 디렉터리 + 이미지 확장자 화이트리스트만(임의 파일 유출 차단)
    ext = os.path.splitext(s)[1].lower()
    if ext in _MEDIA and _is_safe_local(s) and os.path.isfile(s):
        try:
            with open(s, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            return None
        return {"type": "image", "source": {"type": "base64", "media_type": _MEDIA[ext], "data": data}}
    return None  # 이미지 아님/차단 → 텍스트 폴백


def build_content(image_ref: str | None, prompt: str) -> list | str:
    """멀티모달 content 구성 — 이미지 있으면 [image, text], 없으면 텍스트(참조 명시)."""
    block = build_image_block(image_ref)
    if block is not None:
        return [block, {"type": "text", "text": prompt}]
    ref = f" (이미지 참조: {image_ref})" if image_ref else ""
    return prompt + ref
