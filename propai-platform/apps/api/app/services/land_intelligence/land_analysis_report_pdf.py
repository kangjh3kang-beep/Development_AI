"""토지분석보고서 PDF 생성(reportlab, 한글 CID 폰트).

다필지 토지조서 → 종합 토지분석보고서. 표준 6섹션:
  ①필지 요약/케이스 ②토지정보 집계 ③권리관계 안내 ④규제·개발가능성 ⑤대지지분/세대(집합건물) ⑥종합 의견.
무목업: 무자료 항목은 '-' 또는 '확인필요'로 정직 표기(가짜 생성 금지). 감정평가·법적효력 없음(참고용).
"""
from __future__ import annotations

import io
from typing import Any

from app.services.common.pdf_escape import esc as _esc

_PY = 3.305785  # 1평 = 3.305785㎡

_CASE_LABEL = {"land": "토지(나대지)", "building": "단일필지 건물", "aggregate": "집합건물(공동주택)"}


def _won(v: Any) -> str:
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return "-"


def _sqm(v: Any) -> str:
    try:
        f = float(v)
        return f"{f:,.1f}㎡ ({f / _PY:,.1f}평)" if f else "-"
    except (TypeError, ValueError):
        return "-"


def build_land_analysis_report(data: dict[str, Any]) -> bytes:
    """report_data → 토지분석보고서 PDF(bytes).

    data = {project_name, parcels:[{jibun,area_sqm,zone_type,bcr_pct,far_pct,jimok,
            official_price_per_sqm,parcel_case,building,status,reason}],
            units_by_parcel:{jibun:{plat_area_sqm,unit_count,units:[...],reliable}}}
    """
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

    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontName=font, fontSize=18, spaceAfter=4)
    h = ParagraphStyle("h", parent=ss["Heading2"], fontName=font, fontSize=12, spaceBefore=12, spaceAfter=5)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9.5, leading=14)
    small = ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8, textColor=colors.grey, leading=11)

    parcels: list[dict] = data.get("parcels") or []
    units_by = data.get("units_by_parcel") or {}
    proj = data.get("project_name") or "토지분석보고서"

    def tbl(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
        t = Table(rows, colWidths=widths)
        style = [
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
                      ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, 0), 8.5)]
        t.setStyle(TableStyle(style))
        return t

    el: list[Any] = []
    el.append(Paragraph("토지분석보고서", title))
    # proj(project_name)은 사용자 입력이라 esc(Paragraph 직접 보간 → '<','&' 혼입 시 크래시 차단).
    # ★tbl() 의 셀은 bare str 이라 reportlab 이 XML 파싱하지 않아 esc 불필요(Paragraph 만 위험).
    el.append(Paragraph(f"PropAI 사통팔땅 — {_esc(proj)} · 공공데이터 기반 참고용(감정평가·법적효력 없음)", small))
    el.append(Spacer(1, 6))

    # ── 집계 ──
    n = len(parcels)
    tot_area = sum(float(p.get("area_sqm") or 0) for p in parcels)
    tot_val = sum(float(p.get("official_price_per_sqm") or 0) * float(p.get("area_sqm") or 0) for p in parcels)
    by_case: dict[str, int] = {}
    zone_dist: dict[str, int] = {}
    for p in parcels:
        by_case[p.get("parcel_case") or "land"] = by_case.get(p.get("parcel_case") or "land", 0) + 1
        z = p.get("zone_type") or "미상"
        zone_dist[z] = zone_dist.get(z, 0) + 1

    # §1 필지 요약/케이스
    el.append(Paragraph("1. 필지 요약 · 유형 분류", h))
    rows = [["#", "지번", "유형", "면적(㎡/평)", "용도지역", "지목", "상태"]]
    for i, p in enumerate(parcels, 1):
        rows.append([
            str(i), p.get("jibun") or p.get("address") or "-",
            _CASE_LABEL.get(p.get("parcel_case") or "land", "-"),
            _sqm(p.get("area_sqm")), p.get("zone_type") or "-",
            p.get("jimok") or "-",
            "확정" if p.get("status") == "ok" else "보완필요",
        ])
    el.append(tbl(rows, [10 * mm, 42 * mm, 26 * mm, 34 * mm, 30 * mm, 14 * mm, 18 * mm]))
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        f"총 {n}필지 · 토지 {by_case.get('land', 0)} / 단일건물 {by_case.get('building', 0)} / "
        f"집합건물 {by_case.get('aggregate', 0)}.", small))

    # §2 토지정보 집계
    el.append(Paragraph("2. 토지정보 집계", h))
    zone_str = ", ".join(f"{z} {c}필지" for z, c in sorted(zone_dist.items(), key=lambda x: -x[1]))
    priced_n = sum(1 for p in parcels if (p.get("official_price_per_sqm") and p.get("area_sqm")))
    val_str = (f"{_won(tot_val)} (공시지가 확보 {priced_n}/{n}필지 기준)" if tot_val else "- (공시지가 미확보)")
    el.append(tbl([
        ["총 대지면적", _sqm(tot_area)],
        ["용도지역 분포", zone_str or "-"],
        ["개별공시지가 기준 추정 토지가액", val_str],
    ], [55 * mm, 120 * mm], header=False))

    # §3 권리관계 안내
    el.append(Paragraph("3. 권리관계 안내", h))
    el.append(Paragraph(
        "소유자·근저당·지상권 등 권리관계는 공공데이터로 확인할 수 없습니다. 정확한 권리분석은 "
        "토지조서 화면의 ‘등기부등본 열람/발급’으로 확보하시기 바랍니다. 본 보고서는 공부(토지대장·"
        "건축물대장·토지이용계획) 기반 정보만 포함합니다.", body))

    # §4 규제·개발가능성 (용도지역 법정 상한 기반)
    el.append(Paragraph("4. 규제 · 개발가능성(법정 상한 기준)", h))
    rows = [["지번", "용도지역", "건폐율", "용적률", "대지면적", "허용 건축면적", "허용 연면적"]]
    for p in parcels:
        jb_ = p.get("jibun") or p.get("address") or ""
        # 집합건물은 §5와 동일하게 표제부 대지면적(plat_area_sqm)을 기준으로 통일(기준 불일치 방지).
        a = float(p.get("area_sqm") or 0)
        if p.get("parcel_case") == "aggregate":
            pa = (units_by.get(jb_) or {}).get("plat_area_sqm")
            if pa:
                a = float(pa)
        bcr = p.get("bcr_pct")
        far = p.get("far_pct")
        arch = f"{a * bcr / 100:,.0f}㎡" if (a and bcr is not None) else "-"
        gfa = f"{a * far / 100:,.0f}㎡" if (a and far is not None) else "-"
        rows.append([
            p.get("jibun") or "-", p.get("zone_type") or "-",
            f"{bcr}%" if bcr is not None else "-", f"{far}%" if far is not None else "-",
            f"{a:,.0f}㎡" if a else "-", arch, gfa,
        ])
    el.append(tbl(rows, [40 * mm, 30 * mm, 16 * mm, 16 * mm, 24 * mm, 26 * mm, 26 * mm]))
    el.append(Paragraph(
        "※ 필지별 법정 상한(국토계획법 시행령)이며, 용도지역이 섞인 다필지는 단순 합산이 불가합니다"
        "(통합 한도는 면적가중 종합분석 참조). 지구단위계획·조례·인센티브로 가감될 수 있습니다.", small))

    # §5 대지지분/세대(집합건물)
    agg_parcels = [p for p in parcels if (p.get("parcel_case") == "aggregate")]
    if agg_parcels:
        el.append(Paragraph("5. 집합건물 세대 대지지분", h))
        for p in agg_parcels:
            jb = p.get("jibun") or p.get("address") or "-"
            u = units_by.get(jb) or {}
            units = u.get("units") or []
            bld = p.get("building") or {}
            # jb(지번)·building_name·unit_count 는 공부/사용자 동적 문자열이라 esc(Paragraph 직접 보간).
            el.append(Paragraph(
                f"· {_esc(jb)} — {_esc(bld.get('building_name') or '건물명 미상')} / "
                f"세대수 {_esc(bld.get('unit_count') or '-')} / 대지면적 {_sqm(u.get('plat_area_sqm'))}", body))
            if units:
                rows = [["동", "호", "전유면적(㎡)", "대지지분(㎡)", "대지지분(평)"]]
                for un in units[:40]:  # 보고서 가독성 상한(초과분은 토지조서 참조)
                    rows.append([
                        un.get("dong") or "-", un.get("ho") or "-",
                        f"{float(un.get('exclusive_area_sqm') or 0):,.2f}",
                        f"{float(un.get('land_share_sqm') or 0):,.2f}",
                        f"{float(un.get('land_share_pyeong') or 0):,.2f}",
                    ])
                el.append(tbl(rows, [22 * mm, 24 * mm, 36 * mm, 36 * mm, 30 * mm]))
                if len(units) > 40:
                    el.append(Paragraph(f"※ 전체 {len(units)}세대 중 40세대 표기(전체는 토지조서 참조).", small))
                val = u.get("validation") or {}
                el.append(Paragraph(
                    "검증: Σ세대 대지지분 = 대지면적 비례배분"
                    + ("(세대 누락 없음·신뢰)" if val.get("reliable") else "(일부 세대 전유부 누락 가능 — 등기부 확인 권장)"), small))
            el.append(Spacer(1, 3))

    # 종합 의견 — §5(대지지분)이 없으면 5번, 있으면 6번으로 연속 번호 유지.
    sec = "6" if agg_parcels else "5"
    el.append(Paragraph(f"{sec}. 종합 의견", h))
    need_fix = sum(1 for p in parcels if p.get("status") != "ok")
    opinion = (
        f"본 보고서는 총 {n}필지, 대지면적 {_sqm(tot_area)} 규모의 토지를 공부 기반으로 분석한 결과입니다. "
        + (f"이 중 {by_case.get('aggregate', 0)}필지는 집합건물(공동주택)로 세대별 대지지분이 분할되어 있어 "
           "세대 단위 권리·매입 협의가 필요합니다. " if by_case.get("aggregate") else "")
        + (f"{need_fix}필지는 주소·PNU 보완이 필요하니 정확한 지번으로 재확인하시기 바랍니다. " if need_fix else "")
        + "구체적 개발규모는 지구단위계획·조례·인허가 검토로 확정되며, 권리관계는 등기부등본으로 확인하시기 바랍니다."
    )
    el.append(Paragraph(opinion, body))
    el.append(Spacer(1, 8))
    el.append(Paragraph("※ 본 보고서는 공공데이터 기반 참고자료로 감정평가·법적 효력이 없습니다. © PropAI 사통팔땅", small))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm, leftMargin=15 * mm, rightMargin=15 * mm)
    doc.build(el)
    buf.seek(0)
    return buf.getvalue()
