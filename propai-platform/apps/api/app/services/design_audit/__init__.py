"""설계심사(Design Audit) 서비스 패키지 — U5 백엔드 1단계.

- DA-1 brief_extractor            : PDF 텍스트 추출(PyMuPDF) + 설계개요 필드 구조화
  (DesignBriefInterpreter — {value, quote, confidence}, LLM 실패 시 한국어 라벨 정규식 폴백).
- DA-2 geometry_adapter           : IFC(BIMIFCService 재사용)/CAD 도형 → 설계 파라미터,
  출처 병합(user > ifc > brief, 5%+ 괴리 conflicts[]).
- DA-3 design_audit_orchestrator  : 조례 실효한도 선행 + 8엔진 병렬 심사 +
  AuditFinding 정규화 + 결정론 종합판정(fail→부적합, warning→조건부적합) +
  리포트 S섹션 원자료(s1_samples·s4_incentives·efficiency_metrics).
"""

from app.services.design_audit.brief_extractor import (
    BRIEF_FIELDS,
    DesignBriefInterpreter,
    extract_brief,
    extract_text_from_pdf,
    parse_brief_rule_based,
)
from app.services.design_audit.design_audit_orchestrator import (
    ENGINE_NAMES,
    DesignAuditOrchestrator,
    design_audit_orchestrator,
    make_finding,
    run_design_audit,
)
from app.services.design_audit.geometry_adapter import (
    design_payload_from_shapes,
    merge_params,
    params_from_ifc,
)

__all__ = [
    "BRIEF_FIELDS",
    "DesignBriefInterpreter",
    "extract_brief",
    "extract_text_from_pdf",
    "parse_brief_rule_based",
    "ENGINE_NAMES",
    "DesignAuditOrchestrator",
    "design_audit_orchestrator",
    "make_finding",
    "run_design_audit",
    "design_payload_from_shapes",
    "merge_params",
    "params_from_ifc",
]
