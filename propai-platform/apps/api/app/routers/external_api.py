
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models.auth import User
from app.services.auth.auth_service import get_current_user
from app.services.external_api.molit_service import MOLITService
from app.services.external_api.vworld_service import VWorldService

router = APIRouter(prefix="/api/v1/external", tags=["외부 API"])
vworld = VWorldService()
molit = MOLITService()

class PNURequest(BaseModel):
    pnu: str | None = None       # 프론트 표준 필드
    pnu_code: str | None = None  # 하위호환
    address: str | None = None   # PNU 미보유 시 주소→PNU 지오코딩 폴백

class MergeRequest(BaseModel):
    pnu_codes: list[str]

@router.post("/parcel/info")
async def get_parcel_info(req: PNURequest, current_user: User = Depends(get_current_user)):
    """필지 정보(지목·용도지역·면적·이용상황·공시지가·도로접면·지형) 조회.

    ★수정: 기존엔 get_parcel_by_pnu(기하정보만) 반환 → 프론트가 기대하는 토지특성 필드와
    불일치해 전부 빈값이었음. NED getLandCharacteristics(지목·용도지역·공시지가 등)로 교정하고,
    PNU 미보유 시 주소→PNU 지오코딩으로 폴백한다.
    """
    code = req.pnu or req.pnu_code
    # PNU 없고 주소 있으면 지오코딩으로 PNU 도출(필지정보 누락 해소).
    if not code and req.address and req.address.strip():
        geo = await vworld.geocode_address(req.address.strip())
        code = (geo or {}).get("pnu")
    if not code:
        raise HTTPException(status_code=422, detail="pnu 또는 address가 필요합니다")

    lc = await vworld.get_land_characteristics(code)
    if not lc:
        raise HTTPException(status_code=404, detail="필지 정보를 찾을 수 없음")
    resp = {
        "pnu": lc.get("pnu", code),
        "address": req.address or "",
        "land_category": lc.get("land_category", "") or "",
        "zoning": lc.get("zone_type", "") or "",
        "area_sqm": lc.get("area_sqm", 0) or 0,
        "land_use_situation": lc.get("land_use_situation", "") or "",
        "official_price_per_sqm": lc.get("official_price_per_sqm", 0) or 0,
        "road_side": lc.get("road_side", "") or "",
        "terrain": (lc.get("terrain_form") or lc.get("terrain_height") or "") or "",
        "restrictions": [z for z in [lc.get("zone_type_2")] if z],
    }
    # W3-7(설명가능성 기본화): 프론트(ProjectSiteAnalysisWorkspaceClient)가 선언만 하고
    # 항상 비어 있던 신뢰메타(legal_refs·inputs)를 additive 부착 — parcels-info와 동일
    # 빌더 재사용(URL은 legal_reference_registry 출력만, zone 미확정이면 빈 배열=무날조).
    try:
        from apps.api.routers.auto_zoning import _build_inputs, _build_legal_refs

        _shaped = {
            "pnu": resp["pnu"],
            "zone_type": resp["zoning"],
            "land_area_sqm": resp["area_sqm"],
            "official_price_per_sqm": resp["official_price_per_sqm"],
            "address": resp["address"],
        }
        resp["legal_refs"] = _build_legal_refs(_shaped)
        resp["inputs"] = _build_inputs(_shaped)
    except Exception:  # noqa: BLE001 — 신뢰메타 부착 실패는 본 응답을 막지 않음(additive)
        resp.setdefault("legal_refs", [])
    return resp

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
