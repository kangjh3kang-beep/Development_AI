"""등기부 PDF 파서 및 registry_service 폴백 라우터 단위 테스트."""

import pytest

from app.services.registry.registry_pdf_parser import parse_registry_pdf
from app.services.registry.registry_service import RegistryService


def test_parse_registry_pdf_invalid():
    res = parse_registry_pdf(b"not a valid pdf content")
    # pypdf/pdfplumber will fail to extract text from dummy bytes
    assert res["ok"] is False
    assert res["status"] in ("parse_failed", "error")


def test_parse_registry_pdf_text_extraction():
    # 간단한 가상 텍스트가 포함된 텍스트 디코딩 테스트 모킹
    dummy_text = "등기사항전부증명서 고유번호 1101-2023-987654 소유자 홍길동 채권최고액 500,000,000 원"

    # parse_registry_pdf의 텍스트 파싱 서브루틴 검증
    from app.services.registry.registry_pdf_parser import _extract_mortgage, _extract_owner, _extract_unique_no

    assert _extract_owner(dummy_text) == "홍길동"
    assert _extract_unique_no(dummy_text) == "11012023987654"
    assert "500000000" in (_extract_mortgage(dummy_text) or "")


@pytest.mark.asyncio
async def test_registry_service_status(monkeypatch):
    monkeypatch.delenv("HYPHEN_HKEY", raising=False)
    monkeypatch.delenv("HYPHEN_USER_ID", raising=False)
    monkeypatch.delenv("TILKO_API_KEY", raising=False)

    svc = RegistryService()
    st = svc.status()
    assert st["configured"] is False
    assert st["provider"] == "pdf_upload"
