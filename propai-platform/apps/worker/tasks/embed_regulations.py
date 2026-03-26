"""법령 텍스트 벡터 임베딩 태스크.

OpenAI text-embedding-3-small로 법령 텍스트를 벡터화하고 Qdrant에 적재한다.
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def run_embed_regulations(ctx: dict[str, Any], batch_size: int = 100) -> dict[str, Any]:
    """법령 임베딩 배치 처리.

    1. DB에서 embedded=False 법령 텍스트 배치 조회
    2. OpenAI text-embedding-3-small 벡터 생성
    3. Qdrant "regulations" 컬렉션에 upsert
    4. DB에 embedded=True 업데이트
    """
    from openai import AsyncOpenAI
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import PointStruct
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    logger.info("법령 임베딩 시작", batch_size=batch_size)

    settings = ctx["settings"]
    db: AsyncSession = ctx["db"]

    # 1. 미처리 법령 텍스트 조회
    query = text(
        "SELECT id, title, content FROM regulations "
        "WHERE embedded = FALSE "
        "ORDER BY created_at "
        "LIMIT :limit"
    )
    result = await db.execute(query, {"limit": batch_size})
    rows = result.fetchall()

    if not rows:
        logger.info("임베딩 대상 없음")
        return {"status": "completed", "processed": 0, "batch_size": batch_size}

    # 2. OpenAI 임베딩 생성
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    texts = [f"{row.title}\n{row.content}" for row in rows]
    embed_response = await openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )

    vectors = [item.embedding for item in embed_response.data]

    # 3. Qdrant에 벡터 적재
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)

    points = [
        PointStruct(
            id=str(row.id),
            vector=vec,
            payload={
                "title": row.title,
                "content": row.content[:500],
                "regulation_id": str(row.id),
            },
        )
        for row, vec in zip(rows, vectors, strict=True)
    ]

    await qdrant.upsert(
        collection_name="regulations",
        points=points,
    )

    # 4. DB 상태 업데이트
    row_ids = [str(row.id) for row in rows]
    await db.execute(
        text("UPDATE regulations SET embedded = TRUE WHERE id = ANY(:ids)"),
        {"ids": row_ids},
    )
    await db.commit()

    await qdrant.close()

    processed = len(rows)
    logger.info("법령 임베딩 완료", processed=processed)
    return {"status": "completed", "processed": processed, "batch_size": batch_size}
