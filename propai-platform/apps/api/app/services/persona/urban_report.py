"""도시계획 페르소나 PDF(인허가 검토서) — market_report_service.to_pdf 패턴 복제(R8).

전례 없는 도시계획 보고서이므로 신규지만, reportlab SimpleDocTemplate+A4+HYSMyeongJo
한글폰트 폴백·stat_table 헬퍼 패턴을 market to_pdf 에서 그대로 복제한다. 섹션:
용도지역/한도(법정·조례·실효 분리)·개발방식 비교표·인허가 로드맵·리스크·정직 고지.

입력: runner.run_persona('urban_planner', ...) 가 만든 PersonaReport dict.
무목업: 미확보 섹션은 '미확보(정직 고지)'로 표기(빈 표를 가짜로 채우지 않음, R1).
"""

from __future__ import annotations

import io
from typing import Any


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
                        textColor=colors.HexColor("#0e7490"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)
    warn = ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b45309"))

    art = report.get("artifacts") or {}
    story: list = []
    story.append(Paragraph("도시계획·인허가 검토서", h1))
    story.append(Paragraph(
        f"{report.get('address') or '-'} · 상태 {report.get('status') or '-'}", body))
    if not art.get("interpreter_available"):
        story.append(Paragraph(art.get("interpreter_note") or "", warn))
    story.append(Spacer(1, 8))

    def _table(header: list[str], rows: list[list[str]], widths: list[float]) -> None:
        data = [header, *rows] if rows else [header, ["미확보(정직 고지)"] + [""] * (len(header) - 1)]
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    # 1. 용도지역·한도(법정·조례·실효 분리, R12)
    story.append(Paragraph("1. 용도지역·한도 (법정 / 조례 / 실효 분리)", h2))
    zl = art.get("zone_limits") or {}
    far = zl.get("far") or {}
    bcr = zl.get("bcr") or {}

    def _fmt(v: Any) -> str:
        return f"{v}%" if v not in (None, "") else "미확보"

    _table(["구분", "법정상한", "조례", "실효(적용)"],
           [["용적률", _fmt(far.get("legal")), _fmt(far.get("ordinance")), _fmt(far.get("effective"))],
            ["건폐율", _fmt(bcr.get("legal")), _fmt(bcr.get("ordinance")), _fmt(bcr.get("effective"))]],
           [35 * mm, 40 * mm, 40 * mm, 45 * mm])

    # 2. 특이부지 게이트(developability)
    gate = art.get("gate") or {}
    if gate:
        story.append(Paragraph("2. 특이부지 게이트(개발 가능성)", h2))
        story.append(Paragraph(
            f"개발가능성: {gate.get('developability') or '-'} · 해결가능성: {gate.get('resolvable') or '-'} "
            f"· 판정: {gate.get('decision') or '-'}", body))
        if gate.get("honest_disclosure"):
            story.append(Paragraph(gate["honest_disclosure"], warn))
        story.append(Spacer(1, 6))

    # 3. 개발방식 비교표(AHP)
    story.append(Paragraph("3. 개발방식 비교 (AHP 가중평가)", h2))
    methods = art.get("dev_methods") or []
    rows = [[str(m.get("rank")), str(m.get("method")), str(m.get("score"))]
            for m in methods[:7]]
    _table(["순위", "개발방식", "가중점수"], rows, [20 * mm, 80 * mm, 40 * mm])

    # 4. 인센티브(상향수단)
    story.append(Paragraph("4. 인센티브 (종상향·용적완화 등)", h2))
    incentives = art.get("incentives") or []
    if incentives:
        for it in incentives:
            story.append(Paragraph(f"· {it}", body))
    else:
        story.append(Paragraph("현 데이터로 특정 가능한 상향수단 없음 — 지구단위·조례 확인 필요(정직).", warn))
    story.append(Spacer(1, 6))

    # 5. 인허가 로드맵
    story.append(Paragraph("5. 인허가 로드맵", h2))
    roadmap = art.get("permit_roadmap") or []
    if roadmap:
        for step in roadmap:
            story.append(Paragraph(f"[{step.get('phase')}] {step.get('label')}", body))
    else:
        story.append(Paragraph("로드맵 산출에 필요한 인허가 데이터 미확보(정직).", warn))
    story.append(Spacer(1, 6))

    # 6. 체크리스트·정직 고지
    story.append(Paragraph("6. 실무 체크리스트", h2))
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
