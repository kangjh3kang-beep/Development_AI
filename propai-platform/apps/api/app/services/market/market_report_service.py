"""시장조사보고서 서비스 — 주변 실거래·시세·입지·수급을 통합해 심층 보고서 생성.

데이터: MolitClient(유형별 실거래 통계) + LandInfoService(용도지역·공시지가·입지) +
AI 내러티브(get_llm, best-effort). 출력: 구조화 dict / PDF(reportlab) / PPTX(python-pptx).
"""

import io
import json
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_TRADE = [("apt", "아파트"), ("villa", "연립·다세대"), ("officetel", "오피스텔"), ("house", "단독·다가구")]
_RENT = [("apt", "아파트"), ("villa", "연립·다세대"), ("officetel", "오피스텔")]


def _stat(values: list[float]) -> dict[str, Any]:
    vals = [v for v in values if v and v > 0]
    if not vals:
        return {"count": 0, "avg": 0, "min": 0, "max": 0}
    return {"count": len(vals), "avg": round(sum(vals) / len(vals)), "min": min(vals), "max": max(vals)}


def _eok(man: float) -> str:
    if not man:
        return "-"
    if man >= 10000:
        return f"{man / 10000:.1f}억"
    return f"{int(man):,}만"


class MarketReportService:
    def __init__(self) -> None:
        from apps.api.integrations.molit_client import MolitClient

        self.molit = MolitClient()

    def _months(self, n: int = 3) -> list[str]:
        now = datetime.now()
        y, m = now.year, now.month - 1  # 현재월 신고지연 → 직전월부터
        if m == 0:
            m = 12
            y -= 1
        out = []
        for _ in range(n):
            out.append(f"{y}{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return out

    async def _category_stats(self, lawd_cd: str) -> dict[str, Any]:
        import asyncio

        months = self._months(3)
        trade: dict[str, Any] = {}
        rent: dict[str, Any] = {}

        async def trade_one(pt: str, label: str):
            rows: list = []
            res = await asyncio.gather(*[self.molit.get_transactions(lawd_cd, ym, prop_type=pt, num_rows=1000) for ym in months], return_exceptions=True)
            for r in res:
                if isinstance(r, list):
                    rows.extend(r)
            prices = [float(x.get("price_10k_won") or 0) for x in rows]
            areas = [float(x.get("area_m2") or 0) for x in rows]
            return label, {**_stat(prices), "avg_area_m2": round(sum(a for a in areas if a > 0) / max(1, len([a for a in areas if a > 0])), 1) if areas else 0}

        async def rent_one(pt: str, label: str):
            rows: list = []
            res = await asyncio.gather(*[self.molit.get_rent_transactions(lawd_cd, ym, prop_type=pt, num_rows=1000) for ym in months], return_exceptions=True)
            for r in res:
                if isinstance(r, list):
                    rows.extend(r)
            dep = [float(x.get("deposit_10k_won") or 0) for x in rows]
            return label, {**_stat(dep), "count": len([d for d in dep if d > 0])}

        tr = await asyncio.gather(*[trade_one(pt, lb) for pt, lb in _TRADE])
        rr = await asyncio.gather(*[rent_one(pt, lb) for pt, lb in _RENT])
        trade = dict(tr)
        rent = dict(rr)
        return {"months": months, "trade": trade, "rent": rent}

    async def _narrative(self, ctx: dict[str, Any]) -> dict[str, str]:
        """AI 시장 해석(요약·기회·리스크). 실패 시 구조화 폴백."""
        try:
            from app.services.ai.llm_provider import get_llm
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm(timeout=40, max_tokens=1500)
            sys = ("당신은 부동산 시장분석 전문가다. 제공된 실거래·시세·입지 데이터만 근거로 "
                   "한국어 JSON으로 답하라. 키: summary(시장요약 3~4문장), opportunities(기회 2~3개 배열), "
                   "risks(리스크 2~3개 배열), price_trend(가격동향 2문장). 데이터에 없는 수치는 만들지 말 것.")
            usr = f"## 시장 데이터\n{json.dumps(ctx, ensure_ascii=False)[:3500]}"
            resp = await llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=usr)])
            raw = resp.content if hasattr(resp, "content") else str(resp)
            txt = raw.strip()
            if txt.startswith("```"):
                txt = txt.split("```")[1].lstrip("json").strip() if "```" in txt[3:] else txt.strip("`")
            data = json.loads(txt)
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("시장 내러티브 생성 실패, 구조화 폴백", err=str(e)[:80])
            return {"summary": "수집된 실거래·시세 데이터를 기반으로 한 시장 현황입니다.", "opportunities": [], "risks": [], "price_trend": ""}

    async def build_report(self, address: str, lawd_cd: str, pnu: str | None = None) -> dict[str, Any]:
        from app.services.land_intelligence.land_info_service import LandInfoService

        comp = {}
        try:
            comp = await LandInfoService().collect_comprehensive(address, pnu=pnu)
        except Exception:  # noqa: BLE001
            pass
        stats = await self._category_stats(lawd_cd)

        basic = (comp.get("land_register") or {}) if isinstance(comp, dict) else {}
        zone = (comp.get("local_ordinance") or {}) if isinstance(comp, dict) else {}
        infra = (comp.get("infrastructure") or {}) if isinstance(comp, dict) else {}
        coords = comp.get("coordinates") if isinstance(comp, dict) else None

        ctx = {
            "address": address,
            "zone_type": zone.get("zone_type") or (comp.get("land_use_plan") or {}).get("zone_type") if isinstance(comp, dict) else None,
            "official_price": (comp.get("official_prices") or [{}])[0].get("price_per_sqm") if isinstance(comp, dict) and comp.get("official_prices") else None,
            "trade_stats": stats["trade"],
            "rent_stats": stats["rent"],
            "subway": (infra.get("nearest_subway") or {}).get("name") if isinstance(infra, dict) else None,
        }
        narrative = await self._narrative(ctx)

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "address": address,
            "lawd_cd": lawd_cd,
            "coordinates": coords,
            "months": stats["months"],
            "zone_type": ctx["zone_type"],
            "official_price_per_sqm": ctx["official_price"],
            "trade": stats["trade"],
            "rent": stats["rent"],
            "infrastructure": infra,
            "narrative": narrative,
        }

    # ── PDF (reportlab) ──
    def to_pdf(self, rep: dict[str, Any]) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
            font = "HYSMyeongJo-Medium"
        except Exception:  # noqa: BLE001
            font = "Helvetica"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
        ss = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=ss["Title"], fontName=font, fontSize=20)
        h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=font, fontSize=13, textColor=colors.HexColor("#0e7490"))
        body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)
        story: list = []
        story.append(Paragraph("시장조사보고서", h1))
        story.append(Paragraph(f"{rep['address']} · 생성 {rep['generated_at']} · 최근 {len(rep['months'])}개월", body))
        story.append(Spacer(1, 8))

        nar = rep.get("narrative") or {}
        story.append(Paragraph("1. 시장 요약", h2))
        story.append(Paragraph(nar.get("summary") or "-", body))
        if rep.get("zone_type") or rep.get("official_price_per_sqm"):
            story.append(Paragraph(f"용도지역: {rep.get('zone_type') or '-'} · 공시지가(㎡): {_eok((rep.get('official_price_per_sqm') or 0)/10000) if rep.get('official_price_per_sqm') else '-'}", body))
        story.append(Spacer(1, 6))

        def stat_table(title: str, data: dict, unit_label: str):
            story.append(Paragraph(title, h2))
            rows = [["유형", "건수", "평균", "최저", "최고"]]
            for label, s in data.items():
                rows.append([label, str(s.get("count", 0)), _eok(s.get("avg", 0)), _eok(s.get("min", 0)), _eok(s.get("max", 0))])
            t = Table(rows, colWidths=[45 * mm, 25 * mm, 35 * mm, 35 * mm, 35 * mm])
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))

        stat_table("2. 매매 시세 (유형별)", rep.get("trade") or {}, "만원")
        stat_table("3. 전월세 보증금 (유형별)", rep.get("rent") or {}, "만원")

        story.append(Paragraph("4. 기회 요인", h2))
        for o in (nar.get("opportunities") or ["-"]):
            story.append(Paragraph(f"· {o}", body))
        story.append(Spacer(1, 4))
        story.append(Paragraph("5. 리스크 요인", h2))
        for r in (nar.get("risks") or ["-"]):
            story.append(Paragraph(f"· {r}", body))
        story.append(Spacer(1, 4))
        story.append(Paragraph("6. 가격 동향", h2))
        story.append(Paragraph(nar.get("price_trend") or "-", body))

        doc.build(story)
        return buf.getvalue()

    # ── PPTX (python-pptx) ──
    def to_pptx(self, rep: dict[str, Any]) -> bytes:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor

        prs = Presentation()
        prs.slide_width = Inches(13.33)
        prs.slide_height = Inches(7.5)
        accent = RGBColor(0x0E, 0x74, 0x90)

        def title_slide():
            s = prs.slides.add_slide(prs.slide_layouts[6])
            tb = s.shapes.add_textbox(Inches(0.8), Inches(2.4), Inches(11.7), Inches(2.5)).text_frame
            tb.text = "시장조사보고서"
            tb.paragraphs[0].font.size = Pt(44)
            tb.paragraphs[0].font.bold = True
            tb.paragraphs[0].font.color.rgb = accent
            p = tb.add_paragraph()
            p.text = f"{rep['address']}\n생성 {rep['generated_at']} · 최근 {len(rep['months'])}개월"
            p.font.size = Pt(18)

        def text_slide(title: str, lines: list[str]):
            s = prs.slides.add_slide(prs.slide_layouts[6])
            t = s.shapes.add_textbox(Inches(0.7), Inches(0.5), Inches(12), Inches(0.9)).text_frame
            t.text = title
            t.paragraphs[0].font.size = Pt(28); t.paragraphs[0].font.bold = True; t.paragraphs[0].font.color.rgb = accent
            bodytf = s.shapes.add_textbox(Inches(0.8), Inches(1.6), Inches(11.7), Inches(5.2)).text_frame
            bodytf.word_wrap = True
            for i, ln in enumerate(lines or ["-"]):
                para = bodytf.paragraphs[0] if i == 0 else bodytf.add_paragraph()
                para.text = ln
                para.font.size = Pt(16)

        def table_slide(title: str, data: dict):
            s = prs.slides.add_slide(prs.slide_layouts[6])
            t = s.shapes.add_textbox(Inches(0.7), Inches(0.5), Inches(12), Inches(0.9)).text_frame
            t.text = title
            t.paragraphs[0].font.size = Pt(28); t.paragraphs[0].font.bold = True; t.paragraphs[0].font.color.rgb = accent
            rows = len(data) + 1
            tbl = s.shapes.add_table(rows, 5, Inches(0.8), Inches(1.6), Inches(11.7), Inches(0.5 * rows)).table
            hdr = ["유형", "건수", "평균", "최저", "최고"]
            for c, h in enumerate(hdr):
                tbl.cell(0, c).text = h
            for r, (label, st) in enumerate(data.items(), start=1):
                tbl.cell(r, 0).text = label
                tbl.cell(r, 1).text = str(st.get("count", 0))
                tbl.cell(r, 2).text = _eok(st.get("avg", 0))
                tbl.cell(r, 3).text = _eok(st.get("min", 0))
                tbl.cell(r, 4).text = _eok(st.get("max", 0))

        nar = rep.get("narrative") or {}
        title_slide()
        text_slide("1. 시장 요약", [nar.get("summary") or "-", f"용도지역: {rep.get('zone_type') or '-'}"])
        table_slide("2. 매매 시세 (유형별)", rep.get("trade") or {})
        table_slide("3. 전월세 보증금 (유형별)", rep.get("rent") or {})
        text_slide("4. 기회 요인", [f"· {o}" for o in (nar.get("opportunities") or ["-"])])
        text_slide("5. 리스크 요인", [f"· {r}" for r in (nar.get("risks") or ["-"])])
        text_slide("6. 가격 동향", [nar.get("price_trend") or "-"])

        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()
