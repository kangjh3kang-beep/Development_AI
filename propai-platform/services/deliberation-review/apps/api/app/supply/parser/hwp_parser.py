"""R2 — HWP/HWPX 파서. hwp5/pyhwp 우선, 실패 시 HWP->PDF 변환 fallback. 표 구조 추출.

라이브러리 미설치/파싱 실패는 무음 처리 금지 → fallback 경로 사용 + fallback_used 표면화.
완전 실패분은 HITL 큐로 보낼 수 있도록 ParseResult로 결과 노출.
"""
from __future__ import annotations

from app.supply.parser.pdf_parser import ParseResult, PdfParser


class HwpParseError(Exception):
    """1차 HWP 파싱 실패(라이브러리 부재/손상). fallback으로 흡수."""


class HwpParser:
    def __init__(self, pdf_fallback: PdfParser | None = None) -> None:
        self.pdf_fallback = pdf_fallback or PdfParser()

    def parse(self, source: dict) -> ParseResult:
        try:
            tables = self._primary_extract(source)
            return ParseResult(tables=tables, fallback_used=False)
        except HwpParseError:
            # HWP->PDF 변환 fallback.
            return self.pdf_fallback.parse_from_hwp(source)

    @staticmethod
    def _primary_extract(source: dict) -> list[dict]:
        # dev/mock: hwp5/pyhwp 미설치 가정. 'tables'가 직접 주어지면 1차 성공으로 간주.
        tables = source.get("tables")
        if tables:
            return tables
        raise HwpParseError("hwp5/pyhwp unavailable or unparseable")
