"""전자 해촉증명서 PDF 생성(reportlab, 한글 CID 폰트, 직인 날인).

법정 통일양식 아님 — 세무신고(연말정산) 참고용. 직인은 발급주체가 등록한
이미지(전자문서법상 전자서명에 준하는 첨부)를 본문에 날인하고, 무결성은
해시체인(analysis_ledger)으로 보강한다.

reportlab 은 desk_appraisal_pdf.py 와 동일하게 함수 내부에서 지연 import 한다
(미설치 환경에서도 모듈 import 는 깨지지 않도록).
"""

from __future__ import annotations

import io
import ipaddress
import logging
import socket
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from app.services.common.pdf_escape import esc as _esc

logger = logging.getLogger(__name__)

# 직인 이미지 다운로드 정책. SSRF(내부망/메타데이터 접근) 차단·과대응답 차단을 위한 상수.
_STAMP_ALLOWED_SCHEMES = frozenset({"http", "https"})  # file://, gopher:// 등 비웹 스킴 차단
_STAMP_FETCH_TIMEOUT = 8                                # 연결·읽기 타임아웃(초)
_STAMP_MAX_BYTES = 5 * 1024 * 1024                      # 직인 이미지 최대 5MB(메모리 폭주 차단)


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


def _is_blocked_ip(host: str) -> bool:
    """host(이름 또는 IP)가 사설/루프백/링크로컬/메타데이터 대역으로 해석되면 True(차단).

    DNS 가 가리키는 모든 주소를 검사해 'DNS rebinding'(공개 도메인이 내부 IP 로 해석)도 막는다.
    이름 해석 실패는 '안전 우선'으로 차단(True)한다 — 직인은 부가요소라 못 받으면 텍스트 폴백.
    """
    candidates: list[str] = []
    try:
        # 이미 IP 문자열이면 그대로, 아니면 DNS 로 해석한 모든 주소를 후보로.
        ipaddress.ip_address(host)
        candidates.append(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            candidates = [str(info[4][0]) for info in infos]
        except OSError:
            return True  # 해석 불가 → 차단(안전 우선)
    if not candidates:
        return True
    for addr in candidates:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        # ★[allowlist 화] 개별 대역을 일일이 나열(블록리스트)하면 빠뜨린 비공인 대역으로 우회된다.
        #   특히 CGNAT(100.64.0.0/10)는 is_private/is_link_local 어디에도 안 잡혀 과거 통과했다(이통사
        #   내부망·클라우드 NAT 대역 SSRF 표적). is_global=공인 라우팅 가능 주소만 True 이므로,
        #   '공인 주소가 아니면(=is_global False) 전부 차단'으로 뒤집어 CGNAT·사설·루프백·링크로컬
        #   (169.254 메타데이터)·예약·멀티캐스트·미지정을 한 번에 막는다.
        if not ip.is_global:
            return True
    return False


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """리다이렉트 대상(Location)을 매 홉 재검증 — 공개 호스트→내부 IP 302 우회(SSRF) 차단."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, PLR0913
        parts = urlsplit(newurl)
        if parts.scheme.lower() not in _STAMP_ALLOWED_SCHEMES:
            raise OSError(f"리다이렉트 차단: 허용되지 않은 스킴({parts.scheme})")
        host = parts.hostname
        if not host or _is_blocked_ip(host):
            raise OSError(f"리다이렉트 차단: 내부망/사설 호스트({host})")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_stamp_flowable(stamp_url: str | None, mm: Any) -> Any | None:
    """직인 이미지 URL → reportlab Image flowable(최대 26mm). 실패 시 None(텍스트 폴백).

    ★[SSRF 차단] 외부에서 등록한 stamp_url 을 서버가 직접 fetch 하므로, 검증 없이 열면
    내부망·클라우드 메타데이터(169.254.169.254)·file:// 같은 로컬자원을 끌어올 수 있다(SSRF).
      ① 스킴은 http/https 만 허용(file/gopher/ftp 등 차단)
      ② 호스트가 사설/루프백/링크로컬/예약 대역으로 해석되면 차단(DNS rebinding 포함)
      ③ 응답 크기를 5MB 로 상한(과대응답 메모리 폭주 차단)
      ④ 타임아웃 유지
    실패·차단은 발급을 막지 않고 None(텍스트 '(인)' 폴백)으로 graceful 처리하되, 차단 사유는
    분류 로깅한다(silent-drop 금지 — 보안 차단이 조용히 묻히지 않게).
    """
    if not stamp_url:
        return None
    parts = urlsplit(stamp_url)
    if parts.scheme.lower() not in _STAMP_ALLOWED_SCHEMES:
        logger.warning("직인 fetch 차단: 허용되지 않은 스킴(%s) — 텍스트 폴백", parts.scheme)
        return None
    host = parts.hostname
    if not host or _is_blocked_ip(host):
        logger.warning("직인 fetch 차단: 내부망/사설/해석불가 호스트(%s) — 텍스트 폴백(SSRF 방지)", host)
        return None
    try:
        from reportlab.platypus import Image

        # ★[SSRF·리다이렉트 재검증] urlopen 은 3xx 리다이렉트를 자동 추종한다 — 검증된 공개 호스트가
        #   내부 IP 로 302 시키면 우회된다. 리다이렉트 대상의 스킴/호스트를 매 홉마다 재검증한다.
        opener = urllib.request.build_opener(_SafeRedirectHandler)
        req = urllib.request.Request(stamp_url, method="GET")  # noqa: S310 — 위에서 스킴/호스트 검증 완료
        with opener.open(req, timeout=_STAMP_FETCH_TIMEOUT) as resp:  # noqa: S310
            # 크기 상한 + 1바이트만 읽어 초과 여부 판정(상한 넘으면 차단).
            data = resp.read(_STAMP_MAX_BYTES + 1)
        if not data:
            return None
        if len(data) > _STAMP_MAX_BYTES:
            logger.warning("직인 fetch 차단: 응답 크기 상한(%d) 초과 — 텍스트 폴백", _STAMP_MAX_BYTES)
            return None
        img = Image(io.BytesIO(data))
        ratio = (img.imageHeight or 1) / (img.imageWidth or 1)
        img.drawWidth = 26 * mm
        img.drawHeight = 26 * mm * ratio
        return img
    except Exception as exc:  # noqa: BLE001 — 직인 로드 실패는 발급을 막지 않음(텍스트 '(인)' 폴백)
        logger.info("직인 이미지 로드 실패 → 텍스트 폴백: %s", str(exc)[:160])
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
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
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
    # certificate_no 는 동적 입력이라 esc(Paragraph 직접 보간 → '<','&' 혼입 시 크래시 차단).
    # ★_kv_table 의 셀은 bare str 이라 reportlab 이 XML 파싱하지 않아 esc 불필요(Paragraph 만 위험).
    el.append(Paragraph(f"증명서 번호: {_esc(s('certificate_no'))}", small))
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
    # issuer_company_name·issuer_ceo_name 은 사용자 입력 상호/대표명이라 esc(Paragraph 직접 보간).
    seal_label = Paragraph(f"{_esc(s('issuer_company_name'))}  대표 {_esc(s('issuer_ceo_name'))}", body)
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
        # ledger_hash 는 보통 hex 라 안전하나 동적 값이므로 일관 esc(Paragraph 직접 보간).
        el.append(Paragraph(f"무결성 해시: {_esc(s('ledger_hash'))}", small))

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
