"""L4 — 쟁점 임베딩. 실 의미 임베더(주입) 우선, 없으면 결정론 해시 폴백(재현성).

P-C 격상: client 주입 시 의미 벡터(표기 달라도 유사 포착), 미가용 시 해시(동일 키 동일 벡터).
is_semantic으로 상위(PrecedentSearch)가 유사도 임계를 조정.
"""
from __future__ import annotations

import hashlib
import json

from app.adapters.embedding.embedding_client import EmbeddingClient
from app.settings import env_or_setting

_DIM = 16
_MOD = 1000


class Embedder:
    def __init__(self, client: EmbeddingClient | None = None) -> None:
        self.client = client

    @property
    def is_semantic(self) -> bool:
        return self.client is not None

    def embed(self, issue: object) -> list[float]:
        key = issue if isinstance(issue, str) else json.dumps(issue, sort_keys=True, ensure_ascii=False)
        if self.client is not None:
            vec = self.client.embed(key)
            if vec:
                return vec  # 실 의미 벡터
        return self._hash_embed(key)  # 결정론 해시 폴백

    def _hash_embed(self, key: str) -> list[float]:
        vec: list[float] = []
        for d in range(_DIM):
            digest = hashlib.sha256(f"{key}:{d}".encode("utf-8")).hexdigest()
            vec.append((int(digest, 16) % _MOD) / _MOD)
        return vec


def build_embedder() -> Embedder:
    """설정 기반 임베더 팩토리. EMBEDDER=openai + 키 가용 시 실 의미, 아니면 해시(결정론)."""
    if env_or_setting("EMBEDDER") == "openai":
        from app.adapters.embedding.embedding_client import OpenAIEmbeddingClient
        client = OpenAIEmbeddingClient()
        if client.available:
            return Embedder(client=client)
    return Embedder()
