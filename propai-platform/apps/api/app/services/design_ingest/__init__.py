"""설계 도면 인제스천 모듈 — 업로드 설계파일을 DesignSpec으로 정규화하고 검색용 벡터로 적재."""

from app.services.design_ingest.composition import (
    CompositionCandidate,
    SiteContext,
    compose,
    fit_score,
    site_context_from_zone,
)
from app.services.design_ingest.design_spec import DesignSpec, RoomSpec, detect_drawing_type
from app.services.design_ingest.ingest_service import ingest_design_file
from app.services.design_ingest.orchestrator import (
    DesignRequest,
    generate_design_proposals,
)
from app.services.design_ingest.parsers import detect_format, parse_design_file
from app.services.design_ingest.search_service import (
    DrawingMatch,
    SiteQuery,
    search_drawings,
)
from app.services.design_ingest.vector_store import DESIGN_COLLECTION

__all__ = [
    "DESIGN_COLLECTION",
    "CompositionCandidate",
    "DesignRequest",
    "DesignSpec",
    "DrawingMatch",
    "RoomSpec",
    "SiteContext",
    "SiteQuery",
    "compose",
    "detect_drawing_type",
    "detect_format",
    "fit_score",
    "generate_design_proposals",
    "ingest_design_file",
    "parse_design_file",
    "search_drawings",
    "site_context_from_zone",
]
