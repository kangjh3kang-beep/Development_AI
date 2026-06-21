"""설계 도면 벡터스토어 공용 — 컬렉션/차원 상수 + 임베딩 헬퍼(인제스트·검색 공용 DRY).

임베딩은 best-effort: 키 미설정/SDK 부재/실패 시 (None, 사유)를 반환해 호출부가 정직하게
degrade하도록 한다(예외 비전파). 모델/차원/컬렉션명의 단일 출처.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# init_qdrant.py COLLECTIONS와 동일한 컬렉션명·차원(단일 출처).
DESIGN_COLLECTION = "design_drawings"
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536


async def embed_text(text: str) -> tuple[list[float] | None, str | None]:
    """텍스트 임베딩(best-effort). 반환: (벡터, 생략사유). 성공 시 (vector, None).

    사유: no_openai_key | embed_error.
    """
    try:
        from openai import AsyncOpenAI

        from apps.api.config import get_settings

        key = get_settings().openai_api_key
        if not key:
            return None, "no_openai_key"
        client = AsyncOpenAI(api_key=key)
        resp = await client.embeddings.create(model=EMBED_MODEL, input=text[:8000])
        return list(resp.data[0].embedding), None
    except Exception as e:  # noqa: BLE001
        logger.warning("design 임베딩 실패: %s", str(e)[:120])
        return None, "embed_error"
