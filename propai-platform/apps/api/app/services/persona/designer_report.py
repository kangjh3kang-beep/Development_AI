"""설계 페르소나 PDF(설계검토서) — urban_report.to_pdf 패턴 복제(R8).

reportlab SimpleDocTemplate+A4+HYSMyeongJo 한글폰트 폴백·_table 헬퍼·"미확보(정직 고지)"
빈표 처리(R1)를 urban_report 에서 그대로 복제한다. 섹션: 매스 배치·유닛믹스표·
법규 체크·효율·체크리스트·정직 고지.

입력: runner.run_persona('designer', ...) 가 만든 PersonaReport dict.
무목업: 미확보 섹션은 '미확보(정직 고지)'로 표기(빈 표를 가짜로 채우지 않음, R1).
"""

from __future__ import annotations

import io
from typing import Any

from app.services.common.pdf_escape import esc as _esc


def _fmt(v: Any, suffix: str = "") -> str:
    return f"{v}{suffix}" if v not in (None, "") else "미확보"


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
                        textColor=colors.HexColor("#7c3aed"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)
    warn = ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b45309"))

    art = report.get("artifacts") or {}
    story: list = []
    story.append(Paragraph("건축 설계 검토서", h1))
    # address·status 는 동적 입력/엔진 산출이라 XML 이스케이프(크래시 방지).
    story.append(Paragraph(
        f"{_esc(report.get('address') or '-')} · 상태 {_esc(report.get('status') or '-')}", body))
    story.append(Spacer(1, 8))

    def _table(header: list[str], rows: list[list[str]], widths: list[float]) -> None:
        raw = [header, *rows] if rows else [header, ["미확보(정직 고지)"] + [""] * (len(header) - 1)]
        # 표 셀은 동적 데이터(평형코드·세대수·법정한도 등)라 XML 이스케이프(전역 전파방지·은폐 금지).
        data = [[_esc(cell) for cell in row] for row in raw]
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    # 1. 매스 배치
    story.append(Paragraph("1. 매스 배치 (건폐·용적·층수)", h2))
    mass = art.get("mass") or {}
    um = art.get("unit_mix") or {}
    # 세대수는 최적화 결과(unit_mix.total_units) 우선 — 매스 폴백 total_units 가 아닌 실배분 세대수.
    units_for_mass = um.get("total_units") if um.get("total_units") is not None else mass.get("total_units")
    _table(["항목", "값"],
           [["건물폭 × 깊이", f"{_fmt(mass.get('building_width_m'), 'm')} × "
                              f"{_fmt(mass.get('building_depth_m'), 'm')}"],
            ["층수", _fmt(mass.get("num_floors"), "층")],
            ["건물높이", _fmt(mass.get("building_height_m"), "m")],
            ["건폐율", _fmt(mass.get("bcr_pct"), "%")],
            ["용적률", _fmt(mass.get("far_pct"), "%")],
            ["세대수", _fmt(units_for_mass, "세대")]],
           [60 * mm, 100 * mm])

    # 2. 유닛믹스(평형 배분)
    story.append(Paragraph("2. 유닛믹스 (수익 극대 평형 배분)", h2))
    units = um.get("units") or []
    urows = [[str(u.get("code")), str(u.get("count")),
              f"{u.get('ratio_pct')}%" if u.get("ratio_pct") is not None else "-",
              str(u.get("price_per_pyeong_10k") or "-")] for u in units]
    _table(["평형", "세대수", "비율", "분양가(만원/평)"], urows,
           [40 * mm, 40 * mm, 40 * mm, 40 * mm])
    if um.get("total_units"):
        story.append(Paragraph(
            f"총 {_esc(um.get('total_units'))}세대 · 매출 약 {_esc(um.get('total_revenue_100m'))}억원 · "
            f"GFA 효율 {_esc(um.get('gfa_efficiency_pct'))}% · 방식 {_esc(um.get('method'))}", body))
        story.append(Spacer(1, 6))

    # 3. 법규 준수
    story.append(Paragraph("3. 법규 준수 검토 (건폐/용적/높이)", h2))
    comp = art.get("compliance") or {}
    if comp:
        _table(["구분", "실제", "법정한도"],
               [["건폐율", _fmt(comp.get("bcr_pct"), "%"), _fmt(comp.get("max_bcr_pct"), "%")],
                ["용적률", _fmt(comp.get("far_pct"), "%"), _fmt(comp.get("max_far_pct"), "%")]],
               [55 * mm, 50 * mm, 55 * mm])
        viol = comp.get("violations") or []
        if viol:
            joined = ", ".join(str(v) for v in viol)
            story.append(Paragraph("초과 항목: " + _esc(joined) + " — 매스 재조정 필요", warn))
    else:
        _table(["구분", "실제", "법정한도"], [], [55 * mm, 50 * mm, 55 * mm])

    # 4. 효율
    story.append(Paragraph("4. 평면 효율 (전용률·연면적 소진)", h2))
    eff = art.get("efficiency") or {}
    if eff:
        story.append(Paragraph(
            f"GFA 효율 {_esc(_fmt(eff.get('gfa_efficiency_pct'), '%'))} · "
            f"전용률 {_esc(_fmt(eff.get('efficiency_ratio')))} · "
            f"필요 주차 {_esc(_fmt(eff.get('total_parking_required'), '대'))}", body))
    else:
        story.append(Paragraph("효율 진단에 필요한 유닛믹스 미확보(정직).", warn))
    story.append(Spacer(1, 6))

    # 5. 체크리스트·정직 고지
    story.append(Paragraph("5. 실무 체크리스트", h2))
    crows = [[c.get("step", ""), c.get("label", ""), c.get("status", "")]
             for c in (report.get("checklist") or [])]
    _table(["단계", "항목", "판정"], crows, [25 * mm, 90 * mm, 30 * mm])

    notes = report.get("honesty_notes") or []
    if notes:
        story.append(Paragraph("정직 고지", h2))
        for n in notes:
            story.append(Paragraph(f"· {_esc(n)}", warn))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
