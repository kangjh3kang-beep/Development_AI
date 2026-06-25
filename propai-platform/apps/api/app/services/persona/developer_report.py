"""디벨로퍼 페르소나 PDF(사업계획서) — urban_report.to_pdf 패턴 복제(R8).

reportlab SimpleDocTemplate+A4+HYSMyeongJo 한글폰트 폴백·_table 헬퍼·"미확보(정직 고지)"
빈표 처리(R1)를 urban_report 에서 그대로 복제한다. 섹션: 사업타당성(Top3 수지)·
리스크 매트릭스·IRR/NPV/DSCR·Go/No-Go·체크리스트·정직 고지.

입력: runner.run_persona('developer', ...) 가 만든 PersonaReport dict.
무목업: 미확보 섹션은 '미확보(정직 고지)'로 표기(빈 표를 가짜로 채우지 않음, R1).
"""

from __future__ import annotations

import io
from typing import Any

from app.services.common.pdf_escape import esc as _esc


def _won_to_eok(v: Any) -> str:
    """원 → 억원 환산 문자열(미확보면 '미확보')."""
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
                        textColor=colors.HexColor("#1d4ed8"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)
    warn = ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b45309"))

    art = report.get("artifacts") or {}
    story: list = []
    story.append(Paragraph("부동산 개발 사업계획서", h1))
    # address·zone_type·status 는 동적 입력/엔진 산출이라 XML 이스케이프(크래시 방지).
    story.append(Paragraph(
        f"{_esc(report.get('address') or '-')} · 용도지역 {_esc(art.get('zone_type') or '-')} · "
        f"상태 {_esc(report.get('status') or '-')}", body))
    story.append(Spacer(1, 8))

    def _table(header: list[str], rows: list[list[str]], widths: list[float]) -> None:
        raw = [header, *rows] if rows else [header, ["미확보(정직 고지)"] + [""] * (len(header) - 1)]
        # 표 셀은 동적 데이터(모델명·금액·등급 등)라 XML 이스케이프(전역 전파방지·은폐 금지).
        data = [[_esc(cell) for cell in row] for row in raw]
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 8))

    # 1. 사업타당성 — Top1 핵심 KPI
    story.append(Paragraph("1. 사업타당성 핵심 지표 (Top1 추천 모델)", h2))
    kpi = art.get("kpi") or {}
    if kpi:
        story.append(Paragraph(f"추천 모델: {_esc(kpi.get('type_name') or '-')}", body))
        _table(["지표", "값"],
               [["총 매출", _won_to_eok(kpi.get("total_revenue_won"))],
                ["총 사업비", _won_to_eok(kpi.get("total_cost_won"))],
                ["순이익", _won_to_eok(kpi.get("net_profit_won"))],
                ["ROI(사업수익률)", f"{kpi.get('roi_pct')}%" if kpi.get("roi_pct") is not None else "미확보"],
                ["ROE(자기자본수익률)", f"{kpi.get('roe_pct')}%" if kpi.get("roe_pct") is not None else "미확보"],
                ["NPV", _won_to_eok(kpi.get("npv_won"))],
                ["등급", str(kpi.get("grade") or "미확보")]],
               [60 * mm, 100 * mm])
    else:
        _table(["지표", "값"], [], [60 * mm, 100 * mm])

    # 2. Top3 추천 비교
    story.append(Paragraph("2. Top3 사업모델 비교", h2))
    recs = art.get("recommendations") or []
    rrows = []
    for i, r in enumerate(recs[:3]):
        f = r.get("feasibility") or {}
        rrows.append([str(i + 1), str(r.get("type_name") or "-"),
                      _won_to_eok(f.get("net_profit_won")),
                      f"{f.get('roi_pct')}%" if f.get("roi_pct") is not None else "미확보",
                      str(f.get("grade") or "-")])
    _table(["순위", "사업모델", "순이익", "ROI", "등급"], rrows,
           [18 * mm, 62 * mm, 35 * mm, 30 * mm, 20 * mm])

    # 3. 리스크 매트릭스
    story.append(Paragraph("3. 리스크 매트릭스", h2))
    rm = art.get("risk_matrix") or {}
    if rm:
        _table(["리스크 항목", "등급"],
               [["인허가", str(rm.get("permit_risk") or "-")],
                ["시장", str(rm.get("market_risk") or "-")],
                ["자금조달", str(rm.get("funding_risk") or "-")],
                ["공사", str(rm.get("construction_risk") or "-")],
                ["시나리오", str(rm.get("scenario") or "-")]],
               [80 * mm, 80 * mm])
    else:
        _table(["리스크 항목", "등급"], [], [80 * mm, 80 * mm])

    # 4. IRR/NPV/DSCR
    story.append(Paragraph("4. 수익성 지표 (NPV·ROE·DSCR)", h2))
    irr = next((c.get("value") for c in (report.get("checklist") or [])
                if c.get("step") == "irr_npv"), None) or {}
    roe = irr.get("roe_pct")
    story.append(Paragraph(f"NPV: {_esc(_won_to_eok(irr.get('npv_won')))} · "
                           f"ROE: {_esc(roe) if roe is not None else '미확보'}%", body))
    story.append(Paragraph(
        _esc(irr.get("dscr_note") or "DSCR 미산출(정직 고지) — 별도 금융모델 필요."), warn))
    story.append(Spacer(1, 6))

    # 5. Go/No-Go
    story.append(Paragraph("5. Go/No-Go 의사결정", h2))
    gng = art.get("go_nogo") or {}
    if gng:
        story.append(Paragraph(
            f"판정: {_esc(gng.get('decision') or '-')} · 모델: {_esc(gng.get('top1') or '-')} · "
            f"등급: {_esc(gng.get('grade') or '-')} · ROI: {_esc(gng.get('roi_pct'))}%", body))
    else:
        story.append(Paragraph("Go/No-Go 판정에 필요한 사업타당성 미확보(정직).", warn))
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
            story.append(Paragraph(f"· {_esc(n)}", warn))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()
