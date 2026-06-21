"""설계 도면 검색 — 부지조건으로 design_drawings 컬렉션에서 유사 도면 Top-K 검색.

인제스트(ingest_service)가 적재한 벡터를 읽어, 부지 조건(용도지역·면적·도면종류·키워드)에
맞는 도면을 코사인 유사도로 검색한다. 검색+조합(retrieval+composition)의 '검색' 절반.
임베딩/Qdrant 미가용 시 빈 결과+사유로 정직 degrade(예외 비전파).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.design_ingest.vector_store import (
    DESIGN_COLLECTION,
    EMBED_DIM,
    embed_text,
)

logger = logging.getLogger(__name__)


@dataclass
class SiteQuery:
    """검색 입력(부지 조건). 지정된 값만 필터/질의에 반영(미지정은 무제약)."""

    drawing_type: str | None = None   # site_plan|floor_plan|section|elevation|parking
    zone_type: str | None = None      # 용도지역(질의 텍스트에만 반영)
    area_sqm: float | None = None     # 면적 — 질의텍스트(임베딩)에 항상 반영
    area_tolerance_pct: float = 30.0
    # 면적 하드필터(±tolerance Range). 기본 False — 켜면 면적메타 없는(None) 도면이
    # 결과에서 제외되므로(침묵 누락 방지) 호출부가 의도적으로만 활성화한다.
    area_hard_filter: bool = False
    keywords: str = ""
    tenant_id: str | None = None      # 멀티테넌트 격리(지정 시 동일 tenant만)
    project_id: str | None = None

    def to_query_text(self) -> str:
        """임베딩 질의 텍스트(존재하는 값만)."""
        parts: list[str] = []
        if self.drawing_type:
            parts.append(f"도면종류:{self.drawing_type}")
        if self.zone_type:
            parts.append(f"용도지역:{self.zone_type}")
        if self.area_sqm is not None:
            parts.append(f"면적:{self.area_sqm}㎡")
        if self.keywords:
            parts.append(self.keywords)
        return " ".join(parts) or "설계 도면"


@dataclass
class DrawingMatch:
    """검색 결과 1건."""

    point_id: str
    score: float
    drawing_type: str | None = None
    title: str | None = None
    total_area_sqm: float | None = None
    source_format: str | None = None
    summary: str | None = None

    @classmethod
    def from_scored(cls, point: object) -> DrawingMatch:
        """Qdrant ScoredPoint → DrawingMatch(payload 안전 추출)."""
        payload = getattr(point, "payload", None) or {}
        return cls(
            point_id=str(getattr(point, "id", "")),
            score=round(float(getattr(point, "score", 0.0) or 0.0), 4),
            drawing_type=payload.get("drawing_type"),
            title=payload.get("title"),
            total_area_sqm=payload.get("total_area_sqm"),
            source_format=payload.get("source_format"),
            summary=(payload.get("summary") or "")[:300] or None,
        )

    def to_dict(self) -> dict:
        return {
            "point_id": self.point_id,
            "score": self.score,
            "drawing_type": self.drawing_type,
            "title": self.title,
            "total_area_sqm": self.total_area_sqm,
            "source_format": self.source_format,
            "summary": self.summary,
        }


def _build_filter(q: SiteQuery):
    """SiteQuery → Qdrant Filter(must 조건). 조건 없으면 None."""
    from qdrant_client.http.models import FieldCondition, Filter, MatchValue, Range

    must: list = []
    if q.drawing_type:
        must.append(FieldCondition(key="drawing_type", match=MatchValue(value=q.drawing_type)))
    if q.tenant_id:
        must.append(FieldCondition(key="tenant_id", match=MatchValue(value=q.tenant_id)))
    # 면적 하드필터는 명시 활성화 시에만(면적 None 도면 침묵 누락 방지). 평소엔 임베딩으로 소프트 반영.
    if q.area_hard_filter and q.area_sqm is not None and q.area_sqm > 0:
        tol = max(0.0, q.area_tolerance_pct) / 100.0
        must.append(
            FieldCondition(
                key="total_area_sqm",
                range=Range(gte=q.area_sqm * (1 - tol), lte=q.area_sqm * (1 + tol)),
            )
        )
    return Filter(must=must) if must else None


async def search_drawings(query: SiteQuery, top_k: int = 5) -> dict:
    """부지조건으로 유사 도면 Top-K 검색.

    Returns: {ok, results: [DrawingMatch dict], count, skipped_reason}
    skipped_reason: no_openai_key|embed_error|embed_dim_mismatch|qdrant_error|None.

    ★보안: 멀티테넌트 격리를 위해 호출부(라우터)는 query.tenant_id를 클라이언트 입력이 아니라
    인증된 사용자 컨텍스트에서 강제 주입해야 한다(미지정 시 전역검색 — 관리자 전용으로 제한).
    """
    vector, reason = await embed_text(query.to_query_text())
    if vector is None:
        return {"ok": True, "results": [], "count": 0, "skipped_reason": reason}
    if len(vector) != EMBED_DIM:
        return {"ok": True, "results": [], "count": 0, "skipped_reason": "embed_dim_mismatch"}

    try:
        from apps.api.database.init_qdrant import get_qdrant_client

        client = get_qdrant_client()
        # query_points(1.10+)는 deprecated search 대비 포워드호환. 응답의 .points가 결과.
        resp = client.query_points(
            collection_name=DESIGN_COLLECTION,
            query=vector,
            query_filter=_build_filter(query),
            limit=max(1, top_k),
            with_payload=True,
        )
        hits = getattr(resp, "points", None) or []
    except Exception as e:  # noqa: BLE001
        logger.warning("design 검색 실패: %s", str(e)[:120])
        return {"ok": True, "results": [], "count": 0, "skipped_reason": "qdrant_error"}

    matches = [DrawingMatch.from_scored(h).to_dict() for h in hits]
    return {"ok": True, "results": matches, "count": len(matches), "skipped_reason": None}
