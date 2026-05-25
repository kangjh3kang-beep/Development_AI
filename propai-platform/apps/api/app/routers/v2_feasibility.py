"""수지분석 v2 API 라우터 — 12개 엔드포인트 (Excel 내보내기 포함)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

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
from app.services.feasibility.version_control import FeasibilityVCS
from app.services.feasibility.sensitivity_engine import run_sensitivity_analysis

router = APIRouter(prefix="/api/v2/feasibility", tags=["feasibility-v2"])

_service = FeasibilityServiceV2()
_vcs_instances: dict[str, FeasibilityVCS] = {}


def _get_vcs(project_id: str) -> FeasibilityVCS:
    if project_id not in _vcs_instances:
        _vcs_instances[project_id] = FeasibilityVCS()
    return _vcs_instances[project_id]


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
async def vcs_commit(project_id: str, req: VCSCommitRequest):
    """수지분석 커밋."""
    vcs = _get_vcs(project_id)
    c = vcs.commit(req.snapshot, req.message)
    return {"sha": c.sha, "message": c.message, "timestamp": c.timestamp}


@router.post("/repos/{project_id}/rollback")
async def vcs_rollback(project_id: str, req: VCSRollbackRequest):
    """수지분석 롤백."""
    vcs = _get_vcs(project_id)
    c = vcs.rollback(req.target_sha)
    if not c:
        raise HTTPException(status_code=404, detail="커밋을 찾을 수 없습니다")
    return {"sha": c.sha, "message": c.message}


@router.get("/repos/{project_id}/log")
async def vcs_log(project_id: str, max_count: int = 50):
    """커밋 이력."""
    vcs = _get_vcs(project_id)
    log = vcs.log(max_count)
    return {
        "commits": [
            {"sha": c.sha, "message": c.message, "parent_sha": c.parent_sha, "timestamp": c.timestamp}
            for c in log
        ]
    }


@router.get("/repos/{project_id}/diff/{sha_a}/{sha_b}")
async def vcs_diff(project_id: str, sha_a: str, sha_b: str):
    """두 커밋 간 diff."""
    vcs = _get_vcs(project_id)
    return vcs.diff(sha_a, sha_b)


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
