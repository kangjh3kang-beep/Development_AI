"""Stage1 통합 의사결정 브리프 PDF(Decision Brief) — persona PDF 패턴 복제(신규 PDF엔진 금지).

reportlab SimpleDocTemplate+A4+HYSMyeongJo 한글폰트 폴백·_table 헬퍼·"미확보(정직 고지)" 빈표
처리를 urban_report/developer_report.to_pdf 에서 그대로 복제한다(전례 패턴 재사용). 섹션:
제목(부지 주소·통합면적)·종합판정(GO/CONDITIONAL/HOLD + 신뢰도 + reasons/blockers)·핵심 KPI 표·
5(=3 통합)파트 요약(부지/입지·시장·법규·인허가·설계Top3, 각 oneliner + key_metrics)·근거(evidence·
법령링크 verified만)·정직 고지(deploy_pending·unavailable part).

입력: DecisionBriefService.build() 가 반환하는 표준 브리프 dict
  (apps/api/app/services/land_intelligence/decision_brief_service.py).
무목업: 미확보 섹션은 '미확보(정직 고지)'로 표기(빈 표를 가짜로 채우지 않음). 가짜값 금지.
"""

from __future__ import annotations

import io
from typing import Any

from app.services.common.pdf_escape import esc as _esc
from app.services.land_intelligence.decision_brief_service import (
    PART_PERMIT_DESIGN,
    PART_SITE_MARKET,
)

# 종합판정 결정값 → 한국어 라벨(배지 텍스트). 알 수 없는 값은 그대로 노출(가짜 금지).
_DECISION_LABEL = {
    "GO": "추진 권고 (GO)",
    "CONDITIONAL": "조건부 추진 (CONDITIONAL)",
    "HOLD": "보류 (HOLD)",
}
# 신뢰도 라벨(high/medium/low → 한국어).
_CONFIDENCE_LABEL = {"high": "높음", "medium": "보통", "low": "낮음"}


def _fmt_value(value: Any, unit: str | None) -> str:
    """key_metric 값+단위 → 표시 문자열. 값이 비면 '미확보'(가짜값 생성 금지).

    bool 은 int 의 하위형이라 isinstance(value, (int, float)) 에 먼저 걸려 True→'1', False→'0'
    으로 잠복 변환되던 결함을 선차단한다(bool 은 숫자 포맷 대상이 아니므로 str() 로 표기).
    """
    if value in (None, ""):
        return "미확보"
    if isinstance(value, bool):
        text = str(value)
    elif isinstance(value, (int, float)):
        text = f"{value:,}"
    else:
        text = str(value)
    u = (unit or "").strip()
    return f"{text} {u}".strip() if u else text


def to_pdf(brief: dict[str, Any]) -> bytes:
    """통합 의사결정 브리프 dict → PDF bytes. persona to_pdf 패턴(reportlab) 그대로 복제.

    어떤 키 형태 변동·빈 브리프에도 크래시 없이 유효 PDF를 만든다(graceful·.get 안전접근).
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
    except Exception:  # noqa: BLE001 — 한글폰트 미가용 환경은 Helvetica 폴백(persona 동형)
        font = "Helvetica"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontName=font, fontSize=20)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=font, fontSize=13,
                        textColor=colors.HexColor("#7c3aed"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)
    warn = ParagraphStyle("warn", parent=body, textColor=colors.HexColor("#b45309"))

    story: list = []

    # ── 제목(부지 주소·통합면적) ──
    address = brief.get("address") or "-"
    parcel_count = brief.get("parcel_count")
    # 통합면적은 부지 part 의 land_area KPI(통합면적 종단배선 결과)에서 읽는다(SSOT 단일).
    land_area = _land_area_from_parts(brief)
    story.append(Paragraph("Stage1 통합 의사결정 브리프", h1))
    # address 는 사용자/엔진 입력이라 '<'/'&' 가 섞일 수 있어 이스케이프(parcel_count·land_area 는
    # 숫자라 안전하나 합쳐진 동적 문자열 전체를 esc 해 일관·안전하게 렌더).
    subtitle = _esc(address)
    if isinstance(parcel_count, int) and parcel_count > 1:
        subtitle += f" · 통합 {parcel_count}필지"
    if land_area is not None:
        subtitle += f" · 통합 대지면적 {land_area:,}㎡"
    story.append(Paragraph(subtitle, body))
    story.append(Spacer(1, 8))

    def _table(header: list[str], rows: list[list[str]], widths: list[float]) -> None:
        # persona _table 동형 — rows 비면 '미확보(정직 고지)' 1행으로(가짜로 채우지 않음).
        raw = [header, *rows] if rows else [header, ["미확보(정직 고지)"] + [""] * (len(header) - 1)]
        # 모든 셀은 동적 데이터(주소·근거값 등)라 XML 이스케이프해야 '<'/'&' 가 섞여도 크래시 없이
        # 정상 렌더된다(전역 전파방지·은폐 금지). 의도적 마크업은 표 셀에 넣지 않는다.
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

    # ── 1. 종합 판정(GO/CONDITIONAL/HOLD + 신뢰도 + reasons/blockers) ──
    verdict = brief.get("verdict") or {}
    decision = str(verdict.get("decision") or "HOLD")
    confidence = str(verdict.get("confidence") or "low")
    story.append(Paragraph("1. 종합 판정", h2))
    # decision/confidence/gate·go_nogo 필드는 엔진/페르소나 출력이라 동적 — 각 조각을 esc 한다.
    story.append(Paragraph(
        f"판정: {_esc(_DECISION_LABEL.get(decision, decision))} · "
        f"신뢰도: {_esc(_CONFIDENCE_LABEL.get(confidence, confidence))} · "
        f"게이트: {_esc(verdict.get('gate') or '-')}", body))
    go_nogo = verdict.get("go_nogo") or {}
    if go_nogo:
        roi = go_nogo.get("roi_pct")
        story.append(Paragraph(
            f"디벨로퍼 Go/No-Go: {_esc(go_nogo.get('decision') or '-')} · "
            f"모델: {_esc(go_nogo.get('top1') or '-')} · 등급: {_esc(go_nogo.get('grade') or '-')} · "
            f"ROI: {_esc(roi) if roi is not None else '미확보'}%", body))
    reasons = [r for r in (verdict.get("reasons") or []) if r]
    if reasons:
        story.append(Paragraph("판정 근거", body))
        for r in reasons:
            story.append(Paragraph(f"· {_esc(r)}", body))
    blockers = [b for b in (verdict.get("blockers") or []) if b]
    if blockers:
        story.append(Paragraph("차단·제약 요인(정직 고지)", warn))
        for b in blockers:
            story.append(Paragraph(f"· {_esc(b)}", warn))
    story.append(Spacer(1, 6))

    # ── 2. 핵심 KPI 표(통합면적·실효용적률·예상GFA·예상분양가·ROI) ──
    # 가짜값 생성 금지 — 미확보 KPI는 '미확보'로 표기(아래 _fmt_value).
    story.append(Paragraph("2. 핵심 KPI", h2))
    kpi_rows = _kpi_rows(brief)
    _table(["지표", "값"], kpi_rows, [70 * mm, 90 * mm])

    # ── 3. 5(=3 통합)파트 요약(부지/입지·시장 / 법규 / 인허가·설계Top3) ──
    story.append(Paragraph("3. 통합 분석 파트 요약", h2))
    parts = brief.get("parts") or []
    if not parts:
        story.append(Paragraph("분석 파트 미확보(정직 고지) — 주소/입력을 확인하세요.", warn))
    for part in parts:
        if not isinstance(part, dict):
            continue
        title = part.get("title") or part.get("part") or "-"
        status = part.get("status")
        oneliner = part.get("summary_oneliner") or "-"
        # 파트 제목 + 한줄 요약(unavailable 이면 정직 사유가 oneliner 에 이미 포함).
        # title·oneliner 는 엔진 산출 동적 문자열이라 esc(법규명/근거에 '<','&' 가능).
        story.append(Paragraph(f"■ {_esc(title)}", body))
        if status == "unavailable":
            story.append(Paragraph(_esc(oneliner), warn))
        else:
            story.append(Paragraph(_esc(oneliner), body))
        # key_metrics 표(파트별) — 없으면 '미확보(정직 고지)' 1행.
        metrics = part.get("key_metrics") or []
        mrows = [[str(m.get("label") or "-"), _fmt_value(m.get("value"), m.get("unit"))]
                 for m in metrics if isinstance(m, dict)]
        _table(["지표", "값"], mrows, [70 * mm, 90 * mm])
        # 인허가 part 정직 고지(예: site_id 미확보)·잠정 시나리오.
        if part.get("honest_disclosure"):
            story.append(Paragraph(_esc(part["honest_disclosure"]), warn))
        if part.get("scenario_status") == "tentative":
            story.append(Paragraph("· 잠정 시나리오(선행절차 전제) — 확정 수치 아님.", warn))

    # ── 4. 근거·법령(verified url 만 노출·죽은링크 금지) ──
    story.append(Paragraph("4. 근거·법령", h2))
    ev_rows, link_rows = _evidence_and_links(parts)
    story.append(Paragraph("근거(evidence)", body))
    _table(["항목", "값/산식"], ev_rows, [70 * mm, 90 * mm])
    story.append(Paragraph("법령 링크(verified)", body))
    if link_rows:
        for label, url in link_rows:
            # label·url 모두 동적 — '&' 가 흔한 쿼리스트링 URL 도 esc 해야 크래시 없이 렌더된다.
            story.append(Paragraph(f"· {_esc(label)}: {_esc(url)}", body))
    else:
        story.append(Paragraph("verified 법령 링크 미확보(정직 고지).", warn))
    story.append(Spacer(1, 6))

    # ── 5. 정직 고지(deploy_pending·면적 override 괴리) ──
    meta = brief.get("meta") or {}
    notes: list[str] = []
    if meta.get("deploy_pending"):
        notes.append(
            meta.get("deploy_pending_note")
            or "라이브 DB·공공데이터 API·LLM 실호출은 배포 환경에서만 동작합니다(현재 deploy-pending)."
        )
    area_override = meta.get("area_override") or {}
    if area_override.get("warning"):
        notes.append(str(area_override["warning"]))
    if meta.get("reason"):
        notes.append(str(meta["reason"]))
    if notes:
        story.append(Paragraph("정직 고지", h2))
        for n in notes:
            story.append(Paragraph(f"· {_esc(n)}", warn))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# ----------------------------------------------------------------------
# 브리프 dict 에서 KPI·근거를 안전하게 추출(가짜값 생성 금지·.get 안전접근)
# ----------------------------------------------------------------------

def _find_part(brief: dict[str, Any], part_id: str) -> dict[str, Any] | None:
    """parts 에서 특정 part 를 안전 조회(없으면 None)."""
    for p in (brief.get("parts") or []):
        if isinstance(p, dict) and p.get("part") == part_id:
            return p
    return None


def _metric_value(part: dict[str, Any] | None, key: str) -> Any:
    """part.key_metrics 에서 안정 key 로 값을 뽑는다(없으면 None — 가짜값 금지)."""
    if not part:
        return None
    for m in (part.get("key_metrics") or []):
        if isinstance(m, dict) and m.get("key") == key:
            return m.get("value")
    return None


def _land_area_from_parts(brief: dict[str, Any]) -> float | None:
    """부지 part 의 land_area KPI(통합면적 종단배선 결과)를 통합 대지면적으로 읽는다."""
    v = _metric_value(_find_part(brief, PART_SITE_MARKET), "land_area")
    return float(v) if isinstance(v, (int, float)) else None


def _kpi_rows(brief: dict[str, Any]) -> list[list[str]]:
    """핵심 KPI 표 행 — 통합면적·실효용적률·예상GFA·예상분양가·ROI(미확보=정직 '미확보').

    부지 part(site_market)·인허가 part(permit_design)의 안정 key 에서 직접 읽어, 라벨 변경에도
    silent-null 이 나지 않게 한다(가짜값 생성 금지). 각 값은 _fmt_value 로 단위와 함께 표시.
    """
    site = _find_part(brief, PART_SITE_MARKET)
    permit = _find_part(brief, PART_PERMIT_DESIGN)
    rows = [
        ["통합 대지면적", _fmt_value(_metric_value(site, "land_area"), "㎡")],
        ["실효 용적률", _fmt_value(_metric_value(site, "effective_far"), "%")],
        ["예상 연면적(GFA)", _fmt_value(_metric_value(site, "gfa"), "㎡")],
        ["예상 분양가", _fmt_value(_metric_value(site, "presale_price"), "만원/평")],
        ["사업수익률(ROI)", _fmt_value(_metric_value(permit, "roi"), "%")],
    ]
    return rows


def _evidence_and_links(
    parts: list[Any],
) -> tuple[list[list[str]], list[tuple[str, str]]]:
    """모든 part 의 evidence·법령링크를 평탄화. 법령링크는 url 있는 것만(verified·죽은링크 금지)."""
    ev_rows: list[list[str]] = []
    link_rows: list[tuple[str, str]] = []
    seen_links: set[str] = set()
    for part in parts:
        if not isinstance(part, dict):
            continue
        for e in (part.get("evidence") or []):
            if not isinstance(e, dict):
                continue
            label = str(e.get("label") or "-")
            val = e.get("value")
            basis = e.get("basis")
            text = "" if val in (None, "") else str(val)
            if basis:
                text = f"{text} ({basis})".strip() if text else str(basis)
            ev_rows.append([label, text or "-"])
        for ln in (part.get("legal_links") or []):
            if not isinstance(ln, dict):
                continue
            url = ln.get("url")
            # url 없는 항목은 죽은링크 방지 위해 링크 표에 넣지 않는다(라벨만은 근거에 이미 반영).
            if not url:
                continue
            label = str(ln.get("label") or "법령")
            dedup = f"{label}|{url}"
            if dedup in seen_links:
                continue
            seen_links.add(dedup)
            link_rows.append((label, str(url)))
    return ev_rows, link_rows
