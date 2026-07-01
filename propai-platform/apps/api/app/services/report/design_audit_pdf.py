"""설계심사 리포트 PDF 생성 (U6/DA-6) — reportlab, 한글 CID 폰트.

design_audits 1건(dict) → S0~S7 구조의 PDF(bytes).
  S0 종합판정·요약 / S1 비교표본 명세(0건 '비교 사례 없음' 정직) / S2 문제점(사례 편차)
  S3 장점 / S4 적용 가능 법규·정책 인센티브 / S5 공학적 문제점 8룰 표(+기술사 확인 고정 플래그)
  S6 심의 예상 쟁점('AI 추정' 라벨) / S7 설계 효율 지표 / 책임한계·면책

원칙:
- pipeline_report_pdf의 한글 폰트(UnicodeCIDFont HYSMyeongJo-Medium, Helvetica 폴백)
  패턴을 그대로 복제한다.
- 법령 URL은 legal_reference_registry 출력만 사용(여기서 URL 조립·날조 금지).
- 데이터가 없는 섹션은 빈 표 대신 '없음'을 정직하게 명시한다(가짜값 금지).
"""

from __future__ import annotations

import io
from typing import Any

from app.services.common.pdf_escape import esc as _esc


def _fmt(v: Any) -> str:
    """동적 값을 표시 문자열로. ★reportlab Paragraph 안전을 위해 항상 XML 이스케이프한다.

    finding 텍스트·overall·metrics 등 모든 동적 텍스트가 _fmt 를 거쳐 Paragraph 에 들어가므로
    여기 한 곳에서 _esc 하면 '<'/'&'/'</para>' 가 섞여도 ValueError(→HTTP500) 없이 정상
    렌더된다(전역 전파방지·은폐 금지). 정적 한글 헤더는 _fmt 미경유라 무영향.
    """
    if v is None:
        return "-"
    if isinstance(v, bool):
        return _esc("예" if v else "아니오")
    if isinstance(v, (int, float)):
        try:
            return _esc(f"{v:,}" if abs(v) >= 1000 else str(v))
        except (TypeError, ValueError):
            return _esc(str(v))
    return _esc(str(v))


_SEVERITY_LABEL = {
    "high": "높음", "medium": "중간", "low": "낮음",
    "fail": "부적합", "warn": "주의", "pass": "적합", "info": "정보",
}


def _sev(f: dict[str, Any]) -> str:
    raw = str(f.get("severity") or f.get("status") or "-").lower()
    return _SEVERITY_LABEL.get(raw, raw)


def _finding_id(f: dict[str, Any]) -> str:
    return str(f.get("check_id") or f.get("rule_id") or f.get("id") or f.get("code") or "-")


def _finding_text(f: dict[str, Any]) -> str:
    title = str(f.get("title") or f.get("message") or f.get("claim") or "").strip()
    detail = str(f.get("detail") or f.get("note") or "").strip()
    if title and detail and detail != title:
        return f"{title} — {detail}"
    return title or detail or "-"


def _group_findings(findings: Any) -> dict[str, list[dict[str, Any]]]:
    """findings(list 또는 {그룹: [...]} dict) → 섹션 그룹.

    분류 휴리스틱(U5 산출 형식에 관용적): category/kind 문자열 → check_id 접두 →
    severity 순. 모호하면 other로 보존(정보 유실 금지).
    """
    groups: dict[str, list[dict[str, Any]]] = {
        "comparison": [], "engineering": [], "strength": [],
        "legal": [], "efficiency": [], "other": [],
    }
    if isinstance(findings, dict):
        for key, value in findings.items():
            if not isinstance(value, list):
                continue
            target = key if key in groups else "other"
            groups[target].extend(f for f in value if isinstance(f, dict))
        return groups
    for f in findings or []:
        if not isinstance(f, dict):
            continue
        cat = str(f.get("category") or f.get("kind") or "").lower()
        cid = _finding_id(f).upper()
        sev = str(f.get("severity") or "").lower()
        if cat in {"engineering", "eng", "공학"} or cid.startswith("ENG"):
            groups["engineering"].append(f)
        elif cat in {"comparison", "deviation", "comparable", "사례", "비교"} or cid.startswith(("CMP", "REF")):
            groups["comparison"].append(f)
        elif (
            cat in {"legal", "incentive", "법규", "정책"}
            or cid.startswith(("LAW", "LEG", "INC"))
            or f.get("legal_ref_key") or f.get("legal_key") or f.get("legal_ref")
        ):
            groups["legal"].append(f)
        elif cat in {"efficiency", "효율"} or cid.startswith("EFF"):
            groups["efficiency"].append(f)
        elif sev in {"positive", "strength", "good"} or cat in {"strength", "장점"}:
            groups["strength"].append(f)
        else:
            groups["other"].append(f)
    return groups


def _comparables(audit: dict[str, Any]) -> list[dict[str, Any]]:
    """비교표본 목록 — inputs.derived_signals/overall에서 탐색(없으면 빈 목록 정직)."""
    inputs = audit.get("inputs") or {}
    overall = audit.get("overall") or {}
    for source in (
        (inputs.get("derived_signals") or {}) if isinstance(inputs, dict) else {},
        inputs if isinstance(inputs, dict) else {},
        overall if isinstance(overall, dict) else {},
    ):
        comps = source.get("comparables")
        if isinstance(comps, list):
            return [c for c in comps if isinstance(c, dict)]
    return []


def _metrics(audit: dict[str, Any], efficiency_findings: list[dict[str, Any]]) -> dict[str, Any]:
    """S7 설계 효율 지표 — overall.metrics/efficiency·derived_signals.metrics 순 탐색."""
    overall = audit.get("overall") or {}
    inputs = audit.get("inputs") or {}
    derived = inputs.get("derived_signals") if isinstance(inputs, dict) else {}
    for source in (overall, derived or {}):
        if not isinstance(source, dict):
            continue
        for key in ("metrics", "efficiency", "efficiency_metrics"):
            m = source.get(key)
            if isinstance(m, dict) and m:
                return m
    # 폴백: efficiency 그룹 findings의 (id → 내용) 표
    return {_finding_id(f): _finding_text(f) for f in efficiency_findings}


def build_design_audit_pdf(audit: dict[str, Any]) -> bytes:
    """설계심사(audit dict) → 리포트 PDF(bytes). audit=design_audits 행(dict) 형태."""
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

    def _kv_table(rows_kv: list[list[Any]], font_size: float = 8.5) -> Table:
        t = Table(rows_kv, colWidths=[45 * mm, 125 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), font_size),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    def _finding_table(items: list[dict[str, Any]]) -> Table:
        rows: list[list[Any]] = [["ID", "내용", "심각도"]]
        for f in items[:30]:
            rows.append([_finding_id(f), Paragraph(_fmt(_finding_text(f)), body), _sev(f)])
        t = Table(rows, colWidths=[24 * mm, 122 * mm, 24 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    overall = audit.get("overall") if isinstance(audit.get("overall"), dict) else {}
    groups = _group_findings(audit.get("findings"))
    blindspot = audit.get("blindspot") if isinstance(audit.get("blindspot"), dict) else None
    comps = _comparables(audit)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )
    el: list[Any] = []

    el.append(Paragraph("설계심사 리포트", title))
    # project_id·id·created_at 는 동적 식별자라 esc(드물지만 '<','&' 혼입 시 크래시 차단).
    el.append(Paragraph(
        f"PropAI 사통팔땅 · 프로젝트 {_esc(audit.get('project_id') or '미상')} · "
        f"심사 ID {_esc(audit.get('id', ''))} · {_esc(audit.get('created_at') or '')}", small))
    el.append(Spacer(1, 8))

    # ── S0 종합판정·요약 ──
    el.append(Paragraph("S0. 종합판정·요약", h))
    if overall:
        rows = [[str(k), Paragraph(_fmt(v if isinstance(v, (str, int, float, bool, type(None))) else _fmt(v)), body)]
                for k, v in overall.items()]
        el.append(_kv_table(rows, font_size=9))
    elif audit.get("overall") not in (None, {}):
        el.append(Paragraph(_fmt(audit.get("overall")), body))
    else:
        el.append(Paragraph("종합판정 데이터 없음.", body))

    # ── S1 비교표본 명세 ──
    el.append(Paragraph("S1. 비교표본 명세", h))
    if comps:
        rows = [["표본", "내용"]]
        for i, c in enumerate(comps[:15], start=1):
            label = str(c.get("title") or c.get("id") or f"표본 {i}")
            # desc 는 Paragraph 로 들어가므로 키(k)도 esc(값 _fmt 는 이미 esc). label 은 bare 셀이라 무영향.
            desc = ", ".join(f"{_esc(k)}: {_fmt(v)}" for k, v in c.items() if k not in {"title", "id"})
            rows.append([label, Paragraph(desc or "-", body)])
        el.append(_kv_table(rows))
    else:
        # 표본 0건 — 가짜 비교 금지, 정직 명시.
        el.append(Paragraph(
            "비교 사례 없음 — 등록된 비교 표본이 없어 사례 기반 비교 진단은 제공하지 않습니다.", body))

    # ── S2 문제점(비교 사례 편차) ──
    el.append(Paragraph("S2. 문제점 — 비교 사례 편차", h))
    problems = list(groups["comparison"])
    problems += [
        f for f in groups["other"]
        if str(f.get("severity") or "").lower() in {"high", "medium", "fail", "warn"}
    ]
    if problems:
        el.append(_finding_table(problems))
    else:
        el.append(Paragraph("확인된 문제점(사례 편차) 없음.", body))

    # ── S3 장점 ──
    el.append(Paragraph("S3. 장점", h))
    if groups["strength"]:
        el.append(_finding_table(groups["strength"]))
    else:
        el.append(Paragraph("데이터로 확인된 장점 항목 없음.", body))

    # ── S4 적용 가능 법규·정책 인센티브 ──
    el.append(Paragraph("S4. 적용 가능 법규·정책 인센티브", h))
    if groups["legal"]:
        rows = [["근거", "내용", "법령 링크"]]
        for f in groups["legal"][:20]:
            link = "링크 없음(레지스트리 미등재)"
            ref_key = f.get("legal_ref_key") or f.get("legal_key") or f.get("ref_key")
            law_label = ""
            if ref_key:
                # URL은 legal_reference_registry 출력만 사용(여기서 조립 금지).
                try:
                    from app.services.legal.legal_reference_registry import get_legal_refs

                    refs = get_legal_refs([str(ref_key)])
                    if refs:
                        law_label = f"{refs[0].get('law_name', '')} {refs[0].get('article', '')}".strip()
                        link = refs[0].get("url") or link
                except Exception:  # noqa: BLE001
                    pass
            rows.append([
                law_label or _finding_id(f),
                Paragraph(_fmt(_finding_text(f)), body),
                # link 은 레지스트리 URL(쿼리스트링에 '&' 흔함)이라 esc 해야 Paragraph 크래시 차단.
                Paragraph(_esc(link), small),
            ])
        t = Table(rows, colWidths=[40 * mm, 75 * mm, 55 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        el.append(t)
    else:
        el.append(Paragraph("확인된 적용 가능 법규·정책 인센티브 항목 없음.", body))

    # ── S5 공학적 문제점(8룰 표) ──
    el.append(Paragraph("S5. 공학적 문제점 — 정량 룰 점검표", h))
    if groups["engineering"]:
        el.append(_finding_table(groups["engineering"]))
    else:
        el.append(Paragraph("공학 룰 점검 결과 없음(입력 데이터 부족).", body))
    # 고정 플래그 — 자동 점검 범위 한계의 정직 명시(항상 출력).
    el.append(Paragraph(
        "※ 구조상세·설비(기계·전기·소방)는 본 자동 점검 범위 밖입니다 — 해당 분야 기술사 확인 필요.",
        small))

    # ── S6 심의 예상 쟁점(AI 추정) ──
    el.append(Paragraph("S6. 심의 예상 쟁점 — [AI 추정]", h))
    bs_items = (blindspot or {}).get("items") if isinstance(blindspot, dict) else None
    if bs_items:
        for it in bs_items[:10]:
            if not isinstance(it, dict):
                continue
            conf = str(it.get("confidence") or "-")
            basis = str(it.get("basis") or "-")
            gate = it.get("citation_gate") or {}
            gate_mark = " · 인용검문: 치환됨" if gate.get("gated") else ""
            el.append(Paragraph(
                f"<b>[AI 추정]</b> {_fmt(it.get('claim'))}", body))
            # basis·conf 는 엔진 산출 동적 문자열이라 esc(Paragraph 직접 보간). gate_mark 는 정적.
            el.append(Paragraph(f"근거: {_esc(basis)} · 신뢰도: {_esc(conf)}{gate_mark}", small))
        if isinstance(blindspot, dict) and blindspot.get("summary"):
            el.append(Paragraph(f"요약: {_fmt(blindspot['summary'])}", small))
        el.append(Paragraph(
            "※ 본 섹션은 AI 추정이며 확정이 아닙니다. 실제 심의 쟁점은 위원회 구성·지역 여건에 따라 달라집니다.",
            small))
    else:
        el.append(Paragraph("AI 추정 쟁점이 생성되지 않아 본 섹션은 생략합니다.", body))

    # ── S7 설계 효율 지표 ──
    el.append(Paragraph("S7. 설계 효율 지표", h))
    metrics = _metrics(audit, groups["efficiency"])
    if metrics:
        rows = [[str(k), Paragraph(_fmt(v if isinstance(v, (str, int, float, bool, type(None))) else _fmt(v)), body)]
                for k, v in list(metrics.items())[:20]]
        el.append(_kv_table(rows))
    else:
        el.append(Paragraph("설계 효율 지표 데이터 없음.", body))

    # ── 책임한계·면책 ──
    el.append(Spacer(1, 10))
    el.append(Paragraph("책임한계·면책", h))
    el.append(Paragraph(
        "본 리포트는 공개데이터·결정론 룰체크·AI 보조 분석 기반의 참고 자료이며 법적 효력이 없습니다. "
        "인허가 적합 여부의 최종 판단은 허가권자(지자체) 소관이고, 심의 결과를 보장하지 않습니다.", small))
    el.append(Paragraph(
        "구조 안전·상세 설계, 기계·전기·소방 설비는 본 자동 심사 범위 밖이며 반드시 해당 분야 "
        "기술사(건축구조기술사 등)와 건축사의 확인을 받아야 합니다.", small))
    el.append(Paragraph(
        "[AI 추정] 라벨 항목은 생성형 AI의 추정으로 오류가 있을 수 있으며, 인용 검문(citation gate)에서 "
        "근거가 확인되지 않은 수치·법조문은 '전문가 확인 필요'로 치환되어 있습니다. "
        "최종 의사결정 책임은 사용자에게 있습니다.", small))

    doc.build(el)
    return buf.getvalue()
