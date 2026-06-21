"""설계파일 인제스천 오케스트레이션.

업로드 → 파싱(DesignSpec) → content_hash 중복제거 → 임베딩 → Qdrant(design_drawings)
업서트 → 성장 이벤트(capture). 임베딩/Qdrant 실패는 본 기능을 깨지 않고 정직 고지한다
(indexed=False). 원문 바이트는 벡터DB에 저장하지 않는다(메타·요약만).
"""

from __future__ import annotations

import logging

from app.services.design_ingest.design_spec import DesignSpec
from app.services.design_ingest.parsers import parse_design_file_async
from app.services.design_ingest.vector_store import (
    DESIGN_COLLECTION,
    EMBED_DIM,
    embed_text,
)

logger = logging.getLogger(__name__)


def _index(
    spec: DesignSpec, vector: list[float], project_id: str | None, tenant_id: str | None
) -> tuple[bool, str | None]:
    """Qdrant design_drawings에 멱등 업서트(point_id=content_hash 기반). 반환: (성공, 실패사유)."""
    try:
        from qdrant_client.http.models import PointStruct

        from apps.api.database.init_qdrant import get_qdrant_client

        payload = spec.to_payload()
        payload["project_id"] = project_id
        payload["tenant_id"] = tenant_id
        client = get_qdrant_client()
        client.upsert(
            collection_name=DESIGN_COLLECTION,
            # ★point_id에 tenant_id 결합 — 교차테넌트 멱등 덮어쓰기(소유표시 탈취) 차단.
            points=[
                PointStruct(
                    id=spec.point_id(tenant_id=tenant_id), vector=vector, payload=payload
                )
            ],
        )
        return True, None
    except Exception as e:  # noqa: BLE001
        logger.warning("design_ingest Qdrant 업서트 실패: %s", str(e)[:120])
        return False, "qdrant_error"


async def ingest_design_file(
    *,
    filename: str,
    content: bytes,
    project_id: str | None = None,
    tenant_id: str | None = None,
) -> dict:
    """설계파일 1건 인제스천. 항상 DesignSpec 요약을 반환하고, 인덱싱 여부는 정직 표기.

    Returns: {ok, drawing_type, source_format, content_hash, indexed, spec, warnings}
    """
    spec = await parse_design_file_async(content, filename)

    indexed = False
    index_skip_reason: str | None = None
    vector, embed_reason = await embed_text(spec.to_embedding_text())
    if vector is not None and len(vector) == EMBED_DIM:
        indexed, index_skip_reason = _index(spec, vector, project_id, tenant_id)
    elif vector is not None:
        index_skip_reason = "embed_dim_mismatch"
    else:
        index_skip_reason = embed_reason

    # 성장 루프 신호(capture) — PII 미포함(파일명 제외 메타만), 논블로킹.
    try:
        from app.services.growth.capture_service import record_event

        # 도메인 메타는 payload 아래로(capture 화이트리스트 규약 — 평면 키는 폐기됨).
        record_event(
            "design_ingest",
            {
                "service": "design_ingest",
                "tenant_id": tenant_id,
                "payload": {
                    "drawing_type": spec.drawing_type,
                    "source_format": spec.source_format,
                    "indexed": indexed,
                    "content_hash": spec.content_hash(),
                    "has_area": spec.total_area_sqm is not None,
                    "project_id": project_id,
                },
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("design_ingest capture 생략: %s", str(e)[:120])

    return {
        "ok": True,
        "drawing_type": spec.drawing_type,
        "source_format": spec.source_format,
        "content_hash": spec.content_hash(),
        "indexed": indexed,
        # 미인덱싱 사유(정직 구분): no_openai_key|embed_error|embed_dim_mismatch|qdrant_error|None
        "index_skip_reason": index_skip_reason,
        "warnings": spec.meta.get("warnings", []),
        "spec": spec.to_payload(),
    }
