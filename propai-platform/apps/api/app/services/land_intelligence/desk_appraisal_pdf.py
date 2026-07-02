"""예상 탁상감정서 PDF 생성(reportlab, 한글 CID 폰트). 정식 감정평가서 아님(참고용)."""

from __future__ import annotations

import io
from typing import Any

from app.services.common.pdf_escape import esc as _esc

# avm_interpreter 섹션 키 → 한글 라벨(통합보고서 'AI 상세 해석'과 동일 톤).
_AVM_SECTION_LABELS: dict[str, str] = {
    "valuation_narrative": "추정 근거·신뢰도",
    "comparable_explanation": "비교 사례 분석",
    "market_position": "시장 내 포지셔닝",
    "appreciation_outlook": "향후 가치 전망",
    "investment_recommendation": "투자 종합 의견",
}


def build_desk_appraisal_pdf(
    result: dict[str, Any], *, address: str = "", ai_sections: dict[str, Any] | None = None
) -> bytes:
    """desk_appraisal 결과 dict → 탁상감정서 PDF(bytes).

    ai_sections={section:text} 제공 시 'AI 상세 해석' 섹션을 추가(avm_interpreter 산출)."""
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

    def won(v: Any) -> str:
        try:
            return f"{int(v):,}원"
        except (TypeError, ValueError):
            return "-"

    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontName=font, fontSize=18, spaceAfter=4)
    h = ParagraphStyle("h", parent=ss["Heading2"], fontName=font, fontSize=12, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=9.5, leading=14)
    small = ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8, textColor=colors.grey, leading=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm)
    el: list[Any] = []

    el.append(Paragraph("토지 예상가치 추정 리포트", title))
    el.append(Paragraph("PropAI 사통팔땅 — 공시지가·실거래 기반 참고용 시세 추정 (감정평가 아님)", small))
    el.append(Spacer(1, 8))

    cc = result.get("cross_check") or {}
    area = result.get("area_sqm")
    rng = result.get("range_per_sqm") or {}

    # 1. 대상 / 결론
    summary_rows = [
        ["소재지", address or "-"],
        ["대지면적", f"{area:,}㎡" if area else "-"],
        ["채택 추정단가", won(result.get("appraised_price_per_sqm")) + "/㎡"],
        ["채택 추정가(총액)", won(result.get("appraised_total_won"))],
        ["신뢰도", f"{int((result.get('confidence') or 0) * 100)}%"],
        ["신뢰구간(/㎡)", f"{won(rng.get('low'))} ~ {won(rng.get('high'))}"],
    ]
    el.append(Paragraph("1. 추정 요약 (결론)", h))
    t1 = Table(summary_rows, colWidths=[40 * mm, 130 * mm])
    t1.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("BACKGROUND", (1, 2), (1, 3), colors.HexColor("#eef2ff")),
        ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, colors.white]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(t1)

    # 1-2. 대상물건 표시(지목·용도지역·이용상황 등)
    subj = result.get("subject") or {}
    if subj or result.get("official_price_per_sqm"):
        el.append(Paragraph("1-2. 대상물건 표시", h))
        subj_rows = [
            ["지목", subj.get("land_category") or "-", "용도지역", subj.get("zone_type") or "-"],
            ["이용상황", subj.get("land_use_situation") or "-", "지세/형상",
             f"{subj.get('terrain_height') or '-'} / {subj.get('terrain_form') or '-'}"],
            ["개별공시지가", won(result.get("official_price_per_sqm")) + "/㎡",
             "공시기준", f"{subj.get('official_price_year') or result.get('base_year') or '-'}"],
        ]
        ts = Table(subj_rows, colWidths=[28 * mm, 57 * mm, 28 * mm, 57 * mm])
        ts.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke), ("BACKGROUND", (2, 0), (2, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        el.append(ts)

    # 2. 방법별 산출
    el.append(Paragraph("2. 산정방법별 추정", h))
    mrows = [["산정방법", "추정 단가(/㎡)", "근거"]]
    for m in result.get("methods", []):
        # rationale 은 Paragraph(표 셀)이라 esc(동적 근거 문자열에 '<','&' 혼입 시 크래시 차단).
        # method 는 bare 셀이라 reportlab 이 XML 파싱하지 않아 esc 불필요.
        mrows.append([m.get("method", "-"), won(m.get("unit_price")), Paragraph(_esc(m.get("rationale", "")), small)])
    t2 = Table(mrows, colWidths=[35 * mm, 35 * mm, 100 * mm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(t2)
    # weight_note 는 엔진 산출 동적 문자열이라 esc(Paragraph 직접 보간).
    el.append(Paragraph(_esc(result.get("weight_note", "")), small))

    # 3. 다법인 교차검증
    if cc.get("firms"):
        el.append(Paragraph("3. 복수 시나리오 교차검증", h))
        firms = cc["firms"]
        frows = [["시나리오" + str(i + 1) for i in range(len(firms))] + ["평균", "편차(CV)"]]
        frows.append([won(v) for v in firms] + [won(cc.get("mean")), f"{cc.get('cv_pct')}%"])
        t3 = Table(frows)
        t3.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("BACKGROUND", (-2, 1), (-1, 1), colors.HexColor("#eef2ff")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        el.append(t3)
        # note 는 교차검증 동적 코멘트라 esc(Paragraph 직접 보간).
        el.append(Paragraph(_esc(cc.get("note", "")), small))

    # 4. 원가법 복합 / 수익환원법(입력 시)
    building = result.get("building") or {}
    income = result.get("income") or {}
    if building or income:
        el.append(Paragraph("4. 복합·수익 가치(참고)", h))
        cm_rows: list[list[Any]] = [["구분", "가치", "근거"]]
        if building:
            # rationale 은 Paragraph(표 셀)이라 esc(동적 근거 문자열 크래시 차단).
            cm_rows.append(["원가법 복합(토지+건물)", won(result.get("complex_total_won")),
                            Paragraph(_esc(building.get("rationale", "")), small)])
        if income:
            cm_rows.append(["수익환원법", won(result.get("income_total_won")),
                            Paragraph(_esc(income.get("rationale", "")), small)])
        t4 = Table(cm_rows, colWidths=[40 * mm, 35 * mm, 95 * mm])
        t4.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        el.append(t4)
        if result.get("complex_note"):
            # complex_note 는 동적 문자열이라 esc(Paragraph 직접 보간).
            el.append(Paragraph(_esc(result["complex_note"]), small))

    # 5. 시점수정·시장통계 근거
    ms = result.get("market_stats") or {}
    el.append(Paragraph("5. 시점수정·시장통계 근거", h))
    basis_lines = []
    # time_adjust_basis·cap.basis 는 동적 문자열이라 esc(아래 <br/> join 후 Paragraph 에 들어감 →
    # 미escape 시 '<','&' 가 ValueError 유발). 정적 라벨·숫자(pct)는 그대로.
    if result.get("time_adjust_basis"):
        basis_lines.append(f"· 시점수정: {_esc(result['time_adjust_basis'])}")
    cap = (ms.get("cap_rate") or {})
    if cap.get("source") == "R-ONE":
        basis_lines.append(f"· 자본환원율(R-ONE 실측): {cap.get('pct')}% ({_esc(cap.get('basis', ''))})")
    jc = (ms.get("jeonse_conversion_rate") or {})
    if jc.get("source") == "R-ONE":
        basis_lines.append(f"· 전월세전환율(R-ONE 실측): {jc.get('pct')}%")
    if not ms.get("rone_available"):
        basis_lines.append("· 시장통계: R-ONE 통계표 미설정 구간은 근사값 적용(설정 시 실데이터 전환).")
    # <br/> 는 의도적 줄바꿈 마크업이라 보존(위에서 각 조각의 동적 부분만 esc 했으므로 안전).
    el.append(Paragraph("<br/>".join(basis_lines) if basis_lines else "근거 데이터 없음", small))

    # 6. AI 상세 해석(ai_sections 제공 시 — avm_interpreter 산출)
    if isinstance(ai_sections, dict) and any(
        isinstance(v, str) and v.strip() for v in ai_sections.values()
    ):
        el.append(Paragraph("6. AI 상세 해석", h))
        # <b>·<br/> 는 의도적 마크업이라 보존하고, 그 안의 동적 AI 텍스트(v)·동적 key 만 esc.
        # label 은 정적 상수(_AVM_SECTION_LABELS)라 esc 불필요.
        for key, label in _AVM_SECTION_LABELS.items():
            v = ai_sections.get(key)
            if isinstance(v, str) and v.strip():
                el.append(Paragraph(f"<b>· {label}</b><br/>{_esc(v.strip())}", body))
        # 라벨 미정의 추가 섹션도 누락 없이 출력
        for key, v in ai_sections.items():
            if key not in _AVM_SECTION_LABELS and isinstance(v, str) and v.strip():
                el.append(Paragraph(f"<b>· {_esc(key)}</b><br/>{_esc(v.strip())}", body))

    # 7. 면책
    el.append(Spacer(1, 10))
    el.append(Paragraph("※ 면책 (본 문서는 감정평가서가 아님)", h))
    # disclaimer 는 동적 문자열일 수 있어 esc(Paragraph 직접 보간).
    el.append(Paragraph(_esc(result.get("disclaimer", "")), small))

    doc.build(el)
    return buf.getvalue()
