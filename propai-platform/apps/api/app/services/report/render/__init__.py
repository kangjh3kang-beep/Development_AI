"""통합 보고서 생성엔진(render) 패키지.

하나의 정본 보고서 모델(``model.ReportModel``)을 만들어 PDF·PPTX·DOCX 세 포맷으로
'동일한' 디자인(``tokens`` = PRDS 디자인 시스템)으로 렌더한다.

핵심 원칙(★재구현 금지):
- 이 패키지는 '표현(렌더링)'만 담당한다. 사업성·세금·용적률 같은 **산식은 절대 여기서 계산하지 않는다**.
  도메인 서비스가 계산한 값을 ``ReportModel`` 로 '조립'만 받는다.
- DB·FastAPI에 의존하지 않는다(reportlab/python-pptx/python-docx + 표준 라이브러리만).
  덕분에 서버 없이도 스모크 테스트로 실파일을 뽑아 육안 검증할 수 있다.

사용 예:
    from app.services.report.render import build_report_model_from_pipeline, render_report
    model = build_report_model_from_pipeline(pipeline_result, narratives)
    data, media_type, ext = render_report(model, "pptx")
"""

from __future__ import annotations

from .model import (
    Block,
    ChartBlock,
    ChecklistBlock,
    DataTableBlock,
    DisclaimerBlock,
    Evidence,
    EvidenceBlock,
    GradeBadgeBlock,
    ImageBlock,
    KPITile,
    KPITileBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    Series,
)

__all__ = [
    "Block",
    "ChartBlock",
    "ChecklistBlock",
    "DataTableBlock",
    "DisclaimerBlock",
    "Evidence",
    "EvidenceBlock",
    "GradeBadgeBlock",
    "ImageBlock",
    "KPITile",
    "KPITileBlock",
    "KVTableBlock",
    "NarrativeBlock",
    "ReportMeta",
    "ReportModel",
    "Section",
    "Series",
    "render_report",
    "build_report_model_from_pipeline",
    "build_report_model_from_persona",
]


def render_report(model: ReportModel, fmt: str = "pdf") -> tuple[bytes, str, str]:
    """정본 모델을 원하는 포맷으로 렌더. 반환=(파일 bytes, MIME 타입, 확장자).

    지연 임포트: 렌더러가 각자 무거운 라이브러리(reportlab/pptx/docx)를 쓰므로 필요할 때만 로드.
    """
    from .engine import render_report as _render

    return _render(model, fmt)


def build_report_model_from_pipeline(pipeline_result: dict, narratives: dict | None = None) -> ReportModel:
    """파이프라인 통합분석 결과(dict) → 정본 ReportModel 로 조립(어댑터).

    기존 PipelineReportService 의 10섹션 로직을 재사용한다(산식 복제 0)."""
    from .adapters import build_report_model_from_pipeline as _build

    return _build(pipeline_result, narratives)


def build_report_model_from_persona(report: dict, key: str) -> ReportModel:
    """페르소나(도시/디벨로퍼/시공/설계) 분석 결과 → 정본 ReportModel(어댑터).

    4개 클론 *_report.to_pdf 를 통합 — 엔진이 PDF/PPTX/DOCX 를 같은 디자인으로 생성."""
    from .persona_adapter import build_report_model_from_persona as _build

    return _build(report, key)
