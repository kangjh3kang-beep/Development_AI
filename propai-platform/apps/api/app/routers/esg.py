from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict
from app.services.esg.lca_service import LCAService
from app.services.esg.lcc_service import LCCService
from app.services.esg.epd_carbon_service import EPDCarbonService
from app.services.auth.auth_service import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/api/v1/esg", tags=["ESG"])
lca_service = LCAService()
lcc_service = LCCService()
epd_service = EPDCarbonService()

class LCARequest(BaseModel):
    project_id: str
    material_quantities: Dict[str, float]
    floor_area_sqm: float

class LCCRequest(BaseModel):
    construction_cost_krw: float
    annual_maintenance_krw: float
    annual_energy_krw: float
    lifecycle_years: int = 50
    discount_rate: float = 0.03

class EPDRequest(BaseModel):
    material_list: List[Dict]

@router.post("/lca/calculate")
async def calculate_lca(req: LCARequest, current_user: User = Depends(get_current_user)):
    return lca_service.calculate_total_lca(req.material_quantities, req.floor_area_sqm)

@router.post("/lcc/calculate")
async def calculate_lcc(req: LCCRequest, current_user: User = Depends(get_current_user)):
    return lcc_service.calculate_lcc(req.construction_cost_krw, req.annual_maintenance_krw,
                                      req.annual_energy_krw, req.lifecycle_years, req.discount_rate)

@router.post("/epd/carbon-footprint")
async def calculate_epd_carbon(req: EPDRequest, current_user: User = Depends(get_current_user)):
    return epd_service.calculate_material_carbon(req.material_list)

@router.post("/epd/low-carbon-alternatives")
async def get_low_carbon_alternatives(material_name: str, quantity_kg: float,
                                       current_user: User = Depends(get_current_user)):
    return epd_service.recommend_low_carbon_alternatives(material_name, quantity_kg)
