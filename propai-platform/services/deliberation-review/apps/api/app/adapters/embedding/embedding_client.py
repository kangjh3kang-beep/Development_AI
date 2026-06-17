"""P-C 격상 — 실 의미 임베딩 클라이언트. 도면 쟁점/사례를 의미 벡터로(표기 달라도 유사 포착).

OpenAI embeddings(text-embedding-3) 참조 구현. 키/네트워크 부재 시 None(상위 Embedder가 해시 폴백).
키 미노출, 실패는 graceful degrade(날조 금지).
"""
from __future__ import annotations

from typing import Protocol

from app.settings import env_or_setting, settings


class EmbeddingClient(Protocol):
    """텍스트 → 의미 벡터(주입). 실 클라이언트가 구현. 실패 시 None."""

    def embed(self, text: str) -> list[float] | None: ...


class OpenAIEmbeddingClient:
    """참조 실 클라이언트(OpenAI embeddings). lazy httpx + 키 검사. 미가용 시 None."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or env_or_setting("OPENAI_API_KEY")
        self.model = model or env_or_setting("EMBEDDING_MODEL") or settings.EMBEDDING_MODEL

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def embed(self, text: str) -> list[float] | None:
        if not self.api_key:
            return None
        try:
            import httpx
        except ImportError:
            return None
        try:
            r = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": text},
                timeout=20.0,
            )
            r.raise_for_status()
            vec = r.json()["data"][0]["embedding"]
            return vec if isinstance(vec, list) and vec else None
        except Exception:
            return None  # 라이브 실패 → 상위 해시 폴백(결정론 보존)
