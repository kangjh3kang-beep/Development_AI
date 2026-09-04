"""Qdrant 벡터DB 컬렉션 초기화.

법령 RAG 검색을 위한 벡터 컬렉션을 생성한다.
앱 시작 시 또는 별도 초기화 스크립트로 실행한다.
"""

import asyncio

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
)

from apps.api.config import get_settings
from apps.api.logging_config import get_logger

logger = get_logger(__name__)

# 컬렉션 정의
COLLECTIONS = {
    "regulations": {
        "size": 1536,           # OpenAI text-embedding-3-small 차원
        "distance": Distance.COSINE,
        "description": "법령/규제 문서 임베딩 (RAG용)",
    },
    "design_references": {
        "size": 1536,
        "distance": Distance.COSINE,
        "description": "설계 참조 문서 임베딩",
    },
    "project_documents": {
        "size": 1536,
        "distance": Distance.COSINE,
        "description": "프로젝트 문서 임베딩 (보고서, 분석 결과)",
    },
    "design_drawings": {
        "size": 1536,
        "distance": Distance.COSINE,
        "description": "설계 도면 임베딩 (배치도/평면도/단면도/입면도/주차 — 검색+조합용)",
        # 검색 필터 필드 — payload 인덱스로 대규모에서 풀스캔 방지(테넌트격리·분야/종류 분리검색).
        "payload_indexes": ("tenant_id", "drawing_type", "discipline"),
    },
}


def get_qdrant_client() -> QdrantClient:
    """Qdrant 클라이언트를 반환한다."""
    settings = get_settings()
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


async def init_qdrant_collections() -> dict[str, str]:
    """Qdrant 컬렉션을 초기화한다.

    이미 존재하는 컬렉션은 건너뛴다.
    반환값: {컬렉션명: "created" | "exists"} 딕셔너리.
    """
    client = get_qdrant_client()
    results: dict[str, str] = {}

    existing = {c.name for c in client.get_collections().collections}

    for name, config in COLLECTIONS.items():
        if name in existing:
            logger.info("Qdrant 컬렉션 이미 존재", collection=name)
            results[name] = "exists"
        else:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=config["size"],
                    distance=config["distance"],
                ),
            )
            logger.info(
                "Qdrant 컬렉션 생성 완료",
                collection=name,
                description=config["description"],
            )
            results[name] = "created"

        # payload 필터 인덱스(멱등·best-effort) — 신규/기존 컬렉션 모두 보장. 실패해도 검색은
        # 동작(인덱스 없이 필터 가능)하므로 비차단.
        payload_indexes = config.get("payload_indexes", ())
        for field in payload_indexes if isinstance(payload_indexes, (tuple, list)) else ():
            try:
                client.create_payload_index(
                    collection_name=name, field_name=field, field_schema="keyword"
                )
            except Exception as e:  # noqa: BLE001 — 이미 존재/구버전 클라이언트 등은 무시
                logger.debug("payload 인덱스 생략", collection=name, field=field, error=str(e)[:120])

    return results


def check_qdrant_health_sync() -> bool:
    """Qdrant 서버 상태를 확인한다(동기).

    ★qdrant_client 는 **동기** 클라이언트다. 실제 구현이 여기이고, 아래 비동기 통로는
    이걸 스레드로 감싼다.
    """
    try:
        client = get_qdrant_client()
        client.get_collections()
        return True
    except Exception:
        logger.warning("Qdrant 연결 실패")
        return False


async def check_qdrant_health() -> bool:
    """Qdrant 서버 상태를 확인한다(비동기 통로).

    ★종전에는 ``async def`` 안에서 동기 호출을 그대로 했다. 그러면 두 가지가 깨진다:
      ① 호출이 이벤트 루프를 점유한다
      ② ``asyncio.wait_for`` 로 감싸도 **취소되지 않는다** — 이벤트 루프에 올라탄 동기
         호출은 타임아웃이 지나도 끝날 때까지 돌아오지 않으므로, 타임아웃이 장식이 된다.
    스레드로 빼야 비로소 호출부가 상한 안에서 응답할 수 있다.
    (qdrant 가 멀쩡할 땐 0.00초라 이 결함은 평소에 보이지 않는다 — 2026-08-11 실측.)
    """
    return await asyncio.to_thread(check_qdrant_health_sync)
