"""통합 분석 보고서 PDF 생성(reportlab, 한글 CID 폰트). PipelineReport → bytes."""

from __future__ import annotations

import io
from typing import Any


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int, float)):
        try:
            return f"{v:,}" if abs(v) >= 1000 else str(v)
        except (TypeError, ValueError):
            return str(v)
    return str(v)


def build_pipeline_report_pdf(report: dict[str, Any]) -> bytes:
    """통합 분석 보고서(dict) → PDF(bytes). report=PipelineReport.model_dump() 형태."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

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
    el.append(Paragraph(
        f"PropAI 사통팔땅 · {report.get('project_address', '') or '주소 미상'} · {report.get('generated_at', '')}", small))
    el.append(Spacer(1, 8))

    # 핵심 요약
    summ = report.get("executive_summary") or {}
    if summ:
        el.append(Paragraph("핵심 요약", h))
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
        el.append(Paragraph(f"{no}. {sec.get('title', '')}", h))
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

    el.append(Spacer(1, 10))
    el.append(Paragraph("※ 본 보고서는 공개데이터·AI 분석 기반 참고 자료이며, 최종 판단은 사용자가 결정합니다.", small))

    doc.build(el)
    return buf.getvalue()
