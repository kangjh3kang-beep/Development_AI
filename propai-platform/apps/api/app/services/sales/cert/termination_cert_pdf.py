"""전자 해촉증명서 PDF 생성(reportlab, 한글 CID 폰트, 직인 날인).

법정 통일양식 아님 — 세무신고(연말정산) 참고용. 직인은 발급주체가 등록한
이미지(전자문서법상 전자서명에 준하는 첨부)를 본문에 날인하고, 무결성은
해시체인(analysis_ledger)으로 보강한다.

reportlab 은 desk_appraisal_pdf.py 와 동일하게 함수 내부에서 지연 import 한다
(미설치 환경에서도 모듈 import 는 깨지지 않도록).
"""

from __future__ import annotations

import io
from typing import Any


def mask_rrn(rrn: str | None) -> str:
    """주민등록번호 마스킹 — 'YYMMDD-1******' 형태로 뒤 6자리(성별 1자리 제외) 가림."""
    if not rrn:
        return "-"
    digits = "".join(ch for ch in str(rrn) if ch.isdigit())
    if len(digits) == 13:
        return f"{digits[:6]}-{digits[6]}******"
    # 형식 불명 — 앞 일부만 노출
    visible = digits[:6] if len(digits) >= 6 else digits
    return f"{visible}{'*' * max(0, len(digits) - 6)}" or "-"


def _fetch_stamp_flowable(stamp_url: str | None, mm: Any) -> Any | None:
    """직인 이미지 URL → reportlab Image flowable(최대 26mm). 실패 시 None(텍스트 폴백)."""
    if not stamp_url:
        return None
    try:
        import urllib.request

        from reportlab.platypus import Image

        with urllib.request.urlopen(stamp_url, timeout=8) as resp:  # noqa: S310
            data = resp.read()
        if not data:
            return None
        img = Image(io.BytesIO(data))
        ratio = (img.imageHeight or 1) / (img.imageWidth or 1)
        img.drawWidth = 26 * mm
        img.drawHeight = 26 * mm * ratio
        return img
    except Exception:  # noqa: BLE001 — 직인 로드 실패는 발급을 막지 않음(텍스트 '(인)' 폴백)
        return None


def build_termination_cert_pdf(cert: dict[str, Any], *, fetch_stamp: bool = True) -> bytes:
    """해촉증명서 1건 dict → PDF(bytes).

    cert 필드(없으면 '-' 표기):
      freelancer_name, freelancer_rrn(마스킹대상), site_name,
      period_start, period_end, issuer_company_name, issuer_biz_no,
      issuer_ceo_name, issuer_stamp_url,
      payee_name, payee_account, income_total, withholding_total, net_total,
      certificate_no, issued_at
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

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

    def s(key: str) -> str:
        v = cert.get(key)
        return str(v) if v not in (None, "") else "-"

    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], fontName=font, fontSize=20, spaceAfter=6, alignment=1)
    h = ParagraphStyle("h", parent=ss["Heading2"], fontName=font, fontSize=12, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontName=font, fontSize=10, leading=15)
    small = ParagraphStyle("s", parent=ss["Normal"], fontName=font, fontSize=8, textColor=colors.grey, leading=11)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, topMargin=20 * mm, bottomMargin=18 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )
    el: list[Any] = []

    el.append(Paragraph("해 촉 증 명 서", title))
    el.append(Paragraph(f"증명서 번호: {s('certificate_no')}", small))
    el.append(Spacer(1, 10))

    # 1. 인적사항(주민번호 마스킹)
    el.append(Paragraph("1. 인적사항", h))
    personal_rows = [
        ["성명", s("freelancer_name")],
        ["주민등록번호", mask_rrn(cert.get("freelancer_rrn"))],
        ["근무 현장", s("site_name")],
    ]
    el.append(_kv_table(personal_rows, font, mm, colors))

    # 2. 근무기간
    el.append(Paragraph("2. 근무(위촉) 기간", h))
    period_rows = [
        ["위촉일", s("period_start")],
        ["해촉일", s("period_end")],
    ]
    el.append(_kv_table(period_rows, font, mm, colors))

    # 3. 수수료 수령자 정보 · 소득(원천징수)
    el.append(Paragraph("3. 수수료 수령 정보 및 소득(원천징수)", h))
    income_rows = [
        ["수령자명", s("payee_name")],
        ["수령 계좌", s("payee_account")],
        ["지급 총액(소득)", won(cert.get("income_total"))],
        ["원천징수세액(3.3%)", won(cert.get("withholding_total"))],
        ["실수령액", won(cert.get("net_total"))],
    ]
    el.append(_kv_table(income_rows, font, mm, colors))

    # 4. 발급 법인 + 직인
    el.append(Paragraph("4. 발급 법인", h))
    issuer_rows = [
        ["법인명", s("issuer_company_name")],
        ["사업자등록번호", s("issuer_biz_no")],
        ["대표자", s("issuer_ceo_name")],
        ["발급일", s("issued_at")],
    ]
    el.append(_kv_table(issuer_rows, font, mm, colors))
    el.append(Spacer(1, 8))

    el.append(Paragraph(
        "위 사람은 본 법인의 분양상담 업무에 상기 기간 동안 위촉되어 근무하였으며, "
        "현재 위촉관계가 해지(해촉)되었음을 증명합니다.", body))
    el.append(Spacer(1, 14))

    # 직인 날인 행 (법인명 + 직인 이미지)
    stamp = _fetch_stamp_flowable(cert.get("issuer_stamp_url"), mm) if fetch_stamp else None
    seal_label = Paragraph(f"{s('issuer_company_name')}  대표 {s('issuer_ceo_name')}", body)
    seal_cell = stamp if stamp is not None else Paragraph("(직인)", body)
    seal_tbl = Table([[seal_label, seal_cell]], colWidths=[120 * mm, 30 * mm])
    seal_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
    ]))
    el.append(seal_tbl)
    el.append(Spacer(1, 16))

    el.append(Paragraph(
        "※ 본 증명서는 법정 통일양식이 아니며, 연말정산·세무신고 시 참고용으로 발급됩니다. "
        "직인은 발급 법인이 등록한 전자 이미지이며, 문서 무결성은 발급 기록(해시체인)으로 보강됩니다.",
        small))
    if cert.get("ledger_hash"):
        el.append(Paragraph(f"무결성 해시: {s('ledger_hash')}", small))

    doc.build(el)
    return buf.getvalue()


def _kv_table(rows: list[list[str]], font: str, mm: Any, colors: Any) -> Any:
    from reportlab.platypus import Table, TableStyle

    t = Table(rows, colWidths=[45 * mm, 125 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t
