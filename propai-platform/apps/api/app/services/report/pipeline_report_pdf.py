"""통합 분석 보고서 PDF 생성(reportlab, 한글 CID 폰트). PipelineReport → bytes."""

from __future__ import annotations

import io
from typing import Any

from app.services.common.pdf_escape import esc as _esc


def _fmt(v: Any) -> str:
    """동적 값을 표시 문자열로. ★reportlab Paragraph 안전을 위해 항상 XML 이스케이프한다.

    이 빌더의 모든 동적 텍스트(요약·섹션 내용·리스크·중첩 dict 등)는 _fmt 를 거쳐 Paragraph 에
    들어가므로, 여기 한 곳에서 _esc 하면 '<'/'&'/'</para>' 가 섞여도 ValueError(→HTTP500) 없이
    정상 렌더된다(전역 전파방지·은폐 금지). 정적 한글 헤더는 _fmt 를 거치지 않아 무영향.
    """
    if v is None:
        return "-"
    if isinstance(v, bool):
        return _esc("예" if v else "아니오")
    if isinstance(v, (int, float)):
        try:
            return _esc(f"{v:,}" if abs(v) >= 1000 else str(v))
        except (TypeError, ValueError):
            return _esc(str(v))
    return _esc(str(v))


_STAGE_LABEL = {
    "site_analysis": "입지 분석", "design": "건축 계획", "cost": "공사비",
    "feasibility": "사업성·수지", "tax": "세금", "esg": "ESG·탄소",
}


def build_pipeline_report_pdf(report: dict[str, Any], narratives: dict[str, Any] | None = None) -> bytes:
    """통합 분석 보고서(dict) → PDF(bytes). report=PipelineReport.model_dump() 형태.
    narratives={stage:{section:text}} 제공 시 'AI 상세 해석' 섹션 추가."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        font = "HYSMyeongJo-Medium"
    except Exception:  # noqa: BLE001
        font = "Helvetica"

    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontName=font, fontSize=18, spaceAfter=4)
    h = ParagraphStyle("h", parent=ss["Heading2"], fontName=font, fontSize=12, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9.5, leading=14)
    small = ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8, textColor=colors.grey, leading=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm)
    el: list[Any] = []

    el.append(Paragraph("프로젝트 통합 분석 보고서", title))
    # project_address·generated_at 는 사용자/엔진 동적 입력이라 esc(주소에 '<','&' 가능).
    el.append(Paragraph(
        f"PropAI 사통팔땅 · {_esc(report.get('project_address', '') or '주소 미상')} · "
        f"{_esc(report.get('generated_at', ''))}", small))
    el.append(Spacer(1, 8))

    # 핵심 요약
    summ = report.get("executive_summary") or {}
    if summ:
        el.append(Paragraph("핵심 요약", h))
        # 값은 Paragraph(_fmt) 로 XML 이스케이프. 키 셀은 bare str 이라 reportlab 이 XML 파싱하지
        # 않으므로(Paragraph 만 파싱) 크래시 벡터가 아니다 — esc 불필요(무회귀).
        rows = [[str(k), Paragraph(_fmt(v), body)] for k, v in summ.items()]
        t = Table(rows, colWidths=[45 * mm, 125 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        el.append(t)

    # 섹션별
    for sec in report.get("sections", []) or []:
        no = sec.get("section_no", "")
        # section_no·title 은 엔진 산출 동적 문자열이라 esc(Paragraph 에 직접 보간되므로 필수).
        el.append(Paragraph(f"{_esc(no)}. {_esc(sec.get('title', ''))}", h))
        content = sec.get("content") or {}
        if isinstance(content, dict) and content:
            rows = []
            for k, v in content.items():
                # 중첩 dict/list는 요약 문자열로
                val = v if isinstance(v, (str, int, float, bool, type(None))) else _fmt(v)
                rows.append([str(k), Paragraph(_fmt(val), body)])
            t = Table(rows, colWidths=[45 * mm, 125 * mm])
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            el.append(t)
        else:
            el.append(Paragraph(_fmt(content), body))

    # 리스크
    risk = report.get("risk_assessment") or {}
    if risk:
        el.append(Paragraph("리스크 평가", h))
        rows = [[str(k), Paragraph(_fmt(v), body)] for k, v in risk.items()]
        t = Table(rows, colWidths=[45 * mm, 125 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ]))
        el.append(t)

    # AI 상세 해석(narratives 제공 시)
    if narratives:
        el.append(Paragraph("AI 상세 해석", h))
        for stg, secs in narratives.items():
            if not isinstance(secs, dict) or not secs:
                continue
            # stg 폴백(매핑에 없는 단계 id)도 동적이라 esc.
            el.append(Paragraph(_esc(_STAGE_LABEL.get(stg, stg)), ParagraphStyle(
                "sub", parent=body, fontName=font, fontSize=10, spaceBefore=6, spaceAfter=2, textColor=colors.HexColor("#1f2937"))))
            for k, v in secs.items():
                if isinstance(v, str) and v.strip():
                    # <b> 는 의도적 강조 마크업이라 보존하고, 그 안의 동적 k·v 만 esc(혼합 안전).
                    el.append(Paragraph(f"<b>· {_esc(k)}</b> {_esc(v.strip())}", body))

    el.append(Spacer(1, 10))
    el.append(Paragraph("※ 본 보고서는 공개데이터·AI 분석 기반 참고 자료이며, 최종 판단은 사용자가 결정합니다.", small))

    doc.build(el)
    return buf.getvalue()
