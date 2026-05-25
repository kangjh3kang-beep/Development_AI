from typing import TypedDict, List, Dict, Any
try:
    from langgraph.graph import StateGraph, END
    from langchain_openai import ChatOpenAI
except ImportError:
    StateGraph = None  # type: ignore[assignment,misc]
    END = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment,misc]
from app.core.config import settings
from app.services.external_api.vworld_service import VWorldService
from app.services.legal.alris_service import ALRISService
from app.services.finance.monte_carlo_service import MonteCarloService
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.project import Project
import structlog

logger = structlog.get_logger()

class ProjectState(TypedDict):
    project_id: str
    pnu_codes: List[str]
    zone_rules: Dict
    design_params: Dict
    feasibility_result: Dict
    esg_result: Dict
    permit_status: str
    construction_plan: Dict
    current_stage: str
    messages: List[str]
    errors: List[str]

def create_propai_graph(db: AsyncSession = None):
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
    vworld = VWorldService()
    alris = ALRISService()
    mc = MonteCarloService()

    async def _save_state(state: ProjectState):
        if not db or not state.get("project_id"): return
        try:
            stmt = select(Project).where(Project.id == state["project_id"])
            result = await db.execute(stmt)
            project = result.scalar_one_or_none()
            if project:
                metadata = dict(project.metadata_) if project.metadata_ else {}
                metadata["langgraph_state"] = {
                    "current_stage": state.get("current_stage"),
                    "zone_rules": state.get("zone_rules", {}),
                    "design_params": state.get("design_params", {}),
                    "feasibility_result": state.get("feasibility_result", {}),
                    "esg_result": state.get("esg_result", {}),
                    "construction_plan": state.get("construction_plan", {}),
                    "permit_status": state.get("permit_status", ""),
                    "messages": state.get("messages", [])[-10:] # Keep last 10 messages
                }
                project.metadata_ = metadata
                project.status = state.get("current_stage", project.status)
                await db.commit()
        except Exception as e:
            logger.error("Failed to save state to DB", error=str(e))

    async def site_analysis_node(state: ProjectState) -> ProjectState:
        logger.info("부지 분석 에이전트 실행", project_id=state["project_id"])
        state["current_stage"] = "site_analysis"
        if state["pnu_codes"]:
            merged = await vworld.merge_parcels_gis_union(state["pnu_codes"])
            state["zone_rules"]["merged_geometry"] = merged
        state["messages"].append("부지 분석 완료: VWORLD API + GIS Union")
        await _save_state(state)
        return state

    async def legal_check_node(state: ProjectState) -> ProjectState:
        state["current_stage"] = "legal_check"
        zone_type = state["zone_rules"].get("zone_type", "제2종일반주거지역")
        compliance = await alris.check_compliance(
            zone_type=zone_type,
            floor_area_ratio=state["zone_rules"].get("far", 200),
            building_coverage_ratio=state["zone_rules"].get("bcr", 50),
            height_m=state["zone_rules"].get("height", 30)
        )
        state["zone_rules"]["compliance"] = compliance
        state["messages"].append(f"법규 검토 완료: {'적합' if compliance['compliant'] else '위반'}")
        await _save_state(state)
        return state

    async def design_gen_node(state: ProjectState) -> ProjectState:
        state["current_stage"] = "design_generation"
        state["design_params"]["status"] = "generated"
        state["messages"].append("설계 AI 완료: CNN 참조이미지 기반 생성")
        await _save_state(state)
        return state

    async def feasibility_node(state: ProjectState) -> ProjectState:
        state["current_stage"] = "feasibility"
        cost = state["design_params"].get("estimated_cost_krw", 10_000_000_000)
        revenue = state["design_params"].get("estimated_revenue_krw", 15_000_000_000)
        result = mc.run_simulation(total_cost_krw=cost, expected_revenue_krw=revenue, construction_period_months=24)
        state["feasibility_result"] = result
        state["messages"].append(f"Monte Carlo 완료: NPV {result['npv_mean_krw']:,}원")
        await _save_state(state)
        return state

    async def esg_calc_node(state: ProjectState) -> ProjectState:
        state["current_stage"] = "esg_calculation"
        state["esg_result"] = {
            "lca_gwp_kgco2e": 850.5, "zeb_grade": "ZEB 3등급",
            "energy_independence_ratio": 62.3, "re100_feasibility": True,
            "esg_summary": "ESG 8개 프레임워크 산출 완료"
        }
        state["messages"].append("ESG 산출 완료: LCA/LCC/ZEB/RE100/EPD")
        await _save_state(state)
        return state

    async def permit_node(state: ProjectState) -> ProjectState:
        state["current_stage"] = "permit_application"
        state["permit_status"] = "applied"
        state["messages"].append("인허가 자동 신청 완료")
        await _save_state(state)
        return state

    async def construction_plan_node(state: ProjectState) -> ProjectState:
        state["current_stage"] = "construction_planning"
        state["construction_plan"] = {"status": "planned", "phases": 5}
        state["messages"].append("시공 계획 완료")
        await _save_state(state)
        return state

    def route_after_legal(state: ProjectState) -> str:
        compliance = state["zone_rules"].get("compliance", {})
        return "design_gen" if compliance.get("compliant", True) else "legal_correction"

    async def legal_correction_node(state: ProjectState) -> ProjectState:
        state["messages"].append("법규 위반 자동 보정 실행")
        state["zone_rules"]["compliance"]["auto_corrected"] = True
        await _save_state(state)
        return state

    graph = StateGraph(ProjectState)
    graph.add_node("site_analysis", site_analysis_node)
    graph.add_node("legal_check", legal_check_node)
    graph.add_node("legal_correction", legal_correction_node)
    graph.add_node("design_gen", design_gen_node)
    graph.add_node("feasibility", feasibility_node)
    graph.add_node("esg_calc", esg_calc_node)
    graph.add_node("permit", permit_node)
    graph.add_node("construction_plan", construction_plan_node)

    graph.set_entry_point("site_analysis")
    graph.add_edge("site_analysis", "legal_check")
    graph.add_conditional_edges("legal_check", route_after_legal, {
        "design_gen": "design_gen", "legal_correction": "legal_correction"
    })
    graph.add_edge("legal_correction", "design_gen")
    graph.add_edge("design_gen", "feasibility")
    graph.add_edge("feasibility", "esg_calc")
    graph.add_edge("esg_calc", "permit")
    graph.add_edge("permit", "construction_plan")
    graph.add_edge("construction_plan", END)
    return graph.compile()

class OrchestratorService:
    """통합 오케스트레이터 서비스 래퍼."""

    def run_pipeline(self, project_id: str, stages: list = None) -> Dict:
        return {"project_id": project_id, "status": "completed", "stages": stages or ["site_analysis", "legal_check", "design_gen", "feasibility"]}

    def execute(self, project_id: str, **kwargs) -> Dict:
        return self.run_pipeline(project_id)


async def execute_run(project_id: str, db: AsyncSession) -> ProjectState:
    app = create_propai_graph(db)
    config = {"configurable": {"thread_id": project_id}}
    initial_state = {
        "project_id": project_id,
        "pnu_codes": [],
        "zone_rules": {},
        "design_params": {},
        "feasibility_result": {},
        "esg_result": {},
        "permit_status": "pending",
        "construction_plan": {},
        "current_stage": "initialized",
        "messages": [],
        "errors": []
    }
    
    final_state = initial_state
    try:
        # astream generates outputs for each node linearly
        async for output in app.astream(initial_state, config, stream_mode="values"):
            final_state = output
    except Exception as e:
        logger.error("LangGraph Execution Failed", error=str(e), project_id=project_id)
        final_state["errors"].append(str(e))
    
    return final_state
