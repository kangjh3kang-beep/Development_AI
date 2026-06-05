"""D3 설계변경 사전예측 라우터.

착공 전 설계변경 유발 리스크(법규초과·필수요소 누락·정량 정합성 모순)를
사전 예측하고 보완방안(절감 포함)을 제시한다. 룰기반 우선, AI 보조(use_llm시).

prefix: /api/v1/design-risk
정직성: 결과는 사전 예측·경고이며 확정이 아니다(전문가 검토 필요).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.design_risk.design_change_predictor import (
    DesignChangePredictor,
    generate_ai_remedies,
)

router = APIRouter(prefix="/api/v1/design-risk", tags=["설계변경 사전예측(D3)"])

_predictor = DesignChangePredictor()

_BADGE_NOTE = "사전예측·확정아님·전문가검토필요(건축사·구조기술사). 3D 간섭(clash)은 범위 외 — 정량 정합만 점검."


class DesignParams(BaseModel):
    """설계 파라미터(있는 값만). 없으면 좌표/매스로 추정 보강."""

    floors: Optional[int] = Field(None, ge=0, description="지상 층수")
    floor_height_m: Optional[float] = Field(None, gt=0, description="층고(m), 기본 3.0")
    gfa: Optional[float] = Field(None, gt=0, description="연면적(㎡)")
    bcr: Optional[float] = Field(None, ge=0, description="계획 건폐율(%)")
    far: Optional[float] = Field(None, ge=0, description="계획 용적률(%)")
    height_m: Optional[float] = Field(None, ge=0, description="건물 높이(m)")
    parking: Optional[int] = Field(None, ge=0, description="계획 주차대수")
    units: Optional[int] = Field(None, ge=0, description="세대/호수")
    building_type: Optional[str] = Field(None, description="건물 용도(아파트·근린생활시설 등)")
    avg_unit_area_sqm: Optional[float] = Field(None, gt=0, description="평균 전용면적(㎡)")
    land_area_sqm: Optional[float] = Field(None, gt=0, description="대지면적(㎡)")
    building_area_sqm: Optional[float] = Field(None, gt=0, description="건축면적(㎡)")


class PredictRequest(BaseModel):
    address: Optional[str] = None
    pnu: Optional[str] = None
    zone_type: Optional[str] = None
    design_params: Optional[DesignParams] = None
    use_llm: bool = False


def _derive_bcr_far_height(d: dict[str, Any]) -> dict[str, Any]:
    """입력 결손값을 보수적으로 보강(추정은 추정으로 표기되도록 별도 마킹).

    - bcr 없고 building_area·land_area 있으면 산정.
    - far 없고 gfa·land_area 있으면 산정.
    - height 없고 floors 있으면 floors×층고로 추정.
    """
    derived: list[str] = []
    land = d.get("land_area_sqm")
    if d.get("bcr") is None and d.get("building_area_sqm") and land:
        d["bcr"] = d["building_area_sqm"] / land * 100
        derived.append("건폐율(건축면적/대지 산정·추정)")
    if d.get("far") is None and d.get("gfa") and land:
        d["far"] = d["gfa"] / land * 100
        derived.append("용적률(연면적/대지 산정·추정)")
    if d.get("height_m") is None and d.get("floors"):
        fh = d.get("floor_height_m") or 3.0
        d["height_m"] = d["floors"] * fh
        derived.append(f"높이(층수×층고 {fh}m 추정)")
    d["_derived"] = derived
    return d


async def _augment_from_site(
    address: Optional[str], pnu: Optional[str], zone_type: Optional[str]
) -> dict[str, Any]:
    """좌표/주소 → auto_zoning으로 용도지역·대지면적 보강(키 없으면 graceful)."""
    out: dict[str, Any] = {"zone_type": zone_type, "land_area_sqm": None, "source": None}
    if zone_type and not address and not pnu:
        return out
    if not address and not pnu:
        return out
    try:
        from app.services.zoning.auto_zoning_service import AutoZoningService

        svc = AutoZoningService()
        z = await svc.analyze_by_address(address or pnu or "")
        if z:
            out["zone_type"] = zone_type or z.get("zone_type")
            out["land_area_sqm"] = z.get("land_area_sqm")
            out["source"] = "auto_zoning_service(VWorld/NED)"
    except Exception:  # noqa: BLE001 — 외부키 미설정 등은 graceful, 예측은 계속
        pass
    return out


@router.post("/predict")
async def predict_design_change(req: PredictRequest) -> dict[str, Any]:
    """설계변경 사전예측 — 3종 리스크 + 보완방안.

    Req: {address?, pnu?, zone_type?, design_params?{...}, use_llm?}
    design_params 없으면 좌표→용도지역/대지 보강. 좌표·설계 둘다 불가 → ok:false.
    """
    sources: list[str] = []

    # 1) 부지 보강(용도지역·대지면적)
    site = await _augment_from_site(req.address, req.pnu, req.zone_type)
    zone_type = site.get("zone_type") or req.zone_type or ""
    if site.get("source"):
        sources.append(site["source"])

    # 2) 설계 파라미터 구성
    design: dict[str, Any] = {}
    if req.design_params is not None:
        design = req.design_params.model_dump(exclude_none=True)
    if "land_area_sqm" not in design and site.get("land_area_sqm"):
        design["land_area_sqm"] = site["land_area_sqm"]
        sources.append("대지면적: auto_zoning")

    # 좌표·설계 둘 다 없으면 예측 불가
    has_site = bool(zone_type) or bool(site.get("land_area_sqm"))
    has_design = bool(design)
    if not has_design and not has_site:
        return {
            "ok": False,
            "error": "설계 파라미터(design_params) 또는 부지 정보(address/pnu/zone_type) 중 "
            "최소 하나가 필요합니다.",
            "badges": {"note": _BADGE_NOTE, "data_basis": "입력 없음"},
        }

    design = _derive_bcr_far_height(design)
    derived = design.pop("_derived", [])

    # 3) 룰기반 3종 예측
    prediction = _predictor.predict(design, zone_type)
    risks = prediction["risks"]
    summary = prediction["summary"]
    data_gaps = list(prediction.get("data_gaps", []))
    if derived:
        data_gaps.append("추정 보강값: " + ", ".join(derived))

    # 4) AI 통합 보완 전략(use_llm시만, 실패시 룰 폴백)
    ai_remedy: dict[str, str] = {}
    if req.use_llm:
        ai_remedy = await generate_ai_remedies(prediction, zone_type)
        sources.append("AI 보완전략: Claude(룰 폴백 보장)")

    data_basis = "룰기반(건축법·주차장법·국토계획법 정량 한도)"
    if req.use_llm:
        data_basis += " + AI 보조"
    if not zone_type:
        data_basis += " · 용도지역 미상(법규초과 예측 제한)"

    return {
        "ok": True,
        "address": req.address,
        "zone_type": zone_type or None,
        "summary": summary,
        "risks": risks,
        "ai_remedy": ai_remedy or None,
        "badges": {
            "note": _BADGE_NOTE,
            "data_basis": data_basis,
        },
        "limits_used": prediction.get("limits_used"),
        "data_gaps": data_gaps,
        "sources": sources or ["사용자 입력 설계 파라미터"],
    }
