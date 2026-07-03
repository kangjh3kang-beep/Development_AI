"""PDF 저수준 부품(reportlab) — PRDS 토큰을 reportlab 색/스타일로 변환한 공용 헬퍼.

★기존 pipeline_report_pdf.py 의 검증된 패턴(HYSMyeongJo 등록·KV TableStyle·_fmt)을 이 한 곳으로
  추출·승격한다. 8개 PDF 생산자가 각자 복제하던 보일러플레이트를 여기로 수렴(grep count=1 목표).
"""

from __future__ import annotations

from typing import Any

from . import tokens as T
from .model import fmt_value


def _c(hex_str: str):
    """'#0e7490' → reportlab Color."""
    from reportlab.lib.colors import HexColor

    return HexColor(hex_str)


def _esc(s: Any) -> str:
    """reportlab Paragraph 는 & < > 를 XML 로 해석 → 사용자 문자열은 반드시 이스케이프(기존 함정)."""
    return (
        fmt_value(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def register_font() -> str:
    """한글 CID 명조 등록. 실패하면 Helvetica 폴백. 반환=사용할 폰트명."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    try:
        pdfmetrics.registerFont(UnicodeCIDFont(T.FONT_KR_SERIF_PDF))
        return T.FONT_KR_SERIF_PDF
    except Exception:  # noqa: BLE001  # 폰트 미가용 환경이면 라틴 폴백
        return T.FONT_FALLBACK


def styles(font: str) -> dict:
    """PRDS 타이포 스케일 → reportlab ParagraphStyle 묶음."""
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    ss = getSampleStyleSheet()

    def mk(name: str, key: str, parent: str, color: str = T.INK) -> ParagraphStyle:
        size, leading, bold = T.TYPE[key]
        return ParagraphStyle(
            name, parent=ss[parent], fontName=font, fontSize=size,
            leading=leading, textColor=_c(color),
            spaceBefore=6 if key in ("h2", "h3") else 0,
            spaceAfter=4 if key in ("h1", "h2", "h3") else 2,
        )

    return {
        "title": mk("prds_title", "title", "Title", T.INK),
        "h1": mk("prds_h1", "h1", "Heading1", T.BRAND),
        "h2": mk("prds_h2", "h2", "Heading2", T.BRAND),
        "h3": mk("prds_h3", "h3", "Heading3", T.INK),
        "body": mk("prds_body", "body", "Normal", T.INK),
        "caption": mk("prds_caption", "caption", "Normal", T.MUTED),
        "disclaimer": mk("prds_disc", "disclaimer", "Normal", T.MUTED),
        "kpi_value": mk("prds_kpi_v", "kpi_value", "Normal", T.INK),
        "kpi_label": mk("prds_kpi_l", "kpi_label", "Normal", T.MUTED),
    }


def data_table(headers: list[str], rows: list[list[Any]], font: str,
               numeric_cols: list[int] | None = None, total_row: bool = False,
               col_widths: list[float] | None = None):
    """일반 데이터표. 헤더=딥틸 배경 흰 굵게, 행 교대 zebra, 숫자열 우측정렬."""
    from reportlab.platypus import Paragraph, Table, TableStyle

    numeric_cols = numeric_cols or []
    st = styles(font)
    body = st["body"]
    header_cells = [Paragraph(f"<b>{_esc(h)}</b>", _header_cell_style(body)) for h in headers]
    body_rows = [[Paragraph(_esc(v), body) for v in r] for r in rows]
    data = [header_cells, *body_rows]

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), T.TYPE["table"][0]),
        ("BACKGROUND", (0, 0), (-1, 0), _c(T.BRAND)),
        ("TEXTCOLOR", (0, 0), (-1, 0), _c(T.WHITE)),
        ("GRID", (0, 0), (-1, -1), 0.4, _c(T.LINE)),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_c(T.WHITE), _c(T.ZEBRA)]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    for c in numeric_cols:
        style.append(("ALIGN", (c, 1), (c, -1), "RIGHT"))
    if total_row and body_rows:
        style += [
            ("LINEABOVE", (0, -1), (-1, -1), 1.0, _c(T.INK)),
            ("FONTNAME", (0, -1), (-1, -1), font),
            ("BACKGROUND", (0, -1), (-1, -1), _c(T.PANEL)),
        ]
    t.setStyle(TableStyle(style))
    return t


def _header_cell_style(base):
    """헤더 셀용 흰색 스타일(라이브러리 임포트 최소화 위해 파생)."""
    from reportlab.lib.styles import ParagraphStyle

    return ParagraphStyle("prds_hdr_white", parent=base, textColor=_c(T.WHITE))


def kv_table(rows: list[tuple[str, Any]], font: str):
    """키-값 2열표. 라벨열 55mm(zebra 배경·굵게)+값열 125mm."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    st = styles(font)
    body = st["body"]
    data = [[Paragraph(f"<b>{_esc(k)}</b>", body), Paragraph(_esc(v), body)] for k, v in rows]
    t = Table(data, colWidths=[T.PAGE["kv_label_mm"] * mm, T.PAGE["kv_value_mm"] * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), T.TYPE["table"][0]),
        ("GRID", (0, 0), (-1, -1), 0.4, _c(T.LINE)),
        ("BACKGROUND", (0, 0), (0, -1), _c(T.ZEBRA)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def kpi_row(tiles: list, font: str):
    """KPI 타일 행(3~4열). 각 타일=라벨(작게)+수치(크게·임계 신호색)+기준(작게)."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Table, TableStyle

    st = styles(font)
    n = max(1, len(tiles))
    col_w = T.PAGE["body_w_mm"] * mm / n

    cells = []
    for tile in tiles:
        vcolor = tile.signal or T.INK
        vstyle = ParagraphStyle("kpi_v", parent=st["kpi_value"], textColor=_c(vcolor), alignment=1)
        lstyle = ParagraphStyle("kpi_l", parent=st["kpi_label"], alignment=1)
        inner = [Paragraph(_esc(tile.label), lstyle), Paragraph(_esc(tile.value), vstyle)]
        if tile.basis:
            inner.append(Paragraph(_esc(tile.basis), ParagraphStyle("kpi_b", parent=st["caption"], alignment=1)))
        cells.append(inner)

    t = Table([cells], colWidths=[col_w] * n)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, _c(T.LINE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, _c(T.LINE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, -1), _c(T.WHITE)),
    ]))
    return t


def grade_badge(grade: str, label: str | None, font: str):
    """등급 배지(양호/보통/유의/부실우려) — tint 배경 + 진한 텍스트."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    gs = T.grade_style(grade)
    st = styles(font)
    text = f"{label + '  ' if label else ''}<b>{_esc(gs['label'])}</b>"
    pstyle = ParagraphStyle("badge", parent=st["body"], textColor=_c(gs["fg"]))
    t = Table([[Paragraph(text, pstyle)]], colWidths=None)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _c(gs["bg"])),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return t


def vector_chart(block, font: str):
    """벡터 차트(R6): bar/line/pie 는 reportlab.graphics 직렌더. 나머지는 None(호출부가 PNG 폴백)."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib.units import mm

    w = T.PAGE["body_w_mm"] * mm
    h = 70 * mm
    d = Drawing(w, h)
    series_colors = [_c(x) for x in T.SERIES_COLORS]

    if block.chart_type in ("bar", "line"):
        chart = VerticalBarChart() if block.chart_type == "bar" else HorizontalLineChart()
        chart.x, chart.y, chart.width, chart.height = 24, 20, w - 48, h - 40
        chart.data = [s.values for s in block.series] or [[]]
        chart.categoryAxis.categoryNames = [str(c) for c in block.categories]
        chart.categoryAxis.labels.fontName = font
        chart.categoryAxis.labels.fontSize = 7
        chart.valueAxis.labels.fontName = font
        chart.valueAxis.labels.fontSize = 7
        for i, _s in enumerate(block.series):
            col = series_colors[i % len(series_colors)]
            if block.chart_type == "bar":
                chart.bars[i].fillColor = col
            else:
                chart.lines[i].strokeColor = col
        d.add(chart)
    elif block.chart_type == "pie":
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = w / 2 - 45, 8, 90, 90
        vals = block.series[0].values if block.series else []
        pie.data = vals or [1]
        pie.labels = [str(c) for c in block.categories] or [""]
        for i in range(len(pie.data)):
            pie.slices[i].fillColor = series_colors[i % len(series_colors)]
            pie.slices[i].fontName = font
            pie.slices[i].fontSize = 7
        d.add(pie)
    else:
        return None
    d.add(String(0, h - 12, block.title, fontName=font, fontSize=T.TYPE["h3"][0], fillColor=_c(T.INK)))
    return d


def footer_callback(meta):
    """모든 페이지 하단에 페이지번호·기밀·문서ID·작성일. reportlab onPage 콜백."""

    def _draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(T.FONT_FALLBACK, 7.5)
        canvas.setFillColor(_c(T.MUTED))
        from reportlab.lib.units import mm

        y = 8 * mm
        left = f"{T.BRANDING}"
        if meta.confidential:
            left += f"   ·   {T.CONFIDENTIAL_LABEL}"
        right_parts = [f"p.{doc.page}"]
        if meta.doc_no:
            right_parts.insert(0, str(meta.doc_no))
        if meta.generated_at:
            right_parts.insert(0, str(meta.generated_at)[:16])
        canvas.drawString(T.PAGE["margin_side_mm"] * mm, y, left)
        canvas.drawRightString((T.PAGE["a4_w_mm"] - T.PAGE["margin_side_mm"]) * mm, y, "  ·  ".join(right_parts))
        canvas.restoreState()

    return _draw
