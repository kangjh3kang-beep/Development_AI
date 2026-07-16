"""PDF 렌더러 — 정본 ReportModel 을 Block 단위로 순회하며 reportlab 문서 생성.

표지 → (핵심요약) → 섹션들(블록 순회) → 면책. 모든 저수준 그리기는 pdf_kit 재사용.
"""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from . import pdf_kit as K
from . import tokens as T
from .model import (
    ReportModel,
    Section,
    fmt_value,
)


def render_pdf(model: ReportModel) -> bytes:
    """정본 모델 → PDF bytes."""
    font = K.register_font()
    st = K.styles(font)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=T.PAGE["margin_top_mm"] * mm, bottomMargin=T.PAGE["margin_bottom_mm"] * mm,
        leftMargin=T.PAGE["margin_side_mm"] * mm, rightMargin=T.PAGE["margin_side_mm"] * mm,
    )
    el: list[Any] = []

    # ── 표지 ──
    el.append(Spacer(1, 30 * mm))
    el.append(Paragraph(K._esc(model.meta.title), st["title"]))
    sub_bits = [model.meta.subtitle, model.meta.project_address, model.meta.generated_at]
    sub = " · ".join(x for x in sub_bits if x)
    if sub:
        el.append(Paragraph(K._esc(sub), st["caption"]))
    el.append(Spacer(1, 4 * mm))
    el.append(Paragraph(K._esc(T.BRANDING), st["caption"]))
    if model.meta.confidential:
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(
            f'<font color="{T.SIGNAL["danger"]}"><b>{K._esc(T.CONFIDENTIAL_LABEL)}</b></font>', st["caption"]))
    if model.meta.completeness:
        pct = model.meta.completeness.get("pct")
        if pct is not None:
            el.append(Paragraph(K._esc(f"데이터 채움도: {pct}% (정직 표기)"), st["caption"]))
    el.append(PageBreak())

    # ── 핵심 요약(두괄식) ──
    if model.exec_summary:
        _render_section(el, model.exec_summary, st, font, divider=False)

    # ── 섹션들 ──
    for sec in model.sections:
        _render_section(el, sec, st, font, divider=True)

    # ── 면책 ──
    el.append(Spacer(1, 8 * mm))
    el.append(Paragraph(K._esc(model.disclaimer or T.DISCLAIMER_TEXT), st["disclaimer"]))

    cb = K.footer_callback(model.meta)
    doc.build(el, onFirstPage=cb, onLaterPages=cb)
    return buf.getvalue()


def _render_section(el: list, sec: Section, st: dict, font: str, divider: bool) -> None:
    """섹션 제목 + 블록들."""
    heading = f"{sec.section_no}. {sec.title}" if sec.section_no else sec.title
    el.append(Paragraph(K._esc(heading), st["h2"] if divider else st["h1"]))
    for block in sec.blocks:
        _render_block(el, block, st, font)
    el.append(Spacer(1, 4 * mm))


def _render_block(el: list, block: Any, st: dict, font: str) -> None:
    """Block kind 별 렌더 디스패치."""
    kind = getattr(block, "kind", None)

    if kind == "kv":
        if block.title:
            el.append(Paragraph(K._esc(block.title), st["h3"]))
        if block.rows:
            el.append(K.kv_table(block.rows, font))
        else:
            el.append(Paragraph(T.EMPTY_MARK, st["body"]))

    elif kind == "table":
        if block.title:
            el.append(Paragraph(K._esc(block.title), st["h3"]))
        if block.rows:
            el.append(K.data_table(block.headers, block.rows, font,
                                   numeric_cols=block.numeric_cols, total_row=block.total_row))
        else:
            el.append(Paragraph("데이터 없음", st["body"]))
        if block.caption:
            el.append(Paragraph(K._esc(block.caption), st["caption"]))

    elif kind == "kpi":
        if block.tiles:
            el.append(K.kpi_row(block.tiles, font))

    elif kind == "chart":
        drawing = K.vector_chart(block, font)
        if drawing is not None:
            el.append(drawing)
        else:
            # 벡터 불가 차트(waterfall/tornado)는 표로 정직 폴백(가짜 곡선 금지)
            if block.series:
                headers = ["구분", *[s.name for s in block.series]]
                rows = [[block.categories[i] if i < len(block.categories) else "-",
                         *[fmt_value(s.values[i]) if i < len(s.values) else T.EMPTY_MARK for s in block.series]]
                        for i in range(len(block.categories))]
                el.append(Paragraph(K._esc(block.title), st["h3"]))
                el.append(K.data_table(headers, rows, font, numeric_cols=list(range(1, len(headers)))))
        if block.caption:
            el.append(Paragraph(K._esc(block.caption), st["caption"]))

    elif kind == "narrative":
        if block.title:
            el.append(Paragraph(K._esc(block.title), st["h3"]))
        for para in block.paragraphs or []:
            if str(para).strip():
                el.append(Paragraph(K._esc(para), st["body"]))

    elif kind == "evidence":
        if block.title:
            el.append(Paragraph(K._esc(block.title), st["h3"]))
        for ev in block.items or []:
            parts = [f"<b>{K._esc(ev.value)}</b>"]
            if ev.basis:
                parts.append(f"근거: {K._esc(ev.basis)}")
            if ev.source:
                parts.append(f"출처: {K._esc(ev.source)}")
            if ev.confidence and str(ev.confidence).lower() in ("low", "med", "medium"):
                parts.append(f'<font color="{T.AMBER}">(신뢰도 {K._esc(ev.confidence)})</font>')
            line = " · ".join(parts)
            if ev.legal_link and (str(ev.confidence).lower() == "high" or ev.confidence is None):
                # href 도 XML escape — 클라이언트 유래 URL 에 따옴표가 섞이면 reportlab 파싱이
                # 크래시한다(R1 P3). http(s) 스킴만 허용(그 외는 링크 생략·텍스트만).
                _link = str(ev.legal_link)
                if _link.startswith(("http://", "https://")):
                    line += f' · <a href="{K._esc(_link)}"><font color="{T.LINK}">법령</font></a>'
            el.append(Paragraph(line, st["caption"]))

    elif kind == "checklist":
        if block.title:
            el.append(Paragraph(K._esc(block.title), st["h3"]))
        rows = []
        for label, status in block.items or []:
            mark = "✓" if status is True else ("—" if status in (False, None) else fmt_value(status))
            rows.append([label, mark])
        if rows:
            el.append(K.data_table(["항목", "상태"], rows, font))

    elif kind == "grade":
        el.append(K.grade_badge(block.grade, block.label, font))

    elif kind == "image":
        try:
            from reportlab.platypus import Image as RLImage

            w = (block.max_width_mm or 150) * mm
            el.append(RLImage(io.BytesIO(block.png), width=w, height=w * 0.66))
        except Exception:  # noqa: BLE001  # 이미지 깨져도 문서는 계속
            el.append(Paragraph("(이미지 없음)", st["caption"]))
        if block.caption:
            el.append(Paragraph(K._esc(block.caption), st["caption"]))

    elif kind == "disclaimer":
        el.append(Paragraph(K._esc(block.text), st["disclaimer"]))
