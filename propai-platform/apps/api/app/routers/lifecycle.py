from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.lifecycle.construction.construction_start_service import ConstructionStartService
from app.services.lifecycle.construction.supervision_service import SupervisionService
from app.services.lifecycle.risk.risk_service import RiskService
from app.services.smart_city.smart_city_service import SmartCityService
from app.services.lifecycle_opt.lifecycle_optimizer import LifecycleOptimizer
from app.services.digital_twin.realtime_optimizer import RealtimeTwinOptimizer
from app.services.disaster_risk.disaster_risk_service import DisasterRiskService
from app.services.procurement_opt.procurement_optimizer import ProcurementOptimizer
from app.services.auth.auth_service import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/api/v1/lifecycle", tags=["전주기 관리"])
construction_service = ConstructionStartService()
supervision_service = SupervisionService()
risk_service = RiskService()
smart_city_service = SmartCityService()
lc_optimizer = LifecycleOptimizer()
twin_optimizer = RealtimeTwinOptimizer()
disaster_service = DisasterRiskService()
procurement_optimizer = ProcurementOptimizer()

class ConstructionStartRequest(BaseModel):
    project_id: str
    project_type: str
    project_cost_krw: float
    floor_count: int
    excavation_depth_m: float = 0.0

class EVMRequest(BaseModel):
    bac_krw: float
    pv_krw: float
    ev_pct: float
    ac_krw: float

class DisasterRiskRequest(BaseModel):
    region: str
    land_use: str = "공동주택"
    floor_count: int
    distance_to_river_m: float = 500

class EOQRequest(BaseModel):
    material_name: str
    annual_demand: float
    order_cost_krw: float

@router.post("/construction/checklist")
async def get_construction_checklist(req: ConstructionStartRequest,
                                      current_user: User = Depends(get_current_user)):
    return construction_service.generate_checklist(req.project_type, req.project_cost_krw)

@router.post("/construction/safety-plan")
async def generate_safety_plan(req: ConstructionStartRequest,
                                current_user: User = Depends(get_current_user)):
    return construction_service.auto_generate_safety_plan(
        req.project_id, f"프로젝트 {req.project_id}", req.floor_count, req.excavation_depth_m)

@router.post("/supervision/evm")
async def calculate_evm(req: EVMRequest, current_user: User = Depends(get_current_user)):
    return supervision_service.calculate_evm(req.bac_krw, req.pv_krw, req.ev_pct, req.ac_krw)

@router.get("/risk/assessment")
async def get_risk_assessment(current_user: User = Depends(get_current_user)):
    return risk_service.calculate_risk_scores()

@router.post("/disaster-risk/assess")
async def assess_disaster_risk(req: DisasterRiskRequest, current_user: User = Depends(get_current_user)):
    return disaster_service.assess_disaster_risk(req.region, req.land_use, req.floor_count, req.distance_to_river_m)

@router.post("/procurement/eoq")
async def calculate_eoq(req: EOQRequest, current_user: User = Depends(get_current_user)):
    return procurement_optimizer.calculate_eoq(req.annual_demand, req.order_cost_krw)

@router.get("/lifecycle-opt/replacement-schedule")
async def get_replacement_schedule(construction_cost_krw: float, lifespan_years: int = 50,
                                    current_user: User = Depends(get_current_user)):
    return lc_optimizer.optimize_replacement_schedule(construction_cost_krw, lifespan_years)
