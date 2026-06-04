"""예상 탁상감정서 PDF 생성(reportlab, 한글 CID 폰트). 정식 감정평가서 아님(참고용)."""

from __future__ import annotations

import io
from typing import Any


def build_desk_appraisal_pdf(result: dict[str, Any], *, address: str = "") -> bytes:
    """desk_appraisal 결과 dict → 탁상감정서 PDF(bytes)."""
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

    def won(v: Any) -> str:
        try:
            return f"{int(v):,}원"
        except (TypeError, ValueError):
            return "-"

    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontName=font, fontSize=18, spaceAfter=4)
    h = ParagraphStyle("h", parent=ss["Heading2"], fontName=font, fontSize=12, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9.5, leading=14)
    small = ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8, textColor=colors.grey, leading=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm)
    el: list[Any] = []

    el.append(Paragraph("토지 예상가치 추정 리포트", title))
    el.append(Paragraph("PropAI 사통팔땅 — 공시지가·실거래 기반 참고용 시세 추정 (감정평가 아님)", small))
    el.append(Spacer(1, 8))

    cc = result.get("cross_check") or {}
    area = result.get("area_sqm")
    rng = result.get("range_per_sqm") or {}

    # 1. 대상 / 결론
    summary_rows = [
        ["소재지", address or "-"],
        ["대지면적", f"{area:,}㎡" if area else "-"],
        ["채택 추정단가", won(result.get("appraised_price_per_sqm")) + "/㎡"],
        ["채택 추정가(총액)", won(result.get("appraised_total_won"))],
        ["신뢰도", f"{int((result.get('confidence') or 0) * 100)}%"],
        ["신뢰구간(/㎡)", f"{won(rng.get('low'))} ~ {won(rng.get('high'))}"],
    ]
    el.append(Paragraph("1. 추정 요약", h))
    t1 = Table(summary_rows, colWidths=[40 * mm, 130 * mm])
    t1.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("BACKGROUND", (1, 2), (1, 3), colors.HexColor("#eef2ff")),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(t1)

    # 2. 방법별 산출
    el.append(Paragraph("2. 산정방법별 추정", h))
    mrows = [["산정방법", "추정 단가(/㎡)", "근거"]]
    for m in result.get("methods", []):
        mrows.append([m.get("method", "-"), won(m.get("unit_price")) , Paragraph(str(m.get("rationale", "")), small)])
    t2 = Table(mrows, colWidths=[35 * mm, 35 * mm, 100 * mm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(t2)
    el.append(Paragraph(result.get("weight_note", ""), small))

    # 3. 다법인 교차검증
    if cc.get("firms"):
        el.append(Paragraph("3. 복수 시나리오 교차검증", h))
        firms = cc["firms"]
        frows = [["시나리오" + str(i + 1) for i in range(len(firms))] + ["평균", "편차(CV)"]]
        frows.append([won(v) for v in firms] + [won(cc.get("mean")), f"{cc.get('cv_pct')}%"])
        t3 = Table(frows)
        t3.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("BACKGROUND", (-2, 1), (-1, 1), colors.HexColor("#eef2ff")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        el.append(t3)
        el.append(Paragraph(cc.get("note", ""), small))

    # 4. 면책
    el.append(Spacer(1, 10))
    el.append(Paragraph("※ 면책 (본 문서는 감정평가서가 아님)", h))
    el.append(Paragraph(result.get("disclaimer", ""), small))

    doc.build(el)
    return buf.getvalue()
