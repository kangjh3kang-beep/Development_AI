"""Excel 내보내기 서비스 테스트."""

from app.services.export.excel_export_service import ExcelExportService


SAMPLE_FEASIBILITY = {
    "development_type": "공동주택",
    "module_name": "M01_공동주택",
    "total_revenue_won": 50_000_000_000,
    "total_cost_won": 40_000_000_000,
    "net_profit_won": 10_000_000_000,
    "profit_rate_pct": 20.0,
    "roi_pct": 25.0,
    "npv_won": 8_500_000_000,
    "grade": "A",
    "cost_breakdown_won": {
        "토지비": 15_000_000_000,
        "공사비": 20_000_000_000,
        "설계비": 1_000_000_000,
        "금융비": 2_000_000_000,
        "세금": 2_000_000_000,
    },
    "tax_detail": {
        "취득세": 500_000_000,
        "부가가치세": 1_000_000_000,
        "양도소득세": 500_000_000,
    },
}

SAMPLE_COST_ROWS = [
    ["구 분", "금 액 (원)", "비 고"],
    ["Ⅰ. 직접재료비", "5,000,000,000", ""],
    ["Ⅱ. 직접노무비", "3,000,000,000", ""],
    ["Ⅲ. 직접경비", "1,000,000,000", ""],
    ["직접공사비 소계", "9,000,000,000", "Ⅰ+Ⅱ+Ⅲ"],
    ["총 공사비", "12,500,000,000", ""],
]


class TestExcelExportService:

    def test_feasibility_export_returns_bytes(self):
        svc = ExcelExportService()
        file_bytes, content_type = svc.feasibility_to_xlsx(SAMPLE_FEASIBILITY)
        assert isinstance(file_bytes, bytes)
        assert len(file_bytes) > 0
        assert "csv" in content_type or "spreadsheet" in content_type

    def test_feasibility_export_csv_fallback(self):
        """openpyxl 유무와 관계없이 바이트를 반환한다."""
        svc = ExcelExportService()
        file_bytes, content_type = svc.feasibility_to_xlsx(SAMPLE_FEASIBILITY)
        assert len(file_bytes) > 50

    def test_cost_sheet_export_returns_bytes(self):
        svc = ExcelExportService()
        file_bytes, content_type = svc.cost_sheet_to_xlsx(SAMPLE_COST_ROWS)
        assert isinstance(file_bytes, bytes)
        assert len(file_bytes) > 0

    def test_feasibility_empty_result(self):
        svc = ExcelExportService()
        file_bytes, content_type = svc.feasibility_to_xlsx({})
        assert isinstance(file_bytes, bytes)
        assert len(file_bytes) > 0

    def test_cost_sheet_single_row(self):
        svc = ExcelExportService()
        file_bytes, _ = svc.cost_sheet_to_xlsx([["헤더1", "헤더2"]])
        assert len(file_bytes) > 0

    def test_feasibility_content_type_valid(self):
        svc = ExcelExportService()
        _, content_type = svc.feasibility_to_xlsx(SAMPLE_FEASIBILITY)
        valid = ["text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
        assert content_type in valid

    def test_cost_sheet_content_type_valid(self):
        svc = ExcelExportService()
        _, content_type = svc.cost_sheet_to_xlsx(SAMPLE_COST_ROWS)
        valid = ["text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
        assert content_type in valid
