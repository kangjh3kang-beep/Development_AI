"""등기부등본 PDF 파서 (비상 PDF 직접 업로드 폴백용).

유저가 직접 제출하거나 API 응답으로 받은 부동산 등기부 PDF를 파싱하여
표제부, 갑구(소유권), 을구(소유권 이외의 권리 - 근저당/압류 등)를 구조화 텍스트 및 JSON으로 추출합니다.
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def parse_registry_pdf(pdf_input: bytes | str) -> dict[str, Any]:
    """PDF 바이너리 데이터 또는 Base64 문자열을 입력받아 등기부 내용을 구조화 파싱합니다."""
    if isinstance(pdf_input, str):
        # Base64 문자열 처리
        try:
            pdf_bytes = base64.b64decode(pdf_input)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "status": "error", "message": f"Base64 디코딩 실패: {str(e)[:100]}"}
    else:
        pdf_bytes = pdf_input

    if not pdf_bytes:
        return {"ok": False, "status": "bad_request", "message": "PDF 데이터가 비어 있습니다."}

    text_content = ""
    tables_data: list[list[list[str]]] = []

    # 1. pdfplumber 활용 시도 (표 및 텍스트 정밀 추출)
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page_texts = []
            for page in pdf.pages:
                txt = page.extract_text() or ""
                if txt:
                    page_texts.append(txt)
                tbls = page.extract_tables()
                if tbls:
                    tables_data.extend(tbls)
            text_content = "\n".join(page_texts)
    except Exception as e:  # noqa: BLE001
        logger.warning("pdfplumber 파싱 실패, PyPDF/fitz 텍스트 추출 폴백 시도", err=str(e)[:100])
        # PyPDF2 / pypdf 폴백
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(pdf_bytes))
            page_texts = [p.extract_text() or "" for p in reader.pages]
            text_content = "\n".join(page_texts)
        except Exception as pe:  # noqa: BLE001
            logger.warning("pypdf 파싱도 실패", err=str(pe)[:100])

    if not text_content:
        return {
            "ok": False,
            "status": "parse_failed",
            "message": "PDF에서 텍스트를 추출하지 못했습니다 (스캔 이미지 PDF일 가능성).",
        }

    # 2. 텍스트 정규화 및 갑구/을구/소유자 정규식 파싱
    owner = _extract_owner(text_content)
    mortgage_info = _extract_mortgage(text_content)
    unique_no = _extract_unique_no(text_content)

    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    return {
        "ok": True,
        "status": "ok",
        "origin": "pdf_upload",
        "unique_no": unique_no,
        "owner": owner,
        "mortgage_summary": mortgage_info,
        "registry_text": text_content,
        "pdf_base64": pdf_b64,
        "has_pdf": True,
        "out_list": {
            "get소유자": owner,
            "get고유번호": unique_no,
            "get근저당요약": mortgage_info,
        },
        "message": "등기부 PDF 파싱 성공",
    }


def _extract_owner(text: str) -> str | None:
    """갑구에서 최종 소유자 성명 추출."""
    # 패턴 예: "소유자 홍길동", "공유자 김철수", "소유권이전 ... 소유자 XXX"
    m = re.search(r"소유자\s+([가-힣a-zA-Z0-9㈜(주)]+)", text)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"공유자\s+([가-힣a-zA-Z0-9㈜(주)]+)", text)
    if m2:
        return m2.group(1).strip()
    return None


def _extract_unique_no(text: str) -> str | None:
    """고유번호 추출 (예: 1101-2023-123456)."""
    m = re.search(r"고유번호\s*[:\s]*(\d{4}-\d{4}-\d{6})", text)
    if m:
        return m.group(1).replace("-", "").strip()
    return None


def _extract_mortgage(text: str) -> str | None:
    """을구 근저당권 및 채권최고액 추출 요약."""
    matches = re.findall(r"채권최고액\s*금?\s*([\d,]+)\s*원?", text)
    if matches:
        amounts = [m.replace(",", "") for m in matches]
        return f"근저당 채권최고액 {len(amounts)}건 (최고금액: {max(amounts)}원)"
    return "근저당권 내역 없음 또는 미발견"
