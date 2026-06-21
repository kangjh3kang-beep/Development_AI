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
from app.services.design_ingest.law_coverage import (
    DESIGN_LAW_MAP,
    all_referenced_laws,
    laws_for,
    verify_coverage,
)
from app.services.design_ingest.orchestrator import (
    DesignRequest,
    generate_design_proposals,
)
from app.services.design_ingest.parsers import detect_format, parse_design_file
from app.services.design_ingest.provenance import (
    Evidence,
    legal_envelope_evidence,
    permit_evidence,
    proposal_evidence,
)
from app.services.design_ingest.search_service import (
    DrawingMatch,
    SiteQuery,
    search_drawings,
)
from app.services.design_ingest.vector_store import DESIGN_COLLECTION

__all__ = [
    "DESIGN_COLLECTION",
    "DESIGN_LAW_MAP",
    "CompositionCandidate",
    "DesignRequest",
    "DesignSpec",
    "DrawingMatch",
    "Evidence",
    "RoomSpec",
    "SiteContext",
    "SiteQuery",
    "all_referenced_laws",
    "compose",
    "detect_drawing_type",
    "detect_format",
    "fit_score",
    "generate_design_proposals",
    "ingest_design_file",
    "laws_for",
    "legal_envelope_evidence",
    "parse_design_file",
    "permit_evidence",
    "proposal_evidence",
    "search_drawings",
    "site_context_from_zone",
    "verify_coverage",
]
