from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Union
from app.services.esg.lca_service import LCAService
from app.services.esg.lcc_service import LCCService
from app.services.esg.epd_carbon_service import EPDCarbonService
from app.services.auth.auth_service import get_current_user
from app.models.auth import User

router = APIRouter(prefix="/api/v1/esg", tags=["ESG"])
lca_service = LCAService()
lcc_service = LCCService()
epd_service = EPDCarbonService()

# ─────────────────────────────────────────────────────────────────────────────
# 신뢰 레이어(additive): ESG 인증/ZEB 법령 근거(legal_refs) 가산.
# 기존 응답 필드는 1개도 변경하지 않고 legal_refs 1블록만 setdefault로 가산한다.
# law.go.kr URL은 legal_reference_registry.get_legal_refs 출력만 사용하며(여기서
# URL 직접 조립 금지), 레지스트리 실존 키만 쓴다 — 녹색건축 인증·건축물 에너지효율
# 등급·제로에너지건축물(ZEB) 인증(근거법: 녹색건축물 조성 지원법, 조문 딥링크
# 미검증 → 법령 루트 링크). 부착 실패 시 원본 무손상 반환(graceful).
# ─────────────────────────────────────────────────────────────────────────────
_ESG_LEGAL_REF_KEYS = ["green_building", "energy_efficiency", "zeb_certification"]


def _attach_esg_legal_refs(result):
    """ESG 산출 응답 dict에 인증 법령 근거를 additive로 부착(in-place).

    기존 키는 setdefault로 보존(이미 있으면 덮어쓰지 않음). result가 dict가
    아니거나 부착 중 예외가 나면 원본을 그대로 반환(기존 응답 무손상).
    """
    if not isinstance(result, dict):
        return result
    try:
        from app.services.legal.legal_reference_registry import get_legal_refs

        result.setdefault("legal_refs", get_legal_refs(_ESG_LEGAL_REF_KEYS))
    except Exception:  # noqa: BLE001
        pass
    return result

class LCAMaterialItem(BaseModel):
    name: str
    quantity_kg: float
    epd_kgco2e: float | None = None   # 제품수준 실측 EPD(있으면 우선 적용)


class LCARequest(BaseModel):
    project_id: str
    # 자재별 수량(dict) 또는 제품 EPD 포함 리스트(제품수준 EPD)
    material_quantities: Union[Dict[str, float], List[LCAMaterialItem]]
    floor_area_sqm: float
    building_type: str = "apartment"
    # BEEC 1차에너지 원단위(kWh/㎡·yr) — 에너지 분석 결과 연동(없으면 표준 원단위)
    energy_intensity_kwh_per_sqm: float | None = None

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
    # 제품 EPD 리스트는 dict 리스트로 변환(서비스 입력 규격)
    mq = req.material_quantities
    if isinstance(mq, list):
        mq = [it.model_dump() for it in mq]
    raw = lca_service.calculate_total_lca(
        mq,
        req.floor_area_sqm,
        building_type=req.building_type,
        energy_intensity_kwh_per_sqm=req.energy_intensity_kwh_per_sqm,
    )

    # ── 프론트(LcaCalculationResponse) 계약에 맞춰 변환 ──
    a1a3 = raw.get("a1_a3", {})
    b6 = raw.get("b6", {})
    whole = raw.get("whole_life", {}) or {}
    a1a3_only = float(a1a3.get("total_gwp_kgco2e", 0) or 0)
    # 체화(embodied) = 전생애 내재(A1-A3+A4+A5+B1-B5+C). 없으면 A1-A3 폴백.
    embodied = float(whole.get("embodied_total_kgco2e", a1a3_only) or a1a3_only)
    operational = float(b6.get("lifecycle_gwp_50yr_kgco2e", 0) or 0)
    total = float(raw.get("total_gwp_kgco2e", embodied + operational) or 0)
    breakdown_src = a1a3.get("breakdown", {}) or {}
    material_breakdown = [
        {
            "material": name,
            "carbon_kgco2e": float(info.get("gwp_kgco2e", 0) or 0),
            "percentage": (
                round(float(info.get("gwp_kgco2e", 0) or 0) / a1a3_only * 100, 1)
                if a1a3_only else 0.0
            ),
        }
        for name, info in breakdown_src.items()
    ]
    material_breakdown.sort(key=lambda x: x["carbon_kgco2e"], reverse=True)

    result = {
        "project_id": req.project_id,
        "embodied_carbon_kgco2e": round(embodied, 1),
        "operational_carbon_kgco2e": round(operational, 1),
        "total_carbon_kgco2e": round(total, 1),
        "carbon_per_sqm_kgco2e": float(raw.get("gwp_per_sqm_kgco2e", 0) or 0),
        "floor_area_sqm": req.floor_area_sqm,
        "material_breakdown": material_breakdown,
        "whole_life": whole,   # EN 15978 단계별(A4·A5·B1-B5·C·D) + 전생애 총계
        "epd_coverage": a1a3.get("epd_coverage"),   # 한국 EPD 적용 자재 비율
        "gwp_basis": a1a3.get("gwp_basis"),
        "ai_analysis": None,
    }

    # ── LLM(Claude) ESG/탄소 해석 → ai_analysis 단일 텍스트로 결합 (graceful fallback) ──
    try:
        from app.services.ai.esg_interpreter import EsgInterpreter

        total_ton = round(total / 1000, 3) if total else 0
        interp = await EsgInterpreter().generate_interpretation({
            "carbon_emissions": {
                "total_emissions_tco2": total_ton,
                "emissions_per_sqm": result["carbon_per_sqm_kgco2e"],
                "scope1": round(embodied / 1000, 3),
                "scope3": round(operational / 1000, 3),
            },
            "building_info": {"total_gfa_sqm": req.floor_area_sqm},
        })
        if isinstance(interp, dict) and interp:
            _labels = {
                "carbon_assessment": "탄소 평가",
                "reduction_strategy": "저감 전략",
                "certification_pathway": "인증 경로",
                "zeb_roadmap": "ZEB 로드맵",
                "esg_investment_impact": "투자 영향",
                "regulatory_outlook": "규제 전망",
            }
            sections = [
                f"[{_labels[k]}] {interp[k]}" for k in _labels if interp.get(k)
            ]
            if sections:
                result["ai_analysis"] = "\n\n".join(sections)
    except Exception:
        pass

    # 인증/ZEB 법령 근거 가산(additive·graceful) — AI 해석의 인증 경로·ZEB 로드맵 근거.
    return _attach_esg_legal_refs(result)

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
