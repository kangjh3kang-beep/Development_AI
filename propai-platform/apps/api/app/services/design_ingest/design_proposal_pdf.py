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

from app.services.common.pdf_escape import esc as _esc


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

    # 다필지 통합(있을 때만) — 면적가중 실효한도·통합GFA·대표 용도지역(정직·근거)
    mp = (result.get("multi_parcel") or {}).get("aggregation") or {}
    if mp:
        el.append(Paragraph("다필지 통합", h))
        el.append(_kv([
            ["필지 수", _fmt(mp.get("parcel_count"), "개")],
            ["통합 대지면적", _fmt(mp.get("total_area_sqm"), "㎡")],
            ["대표 용도지역", _fmt(mp.get("dominant_zone"))],
            ["면적가중 용적률(실효)", _fmt(mp.get("blended_far_eff_pct"), "%")],
            ["통합 연면적(Σ필지별)", _fmt(mp.get("integrated_gfa_sqm"), "㎡")],
        ]))
        if mp.get("far_basis_note"):
            el.append(Spacer(1, 3))
            # far_basis_note 는 동적 문자열이라 esc(Paragraph 직접 보간 → 크래시 차단).
            # ★_kv() 의 셀은 bare str 이라 reportlab 이 XML 파싱하지 않아 esc 불필요(Paragraph 만 위험).
            el.append(Paragraph(_esc(mp["far_basis_note"]), small))

    # 특이부지 게이트(있을 때만) — 학교용지·GB·농지·맹지 등 비일상 토지 정직 고지(할루시네이션 방어)
    sp = result.get("special_parcel") or {}
    if sp.get("is_special"):
        gate_label = {"BLOCK": "개발 게이트(개발규모 미산정)", "TENTATIVE": "잠정(확정 아님)",
                      "PASS": "경미"}.get(str(sp.get("gate")), str(sp.get("gate") or "—"))
        el.append(Paragraph("⚠ 특이부지 판정", h))
        el.append(_kv([
            ["유형/심각도", _fmt(sp.get("severity_label"))],
            ["개발가능성", _fmt(sp.get("developability"))],
            ["해결가능성", _fmt(sp.get("resolvable"))],
            ["게이트", gate_label],
        ]))
        if sp.get("note"):
            el.append(Spacer(1, 3))
            # note 는 특이부지 동적 고지 문자열이라 esc(Paragraph 직접 보간).
            el.append(Paragraph(_esc(sp["note"]), small))

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
            ["추정 연면적(보수)", _fmt(cand.get("estimated_gfa_sqm"), "㎡")],
            ["법적 상한 연면적", _fmt(cand.get("max_envelope_gfa_sqm"), "㎡")],
            ["추정 층수", _fmt(cand.get("estimated_floors"), "층")],
            ["추정 세대수", _fmt(cand.get("estimated_units"), "세대")],
            ["도면 세트(분야)", disc + (f" · 미확보: {missing}" if missing else "")],
            ["법정 주차", _fmt(cand.get("parking_required"), "대")],
        ]
        # 정북일조 envelope(건축법 61조) — 주거지역 상부층 북측 단계후퇴 반영(값 있을 때만·무목업).
        sun = cand.get("sunlight_profile") or {}
        if sun:
            bind = "일조가 층수 제약(binding)" if sun.get("binding") else "일조 비제약"
            rows.append([
                "일조 envelope(정북사선)",
                f"{_fmt(sun.get('floors'), '층')} · 연면적 {_fmt(sun.get('gfa'), '㎡')} · "
                f"북측 기준 이격 {_fmt(sun.get('base_north_m'), 'm')} · {bind}"
                " (건축법 61조·시행령 86조)",
            ])
        eff = cand.get("unit_efficiency")
        if eff is not None:
            rows.append(["적용 전용률", f"{round(float(eff) * 100)}%"])
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
        sb = cand.get("score_breakdown") or {}
        if sb.get("explanation"):
            rows.append(["선정 근거(점수)", str(sb["explanation"])])  # 랭킹 투명성(근거)
        srcs = cand.get("sources") or []
        if srcs:  # 조합 출처(provenance) — 어느 코퍼스 도면에서 조합됐는지 근거
            src_txt = " · ".join(
                f"{s.get('drawing_type')}(유사 {round((s.get('score') or 0) * 100)}%)" for s in srcs[:8]
            )
            rows.append(["조합 출처(참조 도면)", src_txt])
        el.append(_kv(rows))
        # 평형별 분해(unit_breakdown) — 평형별 세대수·구성%(값 있을 때만·무목업).
        ub = cand.get("unit_breakdown") or []
        if ub:
            el.append(Spacer(1, 4))
            el.append(Paragraph("평형별 분해", body))
            ub_rows: list[list[Any]] = [["평형", "전용(㎡)", "층당", "총세대", "구성%"]]
            for u in ub:
                if not isinstance(u, dict):
                    continue
                ub_rows.append([
                    _fmt(u.get("type")), _fmt(u.get("area_sqm")),
                    _fmt(u.get("count_per_floor")), _fmt(u.get("total_count")),
                    _fmt(u.get("ratio_pct"), "%"),
                ])
            ubt = Table(ub_rows, colWidths=[34 * mm, 34 * mm, 34 * mm, 34 * mm, 34 * mm])
            ubt.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            el.append(ubt)
        # notes·warnings 는 동적 문자열이라 esc(아래 <br/> join 후 Paragraph 에 들어감).
        notes = [_esc(n) for n in (verdict.get("notes") or [])]
        for n in (cand.get("warnings") or []):
            notes.append(_esc(n))
        if notes:
            el.append(Spacer(1, 3))
            # <br/> 는 의도적 줄바꿈 마크업이라 보존(각 note 의 동적 부분은 위에서 esc 완료).
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
            # claim·source·link 모두 동적('&' 흔한 URL 포함)이라 esc(아래 <br/> join 후 Paragraph 에 들어감).
            legal_lines.append(f"{_esc(ev.get('claim') or ev.get('source') or '근거')}: {_esc(ev['link'])}")
    if legal_lines:
        el.append(Spacer(1, 3))
        el.append(Paragraph("관련 법령(verified):", body))
        # <br/> 는 의도적 줄바꿈 마크업 보존(각 라인의 동적 부분은 위에서 esc 완료).
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
        # 부지 경고 문자열은 동적이라 esc(Paragraph 직접 보간).
        el.append(Paragraph(f"· {_esc(n)}", small))

    doc.build(el)
    return buf.getvalue()
