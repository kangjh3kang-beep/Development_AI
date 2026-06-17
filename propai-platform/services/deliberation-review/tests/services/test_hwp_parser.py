"""AT-3 — HWP 표 추출 라운드트립 또는 fallback(HWP->PDF) 경로."""
from app.supply.parser.hwp_parser import HwpParser

SAMPLE_HWP = {"tables": [{"rows": [["용도지역", "용적률"], ["제2종일반", "200%"]]}]}
SAMPLE_HWP_UNPARSEABLE = {"pdf_tables": [{"rows": [["fallback"]]}]}  # 1차 표 없음 → PDF fallback


def test_hwp_table_extraction_or_fallback():
    out = HwpParser().parse(SAMPLE_HWP)
    assert out.tables or out.fallback_used is True


def test_hwp_fallback_path():
    out = HwpParser().parse(SAMPLE_HWP_UNPARSEABLE)
    assert out.fallback_used is True
