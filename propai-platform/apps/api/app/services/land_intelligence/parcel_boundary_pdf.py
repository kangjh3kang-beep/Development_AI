"""구획도(필지 경계) PDF 빌더 — reportlab(내장 한글 CID 폰트). prod 전용(로컬 3.10엔 미설치).

parcel_boundaries() 결과(features+merged_geometry)를 입력받아 1페이지 PDF를 만든다:
 ① 제목 + 통합면적 요약  ② 필지 경계 벡터 도면(용도지역 색·번호·통합 외곽선 점선)  ③ 필지 표(번호·지번·면적·용도지역).
무목업: 데이터로만 렌더(가짜 도형 금지). reportlab 미설치 시 ImportError를 호출측이 graceful 처리.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any


def _zone_fill_rgb(zone: str | None):
    """용도지역 → reportlab Color(토지이음 범례 근사). 미매칭은 회색."""
    from reportlab.lib import colors
    table = {
        "전용주거": colors.HexColor("#8B9DC3"), "일반주거": colors.HexColor("#C0D8B0"),
        "준주거": colors.HexColor("#E8D490"), "상업": colors.HexColor("#F0D870"),
        "공업": colors.HexColor("#D0B8D8"), "녹지": colors.HexColor("#90C890"),
    }
    if zone:
        for k, v in table.items():
            if k in zone:
                return v
    return colors.HexColor("#cbd5e1")


def build_parcel_boundary_pdf(result: dict[str, Any]) -> bytes:
    """구획도 PDF(bytes) 생성. result=parcel_boundaries() 반환 dict."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        Flowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    from shapely.geometry import shape

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        font = "HYSMyeongJo-Medium"
    except Exception:  # noqa: BLE001
        font = "Helvetica"

    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontName=font, fontSize=16, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9.5, leading=14)
    small = ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8,
                           textColor=colors.grey, leading=11)

    features = [f for f in (result.get("features") or []) if f.get("geometry")]
    total_area = result.get("total_area_sqm") or 0
    pyeong = round(total_area / 3.305785, 1) if total_area else 0

    class _BoundaryDrawing(Flowable):
        """필지 경계 벡터 도면(용도지역 색·번호·통합 외곽선). 경위도→페이지 등거리 스케일."""

        def __init__(self, feats, merged, width=170 * mm, height=110 * mm):
            super().__init__()
            self.feats, self.merged = feats, merged
            self.width, self.height = width, height

        def _bounds(self):
            xs, ys = [], []
            for f in self.feats:
                g = shape(f["geometry"]).buffer(0)
                minx, miny, maxx, maxy = g.bounds
                xs += [minx, maxx]
                ys += [miny, maxy]
            return min(xs), min(ys), max(xs), max(ys)

        def draw(self):
            if not self.feats:
                return
            c = self.canv
            minx, miny, maxx, maxy = self._bounds()
            dx, dy = (maxx - minx) or 1e-9, (maxy - miny) or 1e-9
            pad = 8
            sx = (self.width - 2 * pad) / dx
            sy = (self.height - 2 * pad) / dy
            s = min(sx, sy)  # 등비 스케일(왜곡 방지)

            def proj(x, y):
                return pad + (x - minx) * s, pad + (y - miny) * s

            def _rings(geom):
                g = shape(geom).buffer(0)
                polys = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
                return [list(p.exterior.coords) for p in polys]

            for i, f in enumerate(self.feats):
                c.setStrokeColor(colors.HexColor("#3b82f6"))
                c.setLineWidth(1.0)
                c.setFillColor(_zone_fill_rgb(f.get("zone_type")))
                for ring in _rings(f["geometry"]):
                    p = c.beginPath()
                    x0, y0 = proj(*ring[0])
                    p.moveTo(x0, y0)
                    for x, y in ring[1:]:
                        px, py = proj(x, y)
                        p.lineTo(px, py)
                    p.close()
                    c.drawPath(p, fill=1, stroke=1)
                # 번호 라벨(중심)
                g = shape(f["geometry"]).buffer(0)
                cx, cy = proj(g.centroid.x, g.centroid.y)
                c.setFillColor(colors.HexColor("#1e293b"))
                c.setFont(font, 8)
                c.drawCentredString(cx, cy, str(i + 1))
            # 통합 외곽선(빨강 점선)
            if self.merged:
                c.setStrokeColor(colors.HexColor("#ef4444"))
                c.setLineWidth(1.6)
                c.setDash(4, 3)
                for ring in _rings(self.merged):
                    p = c.beginPath()
                    x0, y0 = proj(*ring[0])
                    p.moveTo(x0, y0)
                    for x, y in ring[1:]:
                        px, py = proj(x, y)
                        p.lineTo(px, py)
                    p.close()
                    c.drawPath(p, fill=0, stroke=1)
                c.setDash()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    story: list[Any] = [
        Paragraph("구획도 (필지 경계)", title),
        Paragraph(
            f"필지 {len(features)}개 · 통합면적 {round(total_area):,}㎡ ({pyeong:,}평)"
            + (" · 통합개발 외곽선(빨강 점선)" if result.get("merged_geometry") else ""),
            body),
        Spacer(1, 6),
        _BoundaryDrawing(features, result.get("merged_geometry")),
        Spacer(1, 10),
    ]
    # 필지 표
    rows = [["No", "지번", "면적(㎡)", "면적(평)", "용도지역"]]
    for i, f in enumerate(features):
        a = f.get("area_sqm")
        rows.append([
            str(i + 1), f.get("address") or f.get("pnu") or "-",
            f"{round(a):,}" if a else "-",
            f"{round(a / 3.305785):,}" if a else "-",
            f.get("zone_type") or "-",
        ])
    tbl = Table(rows, colWidths=[12 * mm, 78 * mm, 26 * mm, 24 * mm, 34 * mm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ALIGN", (2, 0), (3, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "본 구획도는 VWorld 지적 폴리곤 기반이며 법적 측량도가 아닙니다(참고용). "
        "정확한 경계·면적은 지적측량·토지대장으로 확인하세요. 생성: PropAI.", small))
    doc.build(story)
    return buf.getvalue()
