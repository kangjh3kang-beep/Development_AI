"""설계제안 보고서 PDF 생성 — generate_design_proposals 결과(dict) → 타당성 요약 PDF(bytes).

섹션: S0 헤더 / S1 부지 조건(용도지역·면적·실효 BCR/FAR·footprint) / S2 추천 설계안
(판정·GFA·층수·세대·분야 도면세트·주차·건물 배치 폴리곤) / S3 인허가·법규(permit+근거 법령링크)
/ S4 근거·면책(evidence + AI보조·건축사 최종책임 고지).

원칙(전역):
- design_audit_pdf의 한글 CID 폰트(UnicodeCIDFont HYSMyeongJo-Medium·Helvetica 폴백) 패턴 복제.
- 법령 URL은 결과에 담긴 evidence.link만 사용(여기서 URL 조립·날조 금지).
- 미확보 값은 빈칸 대신 '데이터 없음'/'—' 정직 표기(가짜값 금지). 다동이면 동수·blocks 표기.
"""

from __future__ import annotations

import io
from typing import Any


def _fmt(v: Any, unit: str = "") -> str:
    if v is None or v == "":
        return "데이터 없음"
    if isinstance(v, bool):
        return "예" if v else "아니오"
    if isinstance(v, (int, float)):
        try:
            s = f"{v:,.0f}" if abs(v) >= 1000 else (f"{v:g}")
        except (TypeError, ValueError):
            s = str(v)
        return f"{s}{unit}"
    return f"{v}{unit}"


_VERDICT_LABEL = {"pass": "적합", "conditional": "조건부", "fail": "부적합"}


def build_design_proposal_pdf(result: dict[str, Any]) -> bytes:
    """generate_design_proposals 반환 dict → 설계제안 보고서 PDF(bytes)."""
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
    h = ParagraphStyle("h", parent=ss["Heading2"], fontName=font, fontSize=12, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9.5, leading=14)
    small = ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8, textColor=colors.grey, leading=11)

    def _kv(rows_kv: list[list[Any]]) -> Table:
        t = Table(rows_kv, colWidths=[45 * mm, 125 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    site = result.get("site") or {}
    permit = result.get("permit") or {}
    proposals = result.get("proposals") or []
    rec = result.get("recommendation") or {}
    rec_idx = rec.get("index") if isinstance(rec, dict) else None
    chosen = None
    if proposals:
        chosen = proposals[rec_idx] if (isinstance(rec_idx, int) and 0 <= rec_idx < len(proposals)) else proposals[0]
    cand = (chosen or {}).get("candidate") or {}
    verdict = (chosen or {}).get("verdict") or {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    el: list[Any] = []

    el.append(Paragraph("설계제안 타당성 보고서", title))
    el.append(Paragraph("PropAI 사통팔땅 · AI 보조 설계초안 — 최종 인허가·설계 책임은 건축사", small))

    # S1 부지 조건
    el.append(Paragraph("1. 부지 조건", h))
    far_src = {"ordinance": "실효(조례)", "statutory": "법정상한",
               "statutory_fallback": "법정(미지정 폴백)"}.get(str(site.get("far_source")), "미확인")
    el.append(_kv([
        ["용도지역(코드)", _fmt(site.get("zone_code"))],
        ["대지면적", _fmt(site.get("area_sqm"), "㎡")],
        ["건축가능 면적(건폐율)", _fmt(site.get("buildable_footprint_sqm"), "㎡")],
        ["최대 연면적(용적률)", _fmt(site.get("max_gfa_sqm"), "㎡")],
        ["추정 가능 층수", _fmt(site.get("max_floors_est"), "층")],
        ["용적률 기준", far_src],
    ]))

    # S2 추천 설계안
    el.append(Paragraph("2. 추천 설계안", h))
    if not cand:
        el.append(Paragraph(
            "참조 도면이 없어 설계 초안을 생성하지 못했습니다(인허가·법적 envelope 평가만 제공).", body))
    else:
        v = _VERDICT_LABEL.get(str(verdict.get("verdict")), str(verdict.get("verdict") or "—"))
        disc = ", ".join(cand.get("disciplines_covered") or []) or "데이터 없음"
        missing = ", ".join(cand.get("missing_disciplines") or [])
        rows = [
            ["종합 판정", v],
            ["추정 연면적", _fmt(cand.get("estimated_gfa_sqm"), "㎡")],
            ["추정 층수", _fmt(cand.get("estimated_floors"), "층")],
            ["추정 세대수", _fmt(cand.get("estimated_units"), "세대")],
            ["도면 세트(분야)", disc + (f" · 미확보: {missing}" if missing else "")],
            ["법정 주차", _fmt(cand.get("parking_required"), "대")],
        ]
        pl = cand.get("placement") or {}
        if pl:
            st = pl.get("site") or {}
            site_dim = f"{_fmt(st.get('w'))}×{_fmt(st.get('d'))}m" if st else "데이터 없음"
            dong_count = pl.get("dong_count") or 1  # 배치불가 placement엔 키 부재 → 안전 1
            if dong_count > 1:
                place = f"부지 {site_dim} · {dong_count}개 동(이격 {_fmt(pl.get('setback_m'))}m)"
            elif pl.get("building"):
                b = pl["building"]
                place = (f"부지 {site_dim} · 건물 {_fmt(b.get('w'))}×{_fmt(b.get('d'))}m"
                         f" · 이격 {_fmt(pl.get('setback_m'))}m")
            else:
                place = f"부지 {site_dim} · 배치 불가({_fmt(pl.get('note'))})"
            rows.append(["건물 배치(스키매틱)", place])
        el.append(_kv(rows))
        notes = [str(n) for n in (verdict.get("notes") or [])]
        for n in (cand.get("warnings") or []):
            notes.append(str(n))
        if notes:
            el.append(Spacer(1, 3))
            el.append(Paragraph("· " + "<br/>· ".join(notes[:10]), small))

    # S3 인허가·법규
    el.append(Paragraph("3. 인허가 · 법규", h))
    if permit:
        el.append(_kv([
            ["인허가 가능 여부", _fmt(permit.get("is_permitted"))],
            ["인허가 복잡도", _fmt(permit.get("permit_complexity"), "/5")],
            ["사유", _fmt(permit.get("reason"))],
        ]))
    else:
        el.append(Paragraph("용도지역명 미제공 — 인허가 가능성 미확인(용도지역명 입력 시 판정).", body))

    # 근거 법령(site evidence + 추천안 evidence의 link)
    legal_lines: list[str] = []
    for ev in (site.get("evidence") or []) + ((chosen or {}).get("evidence") or []):
        if isinstance(ev, dict) and ev.get("link"):
            legal_lines.append(f"{ev.get('claim') or ev.get('source') or '근거'}: {ev['link']}")
    if legal_lines:
        el.append(Spacer(1, 3))
        el.append(Paragraph("관련 법령(verified):", body))
        el.append(Paragraph("<br/>".join(legal_lines[:12]), small))

    # S4 면책
    el.append(Paragraph("4. 근거 · 면책", h))
    el.append(Paragraph(
        "본 보고서는 AI 보조 설계 초안으로, 모든 수치는 제공 데이터·법정/조례 한도에 근거한 추정이며 "
        "현장·지적·인허가 정밀 검토로 달라질 수 있습니다. 배치·주차·동수는 스키매틱 개략 추정(건축선·"
        "대지형상·일조·정밀계획 미반영)입니다. 최종 인허가·설계의 책임은 건축사에게 있습니다.",
        small,
    ))
    for n in (site.get("warnings") or [])[:6]:
        el.append(Paragraph(f"· {n}", small))

    doc.build(el)
    return buf.getvalue()
