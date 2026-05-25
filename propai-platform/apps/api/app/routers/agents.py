from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from app.services.agents.orchestrator import create_propai_graph, ProjectState
from app.services.auth.auth_service import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/api/v1/agents", tags=["멀티에이전트"])

class AgentRequest(BaseModel):
    project_id: str
    pnu_codes: List[str]
    zone_type: str = "제2종일반주거지역"
    estimated_cost_krw: float = 10_000_000_000
    estimated_revenue_krw: float = 15_000_000_000

@router.post("/run-full-cycle")
async def run_full_cycle(req: AgentRequest, current_user: User = Depends(get_current_user)):
    graph = create_propai_graph()
    initial_state = ProjectState(
        project_id=req.project_id, pnu_codes=req.pnu_codes,
        zone_rules={"zone_type": req.zone_type, "far": 200, "bcr": 50, "height": 30},
        design_params={"estimated_cost_krw": req.estimated_cost_krw,
                       "estimated_revenue_krw": req.estimated_revenue_krw},
        feasibility_result={}, esg_result={}, permit_status="pending",
        construction_plan={}, current_stage="init", messages=[], errors=[]
    )
    result = await graph.ainvoke(initial_state)
    return result
