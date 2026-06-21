"""시공 페르소나 PDF(공사비 견적서) — urban_report.to_pdf 패턴 복제(R8).

reportlab SimpleDocTemplate+A4+HYSMyeongJo 한글폰트 폴백·_table 헬퍼·"미확보(정직 고지)"
빈표 처리(R1)를 urban_report 에서 그대로 복제한다. 섹션: 공사비 견적(지상·지하·간접)·
최저~최대 레인지·QTO 물량·원가 안전마진·체크리스트·정직 고지.

입력: runner.run_persona('constructor', ...) 가 만든 PersonaReport dict.
무목업: 미확보 섹션은 '미확보(정직 고지)'로 표기(빈 표를 가짜로 채우지 않음, R1).
"""

from __future__ import annotations

import io
from typing import Any


def _won_to_eok(v: Any) -> str:
    if v in (None, ""):
        return "미확보"
    try:
        return f"{float(v) / 1e8:,.1f}억원"
    except (TypeError, ValueError):
        return "미확보"


def to_pdf(report: dict[str, Any]) -> bytes:
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

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName=font, fontSize=20)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=font, fontSize=13,
                        textColor=colors.HexColor("#ea580c"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)
    warn = ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b45309"))

    art = report.get("artifacts") or {}
    story: list = []
    story.append(Paragraph("공사비 견적서 (개산)", h1))
    est = art.get("estimate") or {}
    story.append(Paragraph(
        f"{report.get('address') or '-'} · {est.get('building_type') or '-'} / "
        f"{est.get('structure_type') or '-'} · 상태 {report.get('status') or '-'}", body))
    story.append(Spacer(1, 8))

    def _table(header: list[str], rows: list[list[str]], widths: list[float]) -> None:
        data = [header, *rows] if rows else [header, ["미확보(정직 고지)"] + [""] * (len(header) - 1)]
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ea580c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    # 1. 공사비 견적 개요
    story.append(Paragraph("1. 공사비 견적 개요", h2))
    if est:
        _table(["항목", "값"],
               [["연면적(총/지상/지하)",
                 f"{est.get('total_gfa_sqm') or '-'} / {est.get('gfa_above_sqm') or '-'} / "
                 f"{est.get('gfa_below_sqm') or '-'} ㎡"],
                ["직접공사비 단가", f"{est.get('unit_cost_per_sqm'):,}원/㎡"
                 if est.get("unit_cost_per_sqm") else "미확보"],
                ["예상 총공사비", _won_to_eok(est.get("total_won"))],
                ["평단가", f"{est.get('per_pyeong_won'):,}원/평"
                 if est.get("per_pyeong_won") else "미확보"]],
               [60 * mm, 100 * mm])
    else:
        _table(["항목", "값"], [], [60 * mm, 100 * mm])

    # 2. 최저~최대 레인지
    story.append(Paragraph("2. 공사비 레인지 (물가·자재 변동)", h2))
    rng = art.get("range") or {}
    if rng:
        _table(["구분", "금액"],
               [["최저", _won_to_eok(rng.get("min_won"))],
                ["예상", _won_to_eok(rng.get("expected_won"))],
                ["최대", _won_to_eok(rng.get("max_won"))]],
               [80 * mm, 80 * mm])
        safety = art.get("safety") or {}
        if safety.get("spread_pct") is not None:
            story.append(Paragraph(
                f"레인지 폭 {safety.get('spread_pct')}% — 폭이 클수록 예산 버퍼 필요.", body))
            story.append(Spacer(1, 6))
    else:
        _table(["구분", "금액"], [], [80 * mm, 80 * mm])

    # 3. QTO 물량(부위별)
    story.append(Paragraph("3. QTO 물량 적산 (부위별)", h2))
    qto = art.get("qto") or {}
    items = qto.get("items") or []
    qrows = [[str(i.get("name") or "-"), str(i.get("quantity") or "-"),
              str(i.get("unit") or "-"), _won_to_eok(i.get("cost_won"))]
             for i in items[:12]]
    _table(["항목", "물량", "단위", "금액"], qrows,
           [60 * mm, 35 * mm, 25 * mm, 40 * mm])
    if qto:
        story.append(Paragraph(
            f"항목 {qto.get('item_count') or 0}건 · 단가 출처 {qto.get('unit_price_source') or '-'} · "
            f"적산 출처 {qto.get('qto_source') or '-'}", body))
        if qto.get("unit_price_source") != "db":
            story.append(Paragraph(
                "단가 일부 fallback(DB 단가 미반영) — 표준 추정 총액은 유효(정직 표기).", warn))
        story.append(Spacer(1, 6))

    # 4. 체크리스트·정직 고지
    story.append(Paragraph("4. 실무 체크리스트", h2))
    crows = [[c.get("step", ""), c.get("label", ""), c.get("status", "")]
             for c in (report.get("checklist") or [])]
    _table(["단계", "항목", "판정"], crows, [25 * mm, 90 * mm, 30 * mm])

    notes = report.get("honesty_notes") or []
    if notes:
        story.append(Paragraph("정직 고지", h2))
        for n in notes:
            story.append(Paragraph(f"· {n}", warn))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
