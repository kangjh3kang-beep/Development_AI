
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.ledger import analysis_ledger_service as ledger

from ..services.report.bank_ready_report_service import BankReadyReportService

router = APIRouter(prefix="/bank-report", tags=["은행제출용 보고서"])


# 원장 analysis_type → bank_report project_data 키 매핑.
# bank_ready_report_service._build_section이 읽는 키와 일치시킨다.
_LEDGER_TYPE_TO_KEY: dict[str, str] = {
    "site_analysis": "site_analysis",
    "design": "design",
    "feasibility": "feasibility",
    "esg": "esg",
    "tax": "tax_detail",
}


class BankReportRequest(BaseModel):
    project_data: dict  # All project context data
    selected_sections: list | None = None
    template: str = "bank"  # "bank" | "internal"
    # 원장 단일출처 우선용 식별자(선택). 제공되고 원장에 적재분이 있으면 권위소스로 사용.
    pnu: str | None = None
    address: str | None = None
    project_id: str | None = None


async def _resolve_tenant_id() -> str | None:
    """요청 컨텍스트 user_id → tenant_id(best-effort, 없으면 None=익명 체인)."""
    try:
        from app.core.request_context import get_current_user_id
        uid = get_current_user_id()
        if not uid:
            return None
        from sqlalchemy import text

        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            row = (await db.execute(
                text("SELECT tenant_id FROM public.users WHERE id = :uid"),
                {"uid": uid})).first()
            if row and row[0]:
                return str(row[0])
    except Exception:  # noqa: BLE001
        pass
    return None


async def _merge_ledger_authoritative(
    project_data: dict, *, tenant_id: str | None,
    pnu: str | None, address: str | None, project_id: str | None,
) -> dict:
    """B2(b): 원장 latest(+verify 통과분)을 권위소스로 project_data에 병합.

    - 원장에 적재분이 있으면 해당 stage 페이로드로 project_data 키를 덮어쓴다(권위소스).
    - 무결성 검증(verify_chain)에 실패한 체인은 신뢰하지 않고 건너뛴다(기존 dict 폴백).
    - 식별자 미제공/원장 비어있음/오류 시 기존 dict 그대로 반환(비파괴 폴백).
    """
    if not (pnu or address or project_id):
        return project_data
    try:
        bundle = await ledger.get_latest(
            analysis_type=None, tenant_id=tenant_id,
            pnu=pnu, address=address, project_id=project_id,
        )
    except Exception:  # noqa: BLE001
        return project_data
    if not bundle:
        return project_data

    merged = dict(project_data or {})
    applied: list[str] = []
    for atype, entry in bundle.items():
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict) or not payload:
            continue
        # 무결성 검증 통과분만 권위소스로 채택(변조 체인은 dict 폴백).
        try:
            chk = await ledger.verify_chain(
                analysis_type=atype, tenant_id=tenant_id,
                pnu=pnu, address=address, project_id=project_id,
            )
            if not chk.get("verified"):
                continue
        except Exception:  # noqa: BLE001
            continue
        key = _LEDGER_TYPE_TO_KEY.get(atype)
        if not key:
            continue
        merged[key] = payload  # 원장 우선(권위소스)
        applied.append(f"{key}:v{entry.get('version')}")
    if applied:
        meta = dict(merged.get("_metadata") or {})
        meta["ledger_authoritative"] = applied
        merged["_metadata"] = meta
    return merged


@router.post("/generate")
async def generate_bank_report(req: BankReportRequest):
    tenant_id = await _resolve_tenant_id()
    project_data = await _merge_ledger_authoritative(
        req.project_data, tenant_id=tenant_id,
        pnu=req.pnu, address=req.address, project_id=req.project_id,
    )
    service = BankReadyReportService()
    return service.generate_report(project_data, req.selected_sections, req.template)


@router.get("/sections")
async def list_sections():
    return {"sections": BankReadyReportService.REPORT_SECTIONS}
