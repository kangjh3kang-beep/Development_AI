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
    "build_report_model_from_bank",
    "build_report_model_from_land",
    "build_report_model_from_appraisal",
    "build_report_model_from_appraisal_multi",
    "build_report_model_from_design_audit",
    "build_report_model_from_cost_estimation",
    "build_report_model_from_regulation",
    "build_report_model_from_market",
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


def build_report_model_from_bank(bank_result: dict) -> ReportModel:
    """은행제출용 사업성 보고서(BankReadyReportService dict) → 정본 ReportModel(어댑터).

    프론트 window.print(HTML 인쇄)를 서버 PDF/PPTX/DOCX 로 대체."""
    from .adapters import build_report_model_from_bank as _build

    return _build(bank_result)


def build_report_model_from_land(data: dict) -> ReportModel:
    """다필지 토지분석보고서(land) → 정본 ReportModel(어댑터). 기존 build_land_analysis_report 이관."""
    from .land_adapter import build_report_model_from_land as _build

    return _build(data)


def build_report_model_from_appraisal(data: dict, **kwargs) -> ReportModel:
    """탁상감정 보고서(appraisal) → 정본 ReportModel(어댑터). 기존 build_desk_appraisal_pdf 이관."""
    from .appraisal_adapter import build_report_model_from_appraisal as _build

    return _build(data, **kwargs)


def build_report_model_from_appraisal_multi(
    results: list, *, addresses: list, ai_sections: dict | None = None, omitted_count: int = 0
) -> ReportModel:
    """다필지 탁상감정 보고서(appraisal) → 정본 ReportModel(어댑터).

    대표(첫 성공) 필지 단건 상세 + 맨 앞 '0. 다필지 추정 총괄' 섹션(additive)."""
    from .appraisal_adapter import build_report_model_from_appraisal_multi as _build

    return _build(results, addresses=addresses, ai_sections=ai_sections, omitted_count=omitted_count)


def build_report_model_from_design_audit(data: dict) -> ReportModel:
    """설계심사 보고서(design_audit) → 정본 ReportModel(어댑터). 기존 build_design_audit_pdf 이관."""
    from .design_audit_adapter import build_report_model_from_design_audit as _build

    return _build(data)


def build_report_model_from_cost_estimation(data: dict) -> ReportModel:
    """적산(공사비 견적) 결과 → 정본 ReportModel(어댑터). 가용 산출만 조립(부재 섹션 생략)."""
    from .cost_estimation_adapter import build_report_model_from_cost_estimation as _build

    return _build(data)


def build_report_model_from_regulation(result: dict, *, address: str = "") -> ReportModel:
    """규제 종합 분석(regulation) 결과 → 정본 ReportModel(어댑터·법규 검토서).

    프론트가 방금 받은 result 를 그대로 넘겨(재분석·LLM 재호출 0) 법규 검토서로 조립한다."""
    from .regulation_adapter import build_report_model_from_regulation as _build

    return _build(result, address=address)


def build_report_model_from_market(report: dict) -> ReportModel:
    """시장조사보고서(market_report_service) 결과 → 정본 ReportModel(어댑터).

    기존 MarketReportService.to_pdf/to_pptx/to_docx 가 각자 재구현하던 표지·Executive Summary·
    8섹션 구성을 이 어댑터로 일원화한다(산식 복제 0 — report dict 값을 그대로 조립)."""
    from .market_adapter import build_report_model_from_market as _build

    return _build(report)
