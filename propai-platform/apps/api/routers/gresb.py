from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from apps.api.app.services.esg.gresb_scoring_service import (
    BENCHMARK_META,
    BENCHMARKS,
    GRESB_COMPONENTS,
    GresbScoringService,
)

router = APIRouter()


class GresbScoreRequest(BaseModel):
    building_type: str = "apartment"
    energy_kwh_per_sqm: Optional[float] = None
    ghg_kg_per_sqm: Optional[float] = None
    water_l_per_sqm: Optional[float] = None
    has_esg_policy: bool = False
    has_green_cert: bool = False
    green_cert_level: str = "none"
    waste_recycling_pct: float = 0.0
    renewable_energy_pct: float = 0.0
    lca_total_carbon_kg: Optional[float] = None
    floor_area_sqm: float = 1000


@router.post("/score")
async def calculate_gresb_score(req: GresbScoreRequest):
    service = GresbScoringService()
    return service.calculate_score(**req.model_dump())


@router.get("/benchmarks")
async def get_benchmarks():
    return {
        "benchmarks": BENCHMARKS,
        "components": GRESB_COMPONENTS,
        "meta": BENCHMARK_META,
    }
