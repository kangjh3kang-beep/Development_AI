"""LLM API 키 정상화(sanitize) 유틸.

.env 복사 과정에서 키 값에 비-ASCII 문자(예: '→' U+2192), 따옴표, 공백,
줄바꿈, 인접 라인 텍스트가 혼입되는 사고가 있었다. 오염된 키는 httpx가
HTTP 헤더를 ascii로 인코딩하는 단계에서 UnicodeEncodeError로 터지며,
"LLM 응답 실패"처럼 보이지만 실제로는 키 문자열 문제다.

이 모듈은 키를 로드하는 모든 지점에서 호출해 오염을 조기에 걸러내고,
명확한 진단 메시지를 남긴다.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def sanitize_api_key(raw: str | None, *, key_name: str = "API_KEY") -> str:
    """API 키 문자열을 정상화한다.

    - 앞뒤 공백/따옴표/제어문자를 제거한다.
    - 내부 공백·탭·줄바꿈에서 첫 토큰만 취한다(인접 라인 혼입 방어).
    - 비-ASCII 문자가 남아 있으면 제거하고 경고 로그를 남긴다.

    Args:
        raw: 원본 키 문자열(None 허용).
        key_name: 로그에 표시할 키 이름.

    Returns:
        정상화된 ASCII 키 문자열(빈 문자열 가능).
    """
    if not raw:
        return ""

    cleaned = raw.strip().strip('"').strip("'").strip()

    # 공백/탭/줄바꿈이 섞이면 첫 토큰만 키로 간주(뒤따르는 주석·다음 라인 혼입 방어).
    if any(ch in cleaned for ch in (" ", "\t", "\n", "\r")):
        first = cleaned.split()[0] if cleaned.split() else ""
        logger.warning(
            "%s에 공백/줄바꿈이 포함되어 첫 토큰만 사용합니다 "
            "(원본 길이=%d → 정리 후=%d). .env 키 값을 점검하세요.",
            key_name, len(cleaned), len(first),
        )
        cleaned = first

    # 비-ASCII 잔존 시 제거(예: '→' U+2192). httpx 헤더 인코딩 사고 방지.
    if not cleaned.isascii():
        bad = sorted({hex(ord(c)) for c in cleaned if ord(c) > 127})
        stripped = "".join(c for c in cleaned if ord(c) < 128)
        logger.error(
            "%s에 비-ASCII 문자(%s)가 포함되어 제거했습니다. "
            ".env 키 값이 오염되었으니 깨끗한 키로 교체하세요.",
            key_name, ", ".join(bad),
        )
        cleaned = stripped

    return cleaned


def get_clean_env_key(env_name: str) -> str:
    """환경변수에서 키를 읽어 정상화하여 반환한다."""
    return sanitize_api_key(os.environ.get(env_name, ""), key_name=env_name)
