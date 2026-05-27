from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from ..services.report.bank_ready_report_service import BankReadyReportService

router = APIRouter(prefix="/bank-report", tags=["은행제출용 보고서"])


class BankReportRequest(BaseModel):
    project_data: dict  # All project context data
    selected_sections: Optional[list] = None
    template: str = "bank"  # "bank" | "internal"


@router.post("/generate")
async def generate_bank_report(req: BankReportRequest):
    service = BankReadyReportService()
    return service.generate_report(req.project_data, req.selected_sections, req.template)


@router.get("/sections")
async def list_sections():
    return {"sections": BankReadyReportService.REPORT_SECTIONS}
