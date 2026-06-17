"""R2 — PDF 파서(표 추출). HWP->PDF 변환 fallback의 종단 파서.

dev/mock: payload의 'pdf_tables'를 표로 반환(라이브러리 미설치 환경 대체).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ParseResult(BaseModel):
    tables: list[dict] = Field(default_factory=list)
    text: str = ""
    fallback_used: bool = False


class PdfParser:
    def parse(self, source: dict) -> ParseResult:
        tables = source.get("pdf_tables", [])
        return ParseResult(tables=tables, text=source.get("text", ""))

    def parse_from_hwp(self, source: dict) -> ParseResult:
        # HWP를 PDF로 변환 후 파싱(mock). 변환 표가 있으면 사용, 없으면 빈 표.
        converted = {"pdf_tables": source.get("pdf_tables", source.get("tables", []))}
        res = self.parse(converted)
        res.fallback_used = True
        return res
