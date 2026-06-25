import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.memory import AgentMemory
from app.schemas.memory import MemoryCreate, MemoryRecallResponse
from app.services.memory_hub.qdrant_client import COLLECTION_NAME

logger = logging.getLogger(__name__)

# 회상(recall) 인라인 await 핫패스 보호용 시간예산(초). 임베딩 망 왕복 + Qdrant 검색 상한.
_RECALL_TIMEOUT_SEC = 3.0


class MemoryHubService:
    """성장 뇌 RAG 저장/회상. ★인프라(임베딩 langchain_openai·OPENAI_API_KEY·Qdrant)는
    선택적 — 미설치/미설정 시 graceful degrade(크래시·import 실패 금지). DB(agent_memories)
    기록은 임베딩 없이도 항상 수행(audit/WRITE 측 보장)하고, 의미검색(Qdrant 벡터)은 가용 시에만.
    """

    def __init__(self):
        self.settings = get_settings()
        # Qdrant — best-effort(미설치/연결실패 시 None → 벡터 저장/검색 생략).
        self.qdrant = None
        try:
            from app.services.memory_hub.qdrant_client import get_qdrant_client
            self.qdrant = get_qdrant_client()
        except Exception as e:  # noqa: BLE001
            logger.warning("Qdrant 미가용 — 의미검색 생략(graceful): %s", str(e)[:160])
        # 임베딩 — langchain_openai 미설치 또는 OPENAI_API_KEY 미설정 시 None(graceful).
        self.embeddings = None
        try:
            api_key = getattr(self.settings, "OPENAI_API_KEY", None)
            if api_key:
                from langchain_openai import OpenAIEmbeddings
                self.embeddings = OpenAIEmbeddings(api_key=api_key, model="text-embedding-3-small")
            else:
                logger.info("OPENAI_API_KEY 미설정 — 임베딩 생략(DB 기록만, 의미검색 비활성)")
        except Exception as e:  # noqa: BLE001
            logger.warning("임베딩 미가용(langchain_openai 미설치 등) — DB 기록만(graceful): %s", str(e)[:160])

    async def store_experience(self, db: AsyncSession, memory_data: MemoryCreate) -> AgentMemory:
        """
        Embeds the memory summary and stores it in Qdrant, then saves metadata to PostgreSQL.
        """
        # 1·2. 임베딩 + Qdrant 벡터 저장(★가용 시에만 — 미가용이면 DB 기록은 계속, 의미검색만 비활성).
        point_ids: list[str] = []
        if self.embeddings is not None and self.qdrant is not None:
            try:
                from qdrant_client.http.models import PointStruct
                vector = await asyncio.to_thread(self.embeddings.embed_query, memory_data.summary)
                point_id = str(uuid.uuid4())
                payload = {
                    "project_id": str(memory_data.project_id) if memory_data.project_id else None,
                    "session_id": memory_data.session_id,
                    "domain": memory_data.domain,
                    "source_type": memory_data.source_type,
                    "summary": memory_data.summary,
                    "metadata": memory_data.metadata,
                    # ★회상 시 시간순 정보 보존 + MemoryRecallResponse.created_at 검증 충족(ISO8601).
                    "created_at": datetime.now(UTC).isoformat(),
                }
                await asyncio.to_thread(
                    self.qdrant.upsert,
                    collection_name=COLLECTION_NAME,
                    points=[PointStruct(id=point_id, vector=vector, payload=payload)],
                )
                point_ids = [point_id]
            except Exception as e:  # noqa: BLE001 — 임베딩/Qdrant 실패는 DB 기록을 막지 않음(graceful)
                logger.warning("임베딩/Qdrant 저장 생략(graceful): %s", str(e)[:160])

        # 3. Store in DB(★항상 — 임베딩 없이도 에이전트 실행 audit/learning 기록 보장).
        db_memory = AgentMemory(
            project_id=memory_data.project_id,
            session_id=memory_data.session_id,
            domain=memory_data.domain,
            source_type=memory_data.source_type,
            summary=memory_data.summary,
            qdrant_point_ids=point_ids,
            metadata_=memory_data.metadata,
        )
        db.add(db_memory)
        await db.commit()
        await db.refresh(db_memory)

        logger.info("Stored experience memory %s in DB (vector=%s).",
                    db_memory.id, "yes" if point_ids else "no")
        return db_memory

    async def recall_experience(
        self, query: str, domain: str | None = None, top_k: int = 3,
    ) -> list[MemoryRecallResponse]:
        """
        Searches Qdrant for past memories similar to the query.
        ★임베딩/Qdrant 미가용 시 빈 리스트(graceful — 회상 없이 진행, 가짜 회상 금지).
        """
        if self.embeddings is None or self.qdrant is None:
            return []
        # 1. Embed query — ★timeout budget(임베딩 망 왕복이 패널/분석 핫패스를 막지 않도록 상한).
        #   expert_panel.analyze 등은 recall 을 인라인 await 한다(ingest 와 달리 비차단 불가) → 예산 초과 시
        #   회상 생략(graceful). _RECALL_TIMEOUT_SEC 기본 3초.
        try:
            vector = await asyncio.wait_for(
                asyncio.to_thread(self.embeddings.embed_query, query),
                timeout=_RECALL_TIMEOUT_SEC,
            )
        except Exception as e:  # noqa: BLE001 — TimeoutError 포함(asyncio.TimeoutError ⊂ Exception)
            logger.warning("회상 임베딩 실패/시간초과(graceful): %s", str(e)[:160])
            return []

        # 2. Build filter
        from qdrant_client.http import models
        filter_args = None
        if domain:
            filter_args = models.Filter(
                must=[
                    models.FieldCondition(
                        key="domain",
                        match=models.MatchValue(value=domain)
                    )
                ]
            )

        # 3. Search Qdrant — 동일 시간예산으로 검색도 상한(핫패스 보호).
        try:
            search_results = await asyncio.wait_for(
                asyncio.to_thread(
                    self.qdrant.search,
                    collection_name=COLLECTION_NAME,
                    query_vector=vector,
                    query_filter=filter_args,
                    limit=top_k,
                ),
                timeout=_RECALL_TIMEOUT_SEC,
            )
        except Exception as e:  # noqa: BLE001 — 검색 실패/시간초과 시 회상 생략(graceful)
            logger.warning("회상 검색 실패/시간초과(graceful): %s", str(e)[:160])
            return []

        # 4. Format responses — ★개별 포인트 파싱 실패가 회상 전체를 죽이지 않도록 항목별 격리.
        #   created_at 은 ISO8601 문자열을 datetime 으로 안전 파싱(없거나 형식오류면 None — 스키마 Optional).
        results = []
        for scored_point in search_results:
            payload = scored_point.payload or {}
            created_raw = payload.get("created_at")
            created_at = None
            if isinstance(created_raw, str) and created_raw:
                try:
                    created_at = datetime.fromisoformat(created_raw)
                except ValueError:
                    created_at = None
            # ★id 위조 금지: point id가 유효 UUID가 아니면(정수/레거시/외부주입 등) 가짜 uuid4 날조 대신
            #   해당 항목을 스킵한다. 날조된 id는 어떤 agent_memories 행도 가리키지 못해 recalled_memory_ids
            #   provenance를 silent 훼손(상류 dedup/추적/감사 불가)하므로, 추적 가능한 항목만 회상에 포함한다.
            try:
                mem_id = uuid.UUID(str(scored_point.id))
            except (ValueError, TypeError, AttributeError):
                logger.warning("회상 항목 id 비-UUID(스킵·위조금지): %s", str(scored_point.id)[:80])
                continue
            try:
                results.append(
                    MemoryRecallResponse(
                        id=mem_id,
                        domain=payload.get("domain", ""),
                        source_type=payload.get("source_type", ""),
                        summary=payload.get("summary", ""),
                        score=scored_point.score,
                        created_at=created_at,
                        metadata=payload.get("metadata", {}),
                    )
                )
            except Exception as e:  # noqa: BLE001 — 한 항목 검증 실패가 회상 전체를 막지 않음(graceful)
                logger.warning("회상 항목 포맷 실패(스킵): %s", str(e)[:160])

        return results
