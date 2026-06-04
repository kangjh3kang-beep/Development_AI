"""수지분석 v2 API 라우터 — 14개 엔드포인트 (Auto-Recommend Top 3 포함)."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.feasibility_v2 import (
    FeasibilityCalculateRequest,
    FeasibilityMultiRequest,
    FeasibilityResultResponse,
    FeasibilityMultiResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    OptimizationRequest,
    RecommendationResponse,
    ModuleListResponse,
    VCSCommitRequest,
    VCSRollbackRequest,
)
from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.feasibility.modules.base_module import ModuleInput
from app.services.feasibility.monte_carlo_engine import run_monte_carlo, MCVariable
from app.services.feasibility.ai_optimizer import optimize_slsqp
from app.services.feasibility.ai_recommendation import diagnose
from app.services.feasibility.version_control_db import FeasibilityVCSDB
from app.services.feasibility.sensitivity_engine import run_sensitivity_analysis
from app.core.database import get_db
from app.services.auth.auth_service import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/api/v2/feasibility", tags=["feasibility-v2"])

_service = FeasibilityServiceV2()


def _parse_project_id(project_id: str) -> uuid.UUID:
    """project_id 문자열을 UUID로 변환. 'default' 등 비UUID 문자열은 결정적 UUID로 매핑."""
    try:
        return uuid.UUID(project_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_DNS, f"propai.feasibility.{project_id}")


def _request_to_input(req: FeasibilityCalculateRequest) -> ModuleInput:
    return ModuleInput(
        development_type=req.development_type,
        project_name=req.project_name,
        total_land_area_sqm=req.total_land_area_sqm,
        land_category=req.land_category,
        official_price_per_sqm=req.official_price_per_sqm,
        price_multiplier=req.price_multiplier,
        total_gfa_sqm=req.total_gfa_sqm,
        building_type=req.building_type,
        total_households=req.total_households,
        avg_sale_price_per_pyeong=req.avg_sale_price_per_pyeong,
        avg_area_pyeong=req.avg_area_pyeong,
        sale_ratio=req.sale_ratio,
        bridge_amount_won=req.bridge_amount_won,
        pf_amount_won=req.pf_amount_won,
        midpay_amount_won=req.midpay_amount_won,
        sido_name=req.sido_name,
        sigungu_name=req.sigungu_name,
        project_months=req.project_months,
        discount_rate=req.discount_rate,
        equity_won=req.equity_won,
        params=req.params,
    )


@router.post("/calculate", response_model=FeasibilityResultResponse)
async def calculate_feasibility(req: FeasibilityCalculateRequest):
    """단일 수지분석 계산."""
    try:
        inp = _request_to_input(req)
        output = _service.calculate(inp)
        return FeasibilityResultResponse(
            development_type=output.development_type,
            module_name=output.module_name,
            total_revenue_won=output.total_revenue_won,
            total_cost_won=output.total_cost_won,
            net_profit_won=output.net_profit_won,
            profit_rate_pct=output.profit_rate_pct,
            roi_pct=output.roi_pct,
            npv_won=output.npv_won,
            grade=output.grade,
            cost_breakdown_won=output.cost_detail,
            tax_detail=output.tax_detail,
            special_detail=output.special_detail,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/compare", response_model=FeasibilityMultiResponse)
async def compare_feasibility(req: FeasibilityMultiRequest):
    """복수 개발유형 비교 분석."""
    inputs = [_request_to_input(p) for p in req.projects]
    result = _service.calculate_multi(inputs)
    responses = []
    for output in result["results"]:
        responses.append(FeasibilityResultResponse(
            development_type=output.development_type,
            module_name=output.module_name,
            total_revenue_won=output.total_revenue_won,
            total_cost_won=output.total_cost_won,
            net_profit_won=output.net_profit_won,
            profit_rate_pct=output.profit_rate_pct,
            roi_pct=output.roi_pct,
            npv_won=output.npv_won,
            grade=output.grade,
        ))
    return FeasibilityMultiResponse(results=responses, comparison=result["comparison"])


@router.get("/modules", response_model=ModuleListResponse)
async def list_modules():
    """사용 가능한 개발유형 모듈 목록."""
    return ModuleListResponse(modules=_service.list_available_modules())


@router.post("/monte-carlo", response_model=MonteCarloResponse)
async def run_monte_carlo_sim(req: MonteCarloRequest):
    """몬테카를로 시뮬레이션."""
    mc_vars = [
        MCVariable(
            name=v["name"],
            mean=v["mean"],
            std=v["std"],
            distribution=v.get("distribution", "normal"),
        )
        for v in req.variables
    ]

    def simple_npv(vals):
        return sum(vals.values())

    result = run_monte_carlo(
        calculate_fn=simple_npv,
        variables=mc_vars,
        n_simulations=req.n_simulations,
        seed=req.seed,
    )
    return MonteCarloResponse(**result)


@router.post("/optimize")
async def run_optimization(req: OptimizationRequest):
    """SLSQP 최적화."""
    variables = {k: tuple(v) for k, v in req.variables.items()}

    def objective(vals):
        return sum(vals.values())

    result = optimize_slsqp(
        objective_fn=objective,
        variables=variables,
        maximize=True,
        max_iter=req.max_iter,
    )
    return result


@router.post("/recommendations", response_model=RecommendationResponse)
async def get_recommendations(req: FeasibilityCalculateRequest):
    """AI 권고 생성."""
    inp = _request_to_input(req)
    output = _service.calculate(inp)

    total_cost = output.total_cost_won or 1
    recs = diagnose(
        profit_rate_pct=output.profit_rate_pct,
        roi_pct=output.roi_pct,
        finance_cost_ratio_pct=output.total_finance_cost_won / total_cost * 100,
        construction_cost_ratio_pct=output.total_construction_cost_won / total_cost * 100,
        tax_cost_ratio_pct=output.total_tax_cost_won / total_cost * 100,
        grade=output.grade,
    )
    return RecommendationResponse(
        recommendations=[
            {
                "rule_code": r.rule_code,
                "rule_name": r.rule_name,
                "severity": r.severity,
                "message": r.message,
                "suggestion": r.suggestion,
            }
            for r in recs
        ]
    )


@router.post("/repos/{project_id}/commit")
async def vcs_commit(
    project_id: str,
    req: VCSCommitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """수지분석 커밋."""
    vcs = FeasibilityVCSDB(db, project_id=_parse_project_id(project_id), tenant_id=current_user.organization_id)
    result = await vcs.commit(req.snapshot, req.message)
    return {"sha": result["sha"], "message": result["message"], "timestamp": result.get("timestamp", "")}


@router.post("/repos/{project_id}/rollback")
async def vcs_rollback(
    project_id: str,
    req: VCSRollbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """수지분석 롤백."""
    vcs = FeasibilityVCSDB(db, project_id=_parse_project_id(project_id), tenant_id=current_user.organization_id)
    result = await vcs.rollback(req.target_sha)
    if not result:
        raise HTTPException(status_code=404, detail="커밋을 찾을 수 없습니다")
    return {"sha": result["sha"], "message": result["message"]}


@router.get("/repos/{project_id}/log")
async def vcs_log(
    project_id: str,
    max_count: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """커밋 이력."""
    vcs = FeasibilityVCSDB(db, project_id=_parse_project_id(project_id), tenant_id=current_user.organization_id)
    log_entries = await vcs.log(max_count)
    return {
        "commits": [
            {"sha": c["sha"], "message": c["message"], "parent_sha": c["parent_sha"], "timestamp": c["timestamp"]}
            for c in log_entries
        ]
    }


@router.get("/repos/{project_id}/diff/{sha_a}/{sha_b}")
async def vcs_diff(
    project_id: str,
    sha_a: str,
    sha_b: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """두 커밋 간 diff."""
    vcs = FeasibilityVCSDB(db, project_id=_parse_project_id(project_id), tenant_id=current_user.organization_id)
    return await vcs.diff(sha_a, sha_b)


@router.post("/export-excel", response_class=Response)
async def export_feasibility_excel(req: FeasibilityCalculateRequest):
    """수지분석 결과를 Excel 파일로 내보낸다."""
    from app.services.export.excel_export_service import ExcelExportService

    try:
        inp = _request_to_input(req)
        output = _service.calculate(inp)

        result_dict = {
            "development_type": output.development_type,
            "module_name": output.module_name,
            "total_revenue_won": output.total_revenue_won,
            "total_cost_won": output.total_cost_won,
            "net_profit_won": output.net_profit_won,
            "profit_rate_pct": output.profit_rate_pct,
            "roi_pct": output.roi_pct,
            "npv_won": output.npv_won,
            "grade": output.grade,
            "cost_breakdown_won": output.cost_detail,
            "tax_detail": output.tax_detail,
        }

        export_svc = ExcelExportService()
        file_bytes, content_type = export_svc.feasibility_to_xlsx(result_dict)

        ext = "xlsx" if "spreadsheet" in content_type else "csv"
        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="feasibility_{output.development_type}.{ext}"'
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ------------------------------------------------------------------
# Auto-Recommend Top 3 + Finalize
# ------------------------------------------------------------------


class AutoRecommendRequest(BaseModel):
    address: str
    land_area_sqm: float | None = None
    region: str = "서울"
    equity_won: int = 10_000_000_000


@router.post("/auto-recommend")
async def auto_recommend_top3(req: AutoRecommendRequest):
    """부지 주소로부터 최적 사업모델 Top 3 자동 추천."""
    service = FeasibilityServiceV2()
    return await service.auto_recommend_top3(
        address=req.address,
        land_area_sqm=req.land_area_sqm,
        region=req.region,
        equity_won=req.equity_won,
    )


class FinalizeRequest(BaseModel):
    project_id: str
    development_type: str
    module_input: dict  # The refined ModuleInput from user


@router.post("/finalize")
async def finalize_business_model(req: FinalizeRequest):
    """선택된 사업모델을 최종 확정."""
    service = FeasibilityServiceV2()
    # Calculate final result
    inp = ModuleInput(**req.module_input)
    result = service.calculate(inp)
    return {
        "project_id": req.project_id,
        "status": "finalized",
        "development_type": req.development_type,
        "final_result": {
            "development_type": result.development_type,
            "module_name": result.module_name,
            "total_revenue_won": result.total_revenue_won,
            "total_cost_won": result.total_cost_won,
            "net_profit_won": result.net_profit_won,
            "profit_rate_pct": result.profit_rate_pct,
            "roi_pct": result.roi_pct,
            "npv_won": result.npv_won,
            "grade": result.grade,
            "cost_breakdown_won": result.cost_detail,
            "tax_detail": result.tax_detail,
        },
        "finalized_at": datetime.now().isoformat(),
    }


# ── 다기간 DCF 월별 현금흐름(베팅 B) ──────────────────────────────
class CashflowRequest(BaseModel):
    land_cost_won: float
    construction_cost_won: float
    construction_months: int = 24
    total_revenue_won: float
    sale_start_month: int = 6          # 시공 개시 기준 분양 시작(월)
    sale_duration_months: int = 6
    bridge_loan_rate: float = 0.08
    pf_loan_rate: float = 0.065
    equity_ratio: float = 0.3
    design_months: int = 3
    design_cost_ratio: float = 0.03
    discount_rate_annual: float = 0.06  # NPV 할인율(연)


def _build_cashflow(req: "CashflowRequest") -> dict:
    from app.services.feasibility.cashflow_generator import CashflowGenerator

    cf = CashflowGenerator().generate_monthly_cashflow(
        land_cost=req.land_cost_won,
        construction_cost=req.construction_cost_won,
        construction_months=max(1, req.construction_months),
        total_revenue=req.total_revenue_won,
        sale_start_month=max(0, req.sale_start_month),
        sale_duration_months=max(1, req.sale_duration_months),
        bridge_loan_rate=req.bridge_loan_rate,
        pf_loan_rate=req.pf_loan_rate,
        equity_ratio=req.equity_ratio,
        design_months=max(0, req.design_months),
        design_cost_ratio=req.design_cost_ratio,
    )
    # 월 할인율로 NPV 재계산(엔진 IRR과 별개로 사용자 지정 할인율 반영)
    rmonthly = (1 + req.discount_rate_annual) ** (1 / 12) - 1
    npv = 0.0
    for r in cf["rows"]:
        net = (r.get("inflow", 0) or 0) - (r.get("outflow", 0) or 0)
        m = r.get("month", 0) or 0
        npv += net / ((1 + rmonthly) ** m)
    cf["summary"]["npv_won"] = round(npv)
    cf["summary"]["discount_rate_annual_pct"] = round(req.discount_rate_annual * 100, 2)
    return cf


@router.post("/cashflow")
async def cashflow(req: CashflowRequest):
    """다기간(월별) DCF 현금흐름 + IRR·NPV·peak 자금소요. (은행제출용 정밀 사업성)"""
    try:
        return _build_cashflow(req)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"현금흐름 산정 실패: {str(e)[:160]}")


@router.post("/cashflow/excel")
async def cashflow_excel(req: CashflowRequest):
    """월별 현금흐름을 Excel(xlsx)로 다운로드."""
    try:
        cf = _build_cashflow(req)
        from io import BytesIO
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = Workbook()
        ws = wb.active or wb.create_sheet()
        ws.title = "월별 현금흐름(DCF)"

        # 요약
        s = cf["summary"]
        ws.append(["■ 사업성 요약 (DCF)"])
        ws["A1"].font = Font(bold=True, size=13)
        summary_rows = [
            ("총 분양수입(원)", s.get("total_inflow")),
            ("총 사업비(원)", s.get("total_outflow")),
            ("순이익(원)", s.get("net_profit")),
            ("수익률(%)", s.get("profit_rate_pct")),
            ("IRR(연,%)", s.get("irr_annual_pct")),
            ("NPV(원)", s.get("npv_won")),
            ("할인율(연,%)", s.get("discount_rate_annual_pct")),
            ("최대 자금소요(peak, 원)", s.get("peak_negative_cashflow")),
            ("자기자본(원)", s.get("equity_amount")),
            ("브릿지론(원)", s.get("bridge_loan_amount")),
            ("PF론(원)", s.get("pf_loan_amount")),
        ]
        for k, v in summary_rows:
            ws.append([k, v])
        ws.append([])

        # 월별 표 헤더
        hdr_row = ws.max_row + 1
        headers = ["월", "단계", "유입(원)", "유출(원)", "순현금(원)", "누적현금(원)"]
        ws.append(headers)
        head_fill = PatternFill("solid", fgColor="1F2937")
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=hdr_row, column=c)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center")

        for r in cf["rows"]:
            net = (r.get("inflow", 0) or 0) - (r.get("outflow", 0) or 0)
            ws.append([
                r.get("month"), r.get("phase", ""),
                round(r.get("inflow", 0) or 0), round(r.get("outflow", 0) or 0),
                round(net), round(r.get("cumulative", 0) or 0),
            ])

        # 숫자 포맷·열너비
        for col in ("C", "D", "E", "F"):
            for cell in ws[col]:
                if isinstance(cell.value, (int, float)):
                    cell.number_format = "#,##0"
        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 16
        for col in ("C", "D", "E", "F"):
            ws.column_dimensions[col].width = 18

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=propai_cashflow_dcf.xlsx"},
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"엑셀 생성 실패: {str(e)[:160]}")
