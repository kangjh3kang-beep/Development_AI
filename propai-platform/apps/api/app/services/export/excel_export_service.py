"""v61 Excel 내보내기 서비스 — 수지분석 + 원가계산서 XLSX 생성.

openpyxl 미설치 시 CSV 폴백으로 동작한다.
"""

from __future__ import annotations

import csv
import io
from typing import Any

try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
except ImportError:
    openpyxl = None  # type: ignore[assignment]


class ExcelExportService:
    """XLSX/CSV 파일 바이트를 생성한다."""

    def feasibility_to_xlsx(self, result: dict[str, Any]) -> tuple[bytes, str]:
        """수지분석 결과를 Excel 바이트로 변환한다.

        Returns:
            (file_bytes, content_type)
        """
        if openpyxl is not None:
            return self._feasibility_xlsx(result), \
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return self._feasibility_csv(result), "text/csv"

    def cost_sheet_to_xlsx(self, rows: list[list[Any]]) -> tuple[bytes, str]:
        """원가계산서 행렬을 Excel 바이트로 변환한다.

        Args:
            rows: OriginCostCalculator.to_excel_data() 반환값.

        Returns:
            (file_bytes, content_type)
        """
        if openpyxl is not None:
            return self._cost_xlsx(rows), \
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return self._cost_csv(rows), "text/csv"

    # ── openpyxl 구현 ──

    def _feasibility_xlsx(self, result: dict[str, Any]) -> bytes:
        wb = openpyxl.Workbook()

        # 요약 시트
        ws = wb.active
        ws.title = "수지분석 요약"
        Font(bold=True, size=12)
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font_white = Font(bold=True, size=11, color="FFFFFF")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        ws.merge_cells("A1:C1")
        ws["A1"] = "PropAI v61 — 수지분석 보고서"
        ws["A1"].font = Font(bold=True, size=14)

        summary_rows = [
            ["항 목", "값", "비 고"],
            ["개발유형", result.get("development_type", "-"), ""],
            ["모듈", result.get("module_name", "-"), ""],
            ["총수입", f"{result.get('total_revenue_won', 0):,.0f} 원", ""],
            ["총비용", f"{result.get('total_cost_won', 0):,.0f} 원", ""],
            ["순이익", f"{result.get('net_profit_won', 0):,.0f} 원", ""],
            ["수익률", f"{result.get('profit_rate_pct', 0):.2f}%", ""],
            ["ROI", f"{result.get('roi_pct', 0):.2f}%", ""],
            ["NPV", f"{result.get('npv_won', 0):,.0f} 원", ""],
            ["등급", result.get("grade", "-"), ""],
        ]

        for row_idx, row_data in enumerate(summary_rows, start=3):
            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = thin_border
                if row_idx == 3:
                    cell.font = header_font_white
                    cell.fill = header_fill

        ws.column_dimensions["A"].width = 20
        ws.column_dimensions["B"].width = 30
        ws.column_dimensions["C"].width = 20

        # 비용 구성 시트
        cost_breakdown = result.get("cost_breakdown_won", {})
        if cost_breakdown:
            ws2 = wb.create_sheet("비용 구성")
            ws2.append(["비용 항목", "금액 (원)", "비율"])
            total = sum(v for v in cost_breakdown.values() if isinstance(v, (int, float)))
            for key, val in cost_breakdown.items():
                ratio = f"{val / total * 100:.1f}%" if total > 0 and isinstance(val, (int, float)) else ""
                ws2.append([key, f"{val:,.0f}" if isinstance(val, (int, float)) else str(val), ratio])
            ws2.column_dimensions["A"].width = 25
            ws2.column_dimensions["B"].width = 25

        # 세금 시트
        tax_detail = result.get("tax_detail", {})
        if tax_detail:
            ws3 = wb.create_sheet("세금 상세")
            ws3.append(["세금 항목", "금액 (원)"])
            for key, val in tax_detail.items():
                ws3.append([key, f"{val:,.0f}" if isinstance(val, (int, float)) else str(val)])
            ws3.column_dimensions["A"].width = 25
            ws3.column_dimensions["B"].width = 25

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def _cost_xlsx(self, rows: list[list[Any]]) -> bytes:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "원가계산서"
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, size=11, color="FFFFFF")
        thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin"),
        )

        ws.merge_cells("A1:C1")
        ws["A1"] = "PropAI v61 — 원가계산서 (2026 법정요율 적용)"
        ws["A1"].font = Font(bold=True, size=14)

        for row_idx, row_data in enumerate(rows, start=3):
            for col_idx, val in enumerate(row_data, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = thin_border
                if row_idx == 3:
                    cell.font = header_font
                    cell.fill = header_fill
                if col_idx == 2:
                    cell.alignment = Alignment(horizontal="right")

        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 25
        ws.column_dimensions["C"].width = 30

        # 합계 행 강조
        total_row = len(rows) + 2
        for col in range(1, 4):
            cell = ws.cell(row=total_row, column=col)
            cell.font = Font(bold=True)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ── CSV 폴백 ──

    def _feasibility_csv(self, result: dict[str, Any]) -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["항목", "값"])
        writer.writerow(["개발유형", result.get("development_type", "")])
        writer.writerow(["총수입", result.get("total_revenue_won", 0)])
        writer.writerow(["총비용", result.get("total_cost_won", 0)])
        writer.writerow(["순이익", result.get("net_profit_won", 0)])
        writer.writerow(["수익률(%)", result.get("profit_rate_pct", 0)])
        writer.writerow(["ROI(%)", result.get("roi_pct", 0)])
        writer.writerow(["NPV", result.get("npv_won", 0)])
        writer.writerow(["등급", result.get("grade", "")])

        cost_bd = result.get("cost_breakdown_won", {})
        if cost_bd:
            writer.writerow([])
            writer.writerow(["비용 항목", "금액"])
            for k, v in cost_bd.items():
                writer.writerow([k, v])

        return buf.getvalue().encode("utf-8-sig")

    def _cost_csv(self, rows: list[list[Any]]) -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in rows:
            writer.writerow(row)
        return buf.getvalue().encode("utf-8-sig")
