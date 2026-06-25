import logging

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Constants
COLLECTION_NAME = "propai_agent_memory"
VECTOR_SIZE = 1536  # text-embedding-3-small dimension size

# ★프로세스 싱글톤 — 호출마다 새 클라이언트를 만들면 in-memory(:memory:) 모드에서 매번 빈
#   저장소가 생성돼 회상이 직전에 저장한 것조차 못 찾는다(프로세스 내 공유 불가). 한 번 만든
#   클라이언트를 재사용한다(QDRANT_HOST 운영 모드에서도 커넥션 재사용으로 효율↑).
_CLIENT: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """
    Initialize and return the Qdrant client (프로세스 싱글톤).
    Creates the collection if it doesn't exist.
    """
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    settings = get_settings()

    # We use in-memory or a specific host based on settings.
    # For now, if QDRANT_HOST is not set, we default to local memory for dev
    qdrant_host = getattr(settings, "QDRANT_HOST", None)
    qdrant_port = getattr(settings, "QDRANT_PORT", 6333)

    if qdrant_host:
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        logger.info(f"Connected to Qdrant at {qdrant_host}:{qdrant_port}")
    else:
        # Fallback for local testing without docker
        client = QdrantClient(":memory:")
        logger.warning("QDRANT_HOST not set, using in-memory Qdrant instance.")

    _ensure_collection(client)
    _CLIENT = client
    return client

def _ensure_collection(client: QdrantClient):
    """Ensure the agent memory collection exists."""
    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)

    if not exists:
        logger.info(f"Creating Qdrant collection: {COLLECTION_NAME}")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
