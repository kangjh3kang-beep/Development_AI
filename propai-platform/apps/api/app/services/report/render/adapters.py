"""도메인 결과 → 정본 ReportModel 어댑터.

★재구현 금지: 기존 PipelineReportService(파이프라인 10섹션 조립·산식 없음)를 재사용해
  PipelineReport 를 만든 뒤, 그것을 정본 ReportModel(디자인 무관 Block)로 '옮겨 담기'만 한다.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .evidence_bridge import evidence_block_from_contract
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


def _pipeline_site_evidence(pipeline_result: dict) -> Any:
    """stages.site_analysis.data 의 표준 근거 계약(evidence[]/legal_refs[]) → EvidenceBlock.

    파이프라인은 _attach_site_trust_blocks 가 부지분석 stage data 에 evidence/legal_refs 를
    이미 부착해 둔다(가정값 부지는 빈 배열 — 그 경우 여기서도 None → 섹션 미부착·정직).
    stages 는 dict({stage: entry}) 또는 list([entry,...]) 두 직렬화 형태를 모두 허용한다.
    """
    stages = pipeline_result.get("stages")
    entry = None
    if isinstance(stages, dict):
        entry = stages.get("site_analysis")
    elif isinstance(stages, list):
        entry = next((s for s in stages
                      if isinstance(s, dict) and s.get("stage") == "site_analysis"), None)
    if not isinstance(entry, dict):
        return None
    # StageResult 직렬화({"stage":..,"data":{..}}) 또는 flat dict 모두 대응(_extract_data와 동일 규칙).
    data = entry["data"] if isinstance(entry.get("data"), dict) else entry
    return evidence_block_from_contract(
        {"evidence": data.get("evidence"), "legal_refs": data.get("legal_refs")}, title=None)


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

    # 부지분석 근거·법령 링크(표준 계약) — 실데이터가 있을 때만 입지분석 섹션에 부착(정직).
    site_evidence = _pipeline_site_evidence(pipeline_result)

    sections: list[Section] = []
    for sec in rd.get("sections", []) or []:
        no = sec.get("section_no")
        blocks: list[Any] = []
        rows = _content_to_rows(sec.get("content") or {})
        if rows:
            blocks.append(KVTableBlock(rows=rows))
        # 입지분석 섹션(2)에 산출 근거·법령 링크 부착(stage data 의 표준 계약 그대로 — 산식 0)
        # 복사본으로 부착 — 여러 섹션이 매칭돼도 같은 가변 객체를 공유하지 않게 한다(dataclass).
        if site_evidence is not None and no == _STAGE_TO_SECTION["site_analysis"]:
            blocks.append(dataclasses.replace(site_evidence, title="산출 근거·법령 링크"))
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


def build_report_model_from_bank(bank_result: dict) -> ReportModel:
    """은행제출용 사업성 보고서(BankReadyReportService.generate_report dict) → 정본 ReportModel.

    ★재구현 금지: 기존 서비스가 만든 10섹션 dict(meta/sections/completeness)를 Block 으로 옮겨 담기만.
      섹션 제목에 이미 번호가 있어(예 '1. 사업개요') section_no 는 비운다(이중 번호 방지).
    ※ 근거 블록: BankReadyReportService 결과에는 표준 evidence/legal_refs 계약이 없어
      EvidenceBlock 을 부착하지 않는다(가짜 근거 생성 금지 — 서비스가 계약을 붙이면 자동 소비 가능).
    """
    meta_d = bank_result.get("meta") or {}
    comp = bank_result.get("completeness") or {}
    meta = ReportMeta(
        title=meta_d.get("title") or "사업성 분석 보고서",
        subtitle="은행 PF 대출 심사 제출용",
        generated_at=meta_d.get("generated_at") or "",
        completeness=comp if comp else None,
        confidential=True,
    )

    sections: list[Section] = []
    for sec in bank_result.get("sections") or []:
        blocks: list[Any] = []
        rows = _content_to_rows(sec.get("content") or {})
        if rows:
            blocks.append(KVTableBlock(rows=rows))
        # 데이터 미확보 섹션은 정직 고지(빈 섹션 은폐 금지)
        if not sec.get("has_data"):
            blocks.append(NarrativeBlock(paragraphs=["※ 이 섹션은 데이터 일부 미확보 상태입니다(정직 고지)."]))
        sections.append(Section(section_no=None, title=sec.get("title", ""), blocks=blocks))

    return ReportModel(meta=meta, sections=sections, disclaimer=meta_d.get("legal_disclaimer"))
