from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from app.services.auth.auth_service import get_current_user
from app.services.external_api.vworld_service import VWorldService
from app.services.external_api.molit_service import MOLITService
from app.models.auth import User

router = APIRouter(prefix="/api/v1/external", tags=["외부 API"])
vworld = VWorldService()
molit = MOLITService()

class PNURequest(BaseModel):
    pnu: str | None = None       # 프론트 표준 필드
    pnu_code: str | None = None  # 하위호환

class MergeRequest(BaseModel):
    pnu_codes: List[str]

@router.post("/parcel/info")
async def get_parcel_info(req: PNURequest, current_user: User = Depends(get_current_user)):
    code = req.pnu or req.pnu_code
    if not code:
        raise HTTPException(status_code=422, detail="pnu 필드가 필요합니다")
    result = await vworld.get_parcel_by_pnu(code)
    if not result:
        raise HTTPException(status_code=404, detail="필지 정보를 찾을 수 없음")
    return result

@router.post("/parcel/merge")
async def merge_parcels(req: MergeRequest, current_user: User = Depends(get_current_user)):
    result = await vworld.merge_parcels_gis_union(req.pnu_codes)
    if not result:
        raise HTTPException(status_code=422, detail="필지 통합 실패")
    return result

@router.get("/transactions/apt")
async def get_apt_transactions(lawd_cd: str, deal_ym: str,
                                current_user: User = Depends(get_current_user)):
    items = await molit.get_apt_transactions(lawd_cd, deal_ym)
    return {"items": items, "total_count": len(items)}
