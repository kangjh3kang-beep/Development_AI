from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict
from app.services.avm.avm_service import AVMService
from app.services.auth.auth_service import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/api/v1/avm", tags=["AVM 시세 산출"])
avm_service = AVMService()

class AVMRequest(BaseModel):
    pnu_code: str
    features: dict
    comparables: list[dict]
    target_lat: float
    target_lon: float

@router.post("/estimate")
async def estimate_value(req: AVMRequest, current_user: User = Depends(get_current_user)):
    return avm_service.estimate_value(req.features, req.comparables, req.target_lat, req.target_lon)
