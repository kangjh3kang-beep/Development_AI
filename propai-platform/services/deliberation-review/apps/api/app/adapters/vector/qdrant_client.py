"""L4 — Qdrant 어댑터(인터페이스 + dev in-memory mock). 소비측 검색은 적재분만(라이브 없음).

실 Qdrant 연동은 동일 인터페이스로 후속 주입. mock은 코사인 유사도 상위 N 반환.
"""
from __future__ import annotations

import math


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class QdrantClientAdapter:
    """in-memory 벡터 저장/검색(dev). upsert(공급측) → search(소비측)."""

    def __init__(self) -> None:
        self._points: list[tuple[str, list[float], dict]] = []

    def upsert(self, case_id: str, vector: list[float], payload: dict) -> None:
        self._points.append((case_id, vector, payload))

    def search(self, vector: list[float], top: int = 5) -> list[tuple[float, str, dict]]:
        scored = [(_cosine(vector, vec), cid, payload) for cid, vec, payload in self._points]
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[:top]


class RealQdrantClient:
    """실 Qdrant 어댑터 — 동일 인터페이스(upsert/search). location=':memory:'(임베디드) 또는 http(서버).

    collection은 차원별로 분리(precedent_<dim>) — 임베더 교체 시 차원 충돌 방지. 코사인 거리.
    """

    def __init__(self, location: str, dim: int, collection: str | None = None) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._c = QdrantClient(url=location) if location.startswith("http") else QdrantClient(location=location)
        self.collection = collection or f"precedent_{dim}"
        self._dim = dim
        self._id = 0
        try:
            self._c.get_collection(self.collection)
        except Exception:  # noqa: BLE001 — 없으면 생성
            self._c.create_collection(
                self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, case_id: str, vector: list[float], payload: dict) -> None:
        from qdrant_client.models import PointStruct

        self._id += 1
        self._c.upsert(self.collection, points=[
            PointStruct(id=self._id, vector=list(vector), payload={**payload, "case_id": case_id})])

    def search(self, vector: list[float], top: int = 5) -> list[tuple[float, str, dict]]:
        res = self._c.query_points(collection_name=self.collection, query=list(vector), limit=top).points
        return [(float(p.score), p.payload["case_id"], p.payload) for p in res]


def build_qdrant(dim: int = 16):
    """벡터 저장소 팩토리. QDRANT_URL 설정+라이브러리 가용 시 실 Qdrant, 아니면 in-memory mock."""
    from app.settings import env_or_setting

    loc = (env_or_setting("QDRANT_URL") or "").strip()
    if loc:
        try:
            return RealQdrantClient(location=loc, dim=dim)
        except Exception:  # noqa: BLE001 — 라이브러리/서버 미가용 → mock 폴백
            pass
    return QdrantClientAdapter()


_DEFAULT_CLIENT = QdrantClientAdapter()


def default_qdrant() -> QdrantClientAdapter:
    return _DEFAULT_CLIENT
