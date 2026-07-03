"""도메인 결과 → 정본 ReportModel 어댑터.

★재구현 금지: 기존 PipelineReportService(파이프라인 10섹션 조립·산식 없음)를 재사용해
  PipelineReport 를 만든 뒤, 그것을 정본 ReportModel(디자인 무관 Block)로 '옮겨 담기'만 한다.
"""

from __future__ import annotations

from typing import Any

from .model import (
    GradeBadgeBlock,
    KPITile,
    KPITileBlock,
    KVTableBlock,
    NarrativeBlock,
    ReportMeta,
    ReportModel,
    Section,
    fmt_value,
)

# 파이프라인 단계 코드 → 사람이 읽는 라벨(기존 pipeline_report_pdf._STAGE_LABEL 재사용)
_STAGE_LABEL = {
    "site_analysis": "입지 분석", "design": "건축 계획", "cost": "공사비",
    "feasibility": "사업성·수지", "tax": "세금", "esg": "ESG·탄소",
}
# 서술(narrative) 단계를 어느 섹션 번호 밑에 붙일지
_STAGE_TO_SECTION = {
    "site_analysis": 2, "design": 3, "cost": 5, "feasibility": 7, "tax": 9, "esg": 10,
}
# 사업성 등급(LOW/MEDIUM/HIGH/VERY_HIGH 또는 A/B/C) → PRDS 등급 키
_RISK_TO_GRADE = {
    "LOW": "good", "MEDIUM": "normal", "HIGH": "caution", "VERY_HIGH": "distress",
}


def _content_to_rows(content: dict) -> list[tuple[str, Any]]:
    """섹션 content dict → K-V 행 목록. 중첩 dict 는 한 단계 펼치고, 리스트는 개수/요약."""
    rows: list[tuple[str, Any]] = []
    for k, v in content.items():
        if v is None:
            rows.append((k, None))
        elif isinstance(v, dict):
            # 빈 dict 는 정직하게 '—', 아니면 한 단계 펼침
            if not v:
                rows.append((k, None))
            for sk, sv in v.items():
                if isinstance(sv, (dict, list)):
                    continue  # 2단 이상 중첩은 생략(과밀 방지)
                rows.append((f"{k} · {sk}", sv))
        elif isinstance(v, list):
            if not v:
                rows.append((k, None))
            elif all(isinstance(x, (str, int, float)) for x in v):
                rows.append((k, ", ".join(fmt_value(x) for x in v[:8])))
            else:
                rows.append((k, f"{len(v)}건"))
        else:
            rows.append((k, v))
    return rows


def _won_to_eok(v: Any) -> str | None:
    """원 단위 큰 금액을 '억' 단위로 요약(표시용). 값 없으면 None."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n == 0:
        return None
    return f"{n / 1e8:,.1f}억원"


def _build_exec_summary(summary: dict, risk: dict) -> Section:
    """1페이지째 두괄식 요약: 등급 배지 + 결정 KPI 타일 + 권고 서술(R2)."""
    blocks: list[Any] = []

    grade = str(summary.get("grade") or "").upper()
    if grade:
        blocks.append(GradeBadgeBlock(grade=_RISK_TO_GRADE.get(grade, "normal"), label="사업성 등급"))

    # 결정 지표 3~4개(있는 것만)
    tiles: list[KPITile] = []
    pr = summary.get("profit_rate_pct")
    if pr is not None:
        tiles.append(KPITile(label="사업이익률", value=f"{fmt_value(pr)}%", basis="목표 15%+"))
    if summary.get("total_project_cost"):
        tiles.append(KPITile(label="총사업비", value=_won_to_eok(summary["total_project_cost"]) or "—"))
    if summary.get("total_revenue"):
        tiles.append(KPITile(label="총매출", value=_won_to_eok(summary["total_revenue"]) or "—"))
    prob = risk.get("probability_positive")
    if prob is not None:
        pct = prob * 100 if prob <= 1 else prob
        tiles.append(KPITile(label="수익 확률", value=f"{fmt_value(round(pct, 1))}%", basis="Monte Carlo"))
    if tiles:
        blocks.append(KPITileBlock(tiles=tiles))

    # 권고(결론-근거 직결)
    rec = risk.get("recommendation")
    decisive = []
    if pr is not None:
        decisive.append(f"사업이익률 {fmt_value(pr)}%")
    if prob is not None:
        decisive.append(f"수익확률 {fmt_value(round((prob*100 if prob<=1 else prob),1))}%")
    line = rec or ""
    if decisive:
        line = (line + "  · " if line else "") + "결정지표: " + ", ".join(decisive)
    if line:
        blocks.append(NarrativeBlock(paragraphs=[line]))

    return Section(title="심사 요약 (Deal Snapshot)", blocks=blocks)


def build_report_model_from_pipeline(pipeline_result: dict, narratives: dict | None = None) -> ReportModel:
    """파이프라인 통합분석 결과 → 정본 ReportModel."""
    # ★기존 서비스 재사용(산식 복제 0)
    from app.services.report.pipeline_report_service import PipelineReportService

    report = PipelineReportService().generate(pipeline_result)
    rd = report.model_dump()
    narratives = narratives or {}

    meta = ReportMeta(
        title="프로젝트 통합 분석 보고서",
        subtitle="사업성 검토 · 은행/투자자 제출용",
        project_address=rd.get("project_address") or "",
        generated_at=rd.get("generated_at") or "",
        doc_no=f"PROPAI-{(rd.get('report_id') or '')[:8]}" if rd.get("report_id") else None,
    )

    exec_summary = _build_exec_summary(rd.get("executive_summary") or {}, rd.get("risk_assessment") or {})

    # 단계별 서술을 섹션 번호로 인덱싱
    narr_by_section: dict[int, list[str]] = {}
    for stage, secs in narratives.items():
        if not isinstance(secs, dict):
            continue
        sec_no = _STAGE_TO_SECTION.get(stage)
        if sec_no is None:
            continue
        texts = [f"[{k}] {v.strip()}" for k, v in secs.items() if isinstance(v, str) and v.strip()]
        if texts:
            narr_by_section.setdefault(sec_no, []).extend(texts)

    sections: list[Section] = []
    for sec in rd.get("sections", []) or []:
        no = sec.get("section_no")
        blocks: list[Any] = []
        rows = _content_to_rows(sec.get("content") or {})
        if rows:
            blocks.append(KVTableBlock(rows=rows))
        # 해당 단계 AI 서술 부착
        if no in narr_by_section:
            blocks.append(NarrativeBlock(title="AI 상세 해석", paragraphs=narr_by_section[no]))
        sections.append(Section(section_no=no, title=sec.get("title", ""), blocks=blocks))

    # 리스크 평가 섹션(마지막)
    risk = rd.get("risk_assessment") or {}
    if risk:
        rrows = _content_to_rows(risk)
        risk_grade = _RISK_TO_GRADE.get(str(risk.get("risk_grade", "")).upper(), "normal")
        next_no = (sections[-1].section_no or 10) + 1 if sections else 11
        sections.append(Section(
            section_no=next_no,
            title="리스크 평가",
            blocks=[
                GradeBadgeBlock(grade=risk_grade, label="종합 리스크"),
                KVTableBlock(rows=rrows),
            ],
        ))

    return ReportModel(meta=meta, sections=sections, exec_summary=exec_summary)
