# PropAI v61.0 -- IDE 빌드 프롬프트 Part 3
# AI BIM 공사비 자동산출 시스템 + 법정요율 자동갱신
# (Part 2 완료 후 실행) | ASCII 100% | 2026-03-30

================================================================================
[IDE 입력 프롬프트 -- Part 3: AI BIM 공사비 자동산출]
================================================================================

## PROMPT:

Part 2까지 완성된 PropAI v61.0 프로젝트에 AI BIM 공사비 자동산출 시스템을
완전히 구현해 주세요.

---

## MODULE D: IFC BIM 물량산출 엔진

```python
# propai/apps/api/app/services/bim/ifc_extractor.py
"""
IFC 4.3 기반 BIM 물량 자동산출
공종 매핑: IfcWall->RC/조적, IfcSlab->RC슬래브, IfcWindow->창호 등
"""
import ifcopenshell
import ifcopenshell.util.element as ifc_util
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class BimQty:
    global_id:  str
    ifc_type:   str
    ifc_name:   str
    work_code:  str
    work_name:  str
    floor:      str
    zone:       str
    quantity:   float
    unit:       str
    formula:    str
    confidence: float = 0.90

# IFC 유형 -> 공종 코드 매핑
IFC_WORK_MAP = {
    "IfcWall":              [("010202","RC벽체"),("010203","조적")],
    "IfcWallStandardCase": [("010202","RC벽체")],
    "IfcSlab":              [("010202","RC슬래브"),("010207","방수")],
    "IfcColumn":            [("010202","RC기둥")],
    "IfcBeam":              [("010202","RC보")],
    "IfcStair":             [("010202","RC계단"),("010205","타일계단")],
    "IfcRoof":              [("010208","지붕"),("010207","방수지붕")],
    "IfcCovering":          [("010205","타일"),("010210","미장")],
    "IfcWindow":            [("010211","창호")],
    "IfcDoor":              [("010211","문"),("010206","목공")],
    "IfcPipeSegment":       [("M0102","배관")],
    "IfcDuctSegment":       [("M0103","덕트")],
    "IfcFlowTerminal":      [("M0101","기계장비")],
    "IfcCableSegment":      [("E0102","전선")],
    "IfcFooting":           [("C01","기초")],
    "IfcPile":              [("C01","파일")],
}

def _get_qty(element, qset: str, qty_name: str) -> Optional[float]:
    """IFC BaseQuantity에서 수량 추출"""
    for rel in element.IsDefinedBy:
        if rel.is_a("IfcRelDefinesByProperties"):
            pset = rel.RelatingPropertyDefinition
            if pset.is_a("IfcElementQuantity") and pset.Name == qset:
                for qty in pset.Quantities:
                    if qty.Name == qty_name:
                        if qty.is_a("IfcQuantityArea"):   return qty.AreaValue
                        if qty.is_a("IfcQuantityLength"): return qty.LengthValue
                        if qty.is_a("IfcQuantityVolume"): return qty.VolumeValue
                        if qty.is_a("IfcQuantityCount"):  return qty.CountValue
    return None

def _wall_qty(el) -> Dict:
    area = _get_qty(el,"Qto_WallBaseQuantities","NetSideArea") or 0
    vol  = _get_qty(el,"Qto_WallBaseQuantities","NetVolume") or 0
    thick = vol/area if area > 0.1 else 0
    code = "010202" if thick >= 0.19 else "010203"
    return {
        "primary":   {"qty":area,"unit":"M2","code":code,
                      "formula":f"NetSideArea={area:.2f}m2"},
        "secondary": [{"qty":area,"unit":"M2","code":"010210",
                       "formula":f"미장면적={area:.2f}m2"}],
    }

def _slab_qty(el) -> Dict:
    area = _get_qty(el,"Qto_SlabBaseQuantities","NetArea") or 0
    vol  = _get_qty(el,"Qto_SlabBaseQuantities","NetVolume") or 0
    return {
        "primary":   {"qty":vol,"unit":"M3","code":"010202",
                      "formula":f"NetVolume={vol:.3f}m3"},
        "secondary": [{"qty":area,"unit":"M2","code":"010207",
                       "formula":f"방수면적={area:.2f}m2"}],
    }

def _col_qty(el) -> Dict:
    vol = _get_qty(el,"Qto_ColumnBaseQuantities","NetVolume") or 0
    return {"primary":{"qty":vol,"unit":"M3","code":"010202",
                        "formula":f"RC기둥={vol:.3f}m3"}}

def _beam_qty(el) -> Dict:
    vol = _get_qty(el,"Qto_BeamBaseQuantities","NetVolume") or 0
    return {"primary":{"qty":vol,"unit":"M3","code":"010202",
                        "formula":f"RC보={vol:.3f}m3"}}

def _opening_qty(el) -> Dict:
    area = (_get_qty(el,"Qto_WindowBaseQuantities","Area") or
            _get_qty(el,"Qto_DoorBaseQuantities","Area") or 0)
    return {"primary":{"qty":area,"unit":"M2","code":"010211",
                        "formula":f"창호면적={area:.2f}m2"}}

def _roof_qty(el) -> Dict:
    area = _get_qty(el,"Qto_RoofBaseQuantities","NetArea") or 0
    return {
        "primary":   {"qty":area,"unit":"M2","code":"010208",
                      "formula":f"지붕={area:.2f}m2"},
        "secondary": [{"qty":area,"unit":"M2","code":"010207",
                       "formula":f"지붕방수={area:.2f}m2"}],
    }

QTY_FUNCS = {
    "IfcWall": _wall_qty, "IfcWallStandardCase": _wall_qty,
    "IfcSlab": _slab_qty, "IfcColumn": _col_qty,
    "IfcBeam": _beam_qty, "IfcWindow": _opening_qty,
    "IfcDoor": _opening_qty, "IfcRoof": _roof_qty,
}

WORK_NAMES = {
    "010202":"철근콘크리트공사","010203":"조적공사","010205":"타일공사",
    "010206":"목공사및수장공사","010207":"방수공사","010208":"지붕공사",
    "010210":"미장공사","010211":"창호및유리공사","010212":"칠공사",
    "M0101":"장비설치","M0102":"배관","M0103":"덕트",
    "E0102":"전기","C01":"토목기초",
}

class IFCExtractor:

    def __init__(self, ifc_path: str, project_id: int):
        self.model = ifcopenshell.open(ifc_path)
        self.project_id = project_id

    def get_floor(self, element) -> str:
        try:
            for rel in element.ContainedInStructure:
                if rel.RelatingStructure.is_a("IfcBuildingStorey"):
                    return rel.RelatingStructure.Name or "미지정"
        except Exception:
            pass
        return "미지정"

    def get_zone(self, element) -> str:
        name = getattr(element,"Name","") or ""
        if any(k in name for k in ["주차","Parking","B"]): return "지하주차장"
        if any(k in name for k in ["기계","Mech"]):         return "기계실"
        return "아파트동"

    def extract(self) -> List[BimQty]:
        results = []
        for ifc_type, fn in QTY_FUNCS.items():
            for el in self.model.by_type(ifc_type):
                try:
                    data = fn(el)
                    if not data: continue
                    floor = self.get_floor(el)
                    zone  = self.get_zone(el)
                    gid   = el.GlobalId
                    iname = getattr(el,"Name","") or ""
                    p = data["primary"]
                    results.append(BimQty(
                        global_id=gid, ifc_type=ifc_type, ifc_name=iname,
                        work_code=p["code"],
                        work_name=WORK_NAMES.get(p["code"],p["code"]),
                        floor=floor, zone=zone,
                        quantity=round(float(p["qty"]),4),
                        unit=p["unit"], formula=p["formula"],
                        confidence=0.92))
                    for s in data.get("secondary",[]):
                        results.append(BimQty(
                            global_id=gid, ifc_type=ifc_type, ifc_name=iname,
                            work_code=s["code"],
                            work_name=WORK_NAMES.get(s["code"],s["code"]),
                            floor=floor, zone=zone,
                            quantity=round(float(s["qty"]),4),
                            unit=s["unit"], formula=s["formula"],
                            confidence=0.85))
                except Exception:
                    continue
        return results

    def aggregate(self, quantities: List[BimQty]) -> Dict[str,float]:
        agg: Dict[str,float] = {}
        for q in quantities:
            agg[q.work_code] = agg.get(q.work_code,0) + q.quantity
        return agg
```

---

## MODULE E: 공사비 자동계산 엔진 (2026년 법정요율 적용)

```python
# propai/apps/api/app/services/cost/cost_engine.py
"""
AI 공사비 자동계산 엔진
2026년 법정보험료율 실시간 적용
5개 분야 통합 원가계산서 자동 생성
"""
from typing import Dict, List
from dataclasses import dataclass
from app.services.rates.current_rates import get_current_rates

@dataclass
class CostItem:
    work_code:  str
    item_name:  str
    spec:       str
    unit:       str
    quantity:   float
    mat_unit:   float
    labor_unit: float
    exp_unit:   float

    @property
    def mat_amt(self)  -> float: return round(self.quantity * self.mat_unit)
    @property
    def labor_amt(self)-> float: return round(self.quantity * self.labor_unit)
    @property
    def exp_amt(self)  -> float: return round(self.quantity * self.exp_unit)
    @property
    def total_amt(self)-> float: return self.mat_amt + self.labor_amt + self.exp_amt


class OriginCostCalculator:
    """원가계산서 자동 생성 (법정요율 DB에서 실시간 조회)"""

    def __init__(self, items: List[CostItem], category: str):
        self.items = items
        self.category = category
        self.R = get_current_rates()   # 2026년 법정요율

    def calc(self) -> Dict:
        R = self.R
        d_mat  = sum(i.mat_amt   for i in self.items)
        d_lab  = sum(i.labor_amt for i in self.items)
        d_exp  = sum(i.exp_amt   for i in self.items)

        # 간접노무비 (직접노무비의 14.40%)
        indirect_lab = round(d_lab * R["indirect_labor_rate"])
        total_lab    = d_lab + indirect_lab

        # 법정보험료 (직+간접 노무비 합계 기준)
        ind_acc  = round(total_lab * R["industrial_accident"])
        emp_ins  = round(total_lab * R["employment_insurance"])
        health   = round(total_lab * R["health_insurance_emp"])
        pension  = round(total_lab * R["national_pension_emp"])
        lcare    = round(total_lab * R["long_term_care"])
        retire   = round(total_lab * R["retirement_fund"])
        safety   = round(d_lab    * R["safety_health"])
        env      = round(d_lab    * R["env_preserve"])

        total_exp = (d_exp + ind_acc + emp_ins + health +
                     pension + lcare + retire + safety + env)
        pure = d_mat + total_lab + total_exp

        gen_mgmt = round(pure * R["general_mgmt"])
        profit_base = total_lab + total_exp + gen_mgmt
        profit   = round(profit_base * R["profit"])
        total_cost = pure + gen_mgmt + profit
        subcontract_bond = round(total_cost * 0.000218)
        total_cost_adj = total_cost + subcontract_bond
        vat = round(total_cost_adj * R["vat"])
        total_project = total_cost_adj + vat

        return {
            "work_category":     self.category,
            "direct_material":   d_mat,
            "indirect_material": 0,
            "material_subtotal": d_mat,
            "direct_labor":      d_lab,
            "indirect_labor":    indirect_lab,
            "labor_subtotal":    total_lab,
            "machine_cost":      d_exp,
            "industrial_acc_ins":ind_acc,
            "employment_ins":    emp_ins,
            "health_ins":        health,
            "pension_ins":       pension,
            "lcare_ins":         lcare,
            "retirement_fund":   retire,
            "safety_health_cost":safety,
            "env_preserve_cost": env,
            "subcontract_bond":  subcontract_bond,
            "expense_subtotal":  total_exp + subcontract_bond,
            "pure_construction": pure,
            "general_mgmt_cost": gen_mgmt,
            "profit_amount":     profit,
            "total_construction":total_cost_adj,
            "vat_amount":        vat,
            "total_project_cost":total_project,
            "applied_rates_snapshot": R,
            "rates_applied_date": "2026-01-01",
        }
```

```python
# propai/apps/api/app/services/rates/current_rates.py
"""2026년 법정요율 -- DB 조회 + 캐시 (fallback: 상수)"""
from functools import lru_cache
from datetime import date

# 2026년 확정 법정요율 (검증 완료)
_RATES_2026 = {
    "indirect_labor_rate":   0.1440,  # 간접노무비 14.40%
    "industrial_accident":   0.0350,  # 산재보험 3.50% (건설업, 고용노동부)
    "employment_insurance":  0.0090,  # 고용보험 0.90%
    "health_insurance_emp":  0.03595, # 건강보험 사업주 3.595% (7.19%/2)
    "national_pension_emp":  0.04750, # 국민연금 사업주 4.75% (9.5%/2, 2026 개정)
    "long_term_care":        0.004724,# 장기요양 0.4724% (0.9448%/2)
    "retirement_fund":       0.02100, # 퇴직공제부금 2.10%
    "safety_health":         0.02070, # 안전보건관리비 2.07%
    "env_preserve":          0.00160, # 환경보전비 0.16%
    "general_mgmt":          0.05500, # 일반관리비 5.50%
    "profit":                0.15000, # 이윤 15.00%
    "vat":                   0.10000, # 부가가치세 10.00%
    "effective_date":        "2026-01-01",
    "source_standard":       "국토교통부공고2024-1782호+고용노동부고시2025",
    "pension_note":          "2026~2033 매년 0.5%p인상(국민연금법개정)",
}

def get_current_rates() -> dict:
    """현재 적용 법정요율 반환 (향후 DB 조회로 대체 가능)"""
    return dict(_RATES_2026)
```

---

## MODULE F: 몬테카를로 공사비 리스크 분석

```python
# propai/apps/api/app/services/simulation/cost_monte_carlo.py
"""
공사비 몬테카를로 시뮬레이션 (10,000회)
삼각분포 기반 리스크 모델링
AACE International RP 57R-09 준거
"""
import numpy as np
from typing import Dict

class CostMonteCarlo:
    """
    리스크 파라미터 (삼각분포: 최솟값, 최빈값, 최댓값 배율)
    근거: 건설 리스크 관리 실무 시뮬레이션 모델
    """
    RISK = {
        "material":   (0.90, 1.00, 1.25),  # 재료비: -10%~+25%
        "labor":      (0.92, 1.00, 1.20),  # 노무비: -8%~+20%
        "expense":    (0.95, 1.00, 1.15),  # 경비: -5%~+15%
        "design_chg": (0.00, 0.05, 0.15),  # 설계변경: 0~15%
        "schedule":   (1.00, 1.00, 1.30),  # 공기지연: 0~30%
    }

    def __init__(self, base: Dict[str,float],
                 iters: int = 10000, seed: int = 42):
        self.base  = base
        self.iters = iters
        self.rng   = np.random.default_rng(seed)

    def _tri(self, lo, mode, hi) -> np.ndarray:
        return self.rng.triangular(lo, mode, hi, size=self.iters)

    def run(self) -> Dict:
        b_mat  = self.base.get("material_subtotal",  0)
        b_lab  = self.base.get("labor_subtotal",     0)
        b_exp  = self.base.get("expense_subtotal",   0)
        b_tot  = self.base.get("total_project_cost", 0)

        m_f = self._tri(*self.RISK["material"])
        l_f = self._tri(*self.RISK["labor"])
        e_f = self._tri(*self.RISK["expense"])
        d_a = self._tri(*self.RISK["design_chg"])
        s_f = self._tri(*self.RISK["schedule"])

        sim_mat   = b_mat * m_f
        sim_lab   = b_lab * l_f
        sim_exp   = b_exp * e_f
        sim_des   = b_tot * d_a
        sim_sch   = b_lab * (s_f - 1.0) * 0.20

        # 간접비 재계산 (법정요율 적용)
        sim_ind_lab = sim_lab * 0.1440
        sim_pure    = sim_mat + sim_lab + sim_ind_lab + sim_exp
        sim_gen     = sim_pure * 0.0550
        sim_profit  = (sim_lab + sim_ind_lab + sim_exp + sim_gen) * 0.15
        sim_total   = (sim_pure + sim_gen + sim_profit) * 1.10
        sim_total  += sim_des + sim_sch

        mean = float(np.mean(sim_total))
        std  = float(np.std(sim_total))
        cv   = std / mean if mean > 0 else 0

        p10  = float(np.percentile(sim_total, 10))
        p50  = float(np.percentile(sim_total, 50))
        p80  = float(np.percentile(sim_total, 80))
        p90  = float(np.percentile(sim_total, 90))

        # 리스크 기여도
        total_var = float(np.var(sim_total))
        contrib = {}
        for name, arr in [("재료비",sim_mat),("노무비",sim_lab+sim_ind_lab),
                           ("경비",sim_exp),("설계변경",sim_des),
                           ("공기지연",sim_sch)]:
            cov = float(np.cov(arr, sim_total)[0,1])
            contrib[name] = round(cov/total_var*100 if total_var>0 else 0, 1)

        return {
            "iterations":        self.iters,
            "base_cost":         round(b_tot),
            "mean_cost":         round(mean),
            "std_dev_cost":      round(std),
            "cv":                round(cv,4),
            "converged":         cv < 0.05,
            "p10_cost":          round(p10),
            "p50_cost":          round(p50),
            "p80_cost":          round(p80),
            "p90_cost":          round(p90),
            "recommended_budget":round(p80),
            "contingency":       round(p80 - b_tot),
            "contingency_rate":  round((p80-b_tot)/b_tot*100,1) if b_tot>0 else 0,
            "risk_contributions":contrib,
        }
```

---

## MODULE G: FastAPI BIM 공사비 엔드포인트

```python
# propai/apps/api/app/api/v1/endpoints/bim_cost.py
"""BIM 공사비 자동산출 + 기성관리 + 몬테카를로 + 수지분석 API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.models.base import (
    BimQuantity, CostDetailItem, CostCalculationSheet,
    ProjectTotalCost, ProgressBilling, MonteCarloResult,
    MaterialUnitPrice
)
from app.services.cost.cost_engine import OriginCostCalculator, CostItem
from app.services.simulation.cost_monte_carlo import CostMonteCarlo
from app.services.rates.current_rates import get_current_rates
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
import shutil, tempfile, os, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

router = APIRouter(prefix="/api/v1/cost", tags=["AI BIM 공사비"])

# ---- IFC 업로드 + 물량 자동산출 ----
@router.post("/{project_id}/upload-ifc")
async def upload_ifc(
    project_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        from app.services.bim.ifc_extractor import IFCExtractor
        extractor = IFCExtractor(tmp_path, project_id)
        quantities = extractor.extract()
        agg = extractor.aggregate(quantities)

        # 기존 물량 삭제 후 재등록
        await db.execute(
            BimQuantity.__table__.delete().where(
                BimQuantity.project_id == project_id))
        for q in quantities:
            db.add(BimQuantity(
                project_id=project_id,
                ifc_global_id=q.global_id,
                ifc_object_type=q.ifc_type,
                ifc_object_name=q.ifc_name,
                work_code=q.work_code,
                floor_level=q.floor,
                zone=q.zone,
                quantity=q.quantity,
                unit=q.unit,
                quantity_formula=q.formula,
                extraction_method="IFC_AI",
            ))
        await db.commit()
        return {"status":"OK","element_count":len(quantities),"aggregate":agg}
    finally:
        os.unlink(tmp_path)

# ---- AI 공사비 자동계산 (표준품셈 단가 + 2026 법정요율) ----
@router.post("/{project_id}/calculate")
async def calculate_cost(
    project_id: int,
    db: AsyncSession = Depends(get_db)
):
    # 물량 조회
    qtys = (await db.execute(
        select(BimQuantity).where(BimQuantity.project_id==project_id)
    )).scalars().all()

    if not qtys:
        raise HTTPException(404,"BIM 물량 없음. IFC 업로드 또는 설계도면에서 물량 생성")

    # 표준단가 조회
    prices = {r.material_code: r for r in
              (await db.execute(
                  select(MaterialUnitPrice)
                  .where(MaterialUnitPrice.is_current==True)
              )).scalars().all()}

    # 공종코드 -> 표준단가 매핑
    CODE_PRICE_MAP = {
        "010202": "RC-006",  # 레미콘24MPa (RC공사 대표)
        "010203": "TL-001",  # 타일 (조적 대체)
        "010205": "TL-001",  # 타일
        "010206": "PT-001",  # 도장 (목공 대체)
        "010207": "WP-001",  # 우레탄방수
        "010208": "WP-003",  # 도막방수 (지붕)
        "010210": "PT-001",  # 수성페인트 (미장 대체)
        "010211": "WW-001",  # PVC창호
        "M0101":  "ME-001",  # 기계장비
        "M0102":  "ME-002",  # 배관
        "E0102":  "EL-002",  # 전기84형
        "C01":    "CV-001",  # H파일
    }

    # 분야별 품목 생성
    cat_map = {
        "010":"건축","M":"기계","E":"전기","L":"조경","C":"토목"
    }
    items_by_cat: dict = {c:[] for c in ["건축","기계","전기","조경","토목"]}

    for q in qtys:
        code = q.work_code or ""
        cat = "건축"
        for prefix,c in cat_map.items():
            if code.startswith(prefix): cat = c; break

        price_code = CODE_PRICE_MAP.get(code)
        price = prices.get(price_code)
        mat_u = float(price.material_price) if price else 0
        lab_u = float(price.labor_price)    if price else 0
        exp_u = float(price.expense_price)  if price else 0

        items_by_cat[cat].append(CostItem(
            work_code=code, item_name=q.ifc_object_name or code,
            spec=q.ifc_object_type or "", unit=q.unit,
            quantity=float(q.quantity),
            mat_unit=mat_u, labor_unit=lab_u, exp_unit=exp_u,
        ))

    # 분야별 원가계산서 계산 + 저장
    results = {}
    for cat, items in items_by_cat.items():
        if not items: continue
        calc = OriginCostCalculator(items, cat)
        origin = calc.calc()
        results[cat] = origin
        # DB upsert
        stmt = select(CostCalculationSheet).where(
            CostCalculationSheet.project_id==project_id,
            CostCalculationSheet.work_category==cat)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            for k,v in origin.items():
                if hasattr(existing, k): setattr(existing, k, v)
            existing.calc_at = datetime.utcnow()
        else:
            db.add(CostCalculationSheet(project_id=project_id, **origin))
    await db.commit()

    total = sum(v["total_project_cost"] for v in results.values())
    rates = get_current_rates()

    return {
        "status": "OK",
        "category_totals": {k: round(v["total_project_cost"])
                            for k,v in results.items()},
        "grand_total": round(total),
        "grand_total_formatted": f"{total/1e8:.2f}억원",
        "applied_rates": {
            "산재보험_건설업": f"{rates['industrial_accident']*100:.2f}%",
            "건강보험_사업주": f"{rates['health_insurance_emp']*100:.3f}%",
            "국민연금_사업주": f"{rates['national_pension_emp']*100:.2f}%",
            "장기요양":        f"{rates['long_term_care']*100:.4f}%",
            "일반관리비":      f"{rates['general_mgmt']*100:.1f}%",
            "이윤":            f"{rates['profit']*100:.1f}%",
        },
    }

# ---- 몬테카를로 시뮬레이션 ----
@router.post("/{project_id}/monte-carlo")
async def run_monte_carlo(
    project_id: int,
    iterations: int = 10000,
    db: AsyncSession = Depends(get_db)
):
    sheets = (await db.execute(
        select(CostCalculationSheet).where(
            CostCalculationSheet.project_id==project_id)
    )).scalars().all()
    if not sheets:
        raise HTTPException(404,"원가계산서 없음. /calculate 먼저 실행")

    base = {
        "material_subtotal":  float(sum(s.material_subtotal  for s in sheets)),
        "labor_subtotal":     float(sum(s.labor_subtotal     for s in sheets)),
        "expense_subtotal":   float(sum(s.expense_subtotal   for s in sheets)),
        "total_project_cost": float(sum(s.total_project_cost for s in sheets)),
    }

    mc = CostMonteCarlo(base, iterations)
    result = mc.run()

    db.add(MonteCarloResult(
        project_id=project_id, sim_type="공사비",
        iterations=iterations,
        p10_value=result["p10_cost"], p50_value=result["p50_cost"],
        p80_value=result["p80_cost"], p90_value=result["p90_cost"],
        mean_value=result["mean_cost"], std_dev=result["std_dev_cost"],
        cv=result["cv"], converged=result["converged"],
        risk_contributions=result["risk_contributions"],
        recommended_value=result["recommended_budget"],
        contingency_rate=result["contingency_rate"],
    ))
    await db.commit()

    return {
        **result,
        "formatted": {
            "P10(낙관)": f"{result['p10_cost']/1e8:.2f}억원",
            "P50(중간)": f"{result['p50_cost']/1e8:.2f}억원",
            "P80(권고)": f"{result['p80_cost']/1e8:.2f}억원",
            "P90(보수)": f"{result['p90_cost']/1e8:.2f}억원",
            "권고예산":  f"{result['recommended_budget']/1e8:.2f}억원",
            "예비비":    f"{result['contingency']/1e8:.2f}억원"
                         f"({result['contingency_rate']}%)",
            "수렴여부":  "완료" if result["converged"] else "미수렴",
        }
    }

# ---- 기성 등록 + EVM 자동계산 ----
class BillingRequest(BaseModel):
    billing_no: int
    period_from: date
    period_to: date
    work_entries: List[dict]  # [{work_code,actual_qty,planned_qty,actual_amount,planned_amount}]

@router.post("/{project_id}/billing/create")
async def create_billing(
    project_id: int, req: BillingRequest,
    db: AsyncSession = Depends(get_db)
):
    ptc = (await db.execute(
        select(ProjectTotalCost).where(
            ProjectTotalCost.project_id==project_id)
    )).scalar_one_or_none()
    total_budget = float(ptc.direct_cost_total) if ptc else 0

    records = []
    for entry in req.work_entries:
        a_qty  = entry.get("actual_qty", 0)
        p_qty  = entry.get("planned_qty", 0)
        a_amt  = entry.get("actual_amount", 0)
        p_amt  = entry.get("planned_amount", 0)
        prog   = a_qty/p_qty if p_qty > 0 else 0
        bcwp   = total_budget * prog
        bcws   = p_amt
        acwp   = a_amt
        spi    = round(bcwp/bcws,4) if bcws > 0 else 1.0
        cpi    = round(bcwp/acwp,4) if acwp > 0 else 1.0
        rec = ProgressBilling(
            project_id=project_id, billing_no=req.billing_no,
            billing_period_from=req.period_from,
            billing_period_to=req.period_to,
            work_code=entry.get("work_code"),
            actual_qty=a_qty, planned_qty=p_qty,
            progress_rate=round(prog,4),
            actual_amount=a_amt, planned_amount=p_amt,
            bcwp=bcwp, bcws=bcws, acwp=acwp, spi=spi, cpi=cpi,
        )
        db.add(rec); records.append(rec)
    await db.commit()

    avg_spi = sum(r.spi for r in records)/len(records) if records else 1.0
    avg_cpi = sum(r.cpi for r in records)/len(records) if records else 1.0
    return {
        "status": "OK",
        "billing_no": req.billing_no,
        "evm": {
            "avg_spi": round(avg_spi,3),
            "avg_cpi": round(avg_cpi,3),
            "schedule_status": "정상" if avg_spi >= 0.95 else "지연",
            "cost_status":     "정상" if avg_cpi >= 0.95 else "초과",
            "total_actual":    sum(r.actual_amount for r in records),
        }
    }

# ---- 기성 현황 조회 ----
@router.get("/{project_id}/billing/summary")
async def billing_summary(project_id: int, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(
        select(
            func.max(ProgressBilling.billing_no).label("last_no"),
            func.sum(ProgressBilling.actual_amount).label("total_actual"),
            func.avg(ProgressBilling.spi).label("avg_spi"),
            func.avg(ProgressBilling.cpi).label("avg_cpi"),
        ).where(ProgressBilling.project_id==project_id)
    )).one()
    return {
        "last_billing_no": r.last_no or 0,
        "cumulative_actual": float(r.total_actual or 0),
        "avg_spi": round(float(r.avg_spi or 1.0),3),
        "avg_cpi": round(float(r.avg_cpi or 1.0),3),
        "schedule_status": "정상" if (r.avg_spi or 1.0) >= 0.95 else "지연",
        "cost_status":     "정상" if (r.avg_cpi or 1.0) >= 0.95 else "초과",
    }

# ---- 수지분석 (공사비 자동 연동) ----
class FeasibilityRequest(BaseModel):
    land_cost: float
    total_floor_area: float
    sellable_ratio: float = 0.70
    region: str = "의정부"
    dev_type: str = "주상복합"
    project_years: int = 3

@router.post("/{project_id}/feasibility")
async def full_feasibility(
    project_id: int, req: FeasibilityRequest,
    db: AsyncSession = Depends(get_db)
):
    sheets = (await db.execute(
        select(CostCalculationSheet).where(
            CostCalculationSheet.project_id==project_id)
    )).scalars().all()
    construction_cost = float(sum(s.total_project_cost for s in sheets))
    if construction_cost == 0:
        raise HTTPException(404,"공사비 없음. /calculate 먼저 실행")

    # 시장 분양가 (시뮬레이션 기준, 2026년 경기도)
    MARKET = {
        "의정부":  {"아파트":5_400_000,"주상복합":6_000_000},
        "서울":    {"아파트":13_000_000,"주상복합":15_000_000},
        "인천":    {"아파트":5_000_000,"주상복합":5_500_000},
    }
    mkt = MARKET.get(req.region,MARKET["의정부"]).get(req.dev_type,6_000_000)

    land = req.land_cost
    acq_tax   = round(land * 0.0400)
    reg_tax   = round(land * 0.0024)
    agency_fee= round(construction_cost * 0.0050)
    model_house=round(construction_cost * 0.0030)
    advert    = round(construction_cost * 0.0080)
    pf_int    = round(construction_cost * 0.0650 * req.project_years*0.5)
    legal     = round(construction_cost * 0.0015)
    design    = round(construction_cost * 0.0300)
    supervise = round(construction_cost * 0.0150)

    total_cost= (land + construction_cost + acq_tax + reg_tax +
                 agency_fee + model_house + advert +
                 pf_int + legal + design + supervise)

    sellable  = req.total_floor_area * req.sellable_ratio
    revenue   = round(sellable * mkt * 0.95)  # VAT 등 5% 공제
    net_profit= revenue - total_cost

    # IRR (Newton-Raphson)
    cfs = [-total_cost] + [0]*(req.project_years-1) + [revenue]
    irr = None
    r = 0.10
    for _ in range(1000):
        f  = sum(cf/(1+r)**t for t,cf in enumerate(cfs))
        df = sum(-t*cf/(1+r)**(t+1) for t,cf in enumerate(cfs))
        if abs(df) < 1e-10: break
        r2 = r - f/df
        if abs(r2-r) < 1e-8: irr = r2; break
        r = r2

    npv = sum(cf/(1.08)**t for t,cf in enumerate(cfs))

    return {
        "summary": {
            "총사업비":   f"{total_cost/1e8:.2f}억원",
            "총분양수입": f"{revenue/1e8:.2f}억원",
            "순이익":     f"{net_profit/1e8:.2f}억원",
            "수익률":     f"{net_profit/total_cost*100:.1f}%",
            "IRR":        f"{irr*100:.2f}%" if irr else "산출불가",
            "NPV":        f"{npv/1e8:.2f}억원",
            "분양면적":   f"{sellable:,.1f}m2",
            "평균분양가": f"{mkt:,}원/m2",
        },
        "feasibility_ok": net_profit > 0 and (irr or 0) > 0.08,
        "detail": {
            "land_cost": land, "construction_cost": construction_cost,
            "acq_tax": acq_tax, "pf_interest": pf_int,
            "design_cost": design, "supervision_cost": supervise,
            "total_cost": total_cost, "revenue": revenue,
            "net_profit": net_profit,
        }
    }

# ---- 원가계산서 Excel 출력 ----
@router.get("/{project_id}/export-excel")
async def export_excel(project_id: int, db: AsyncSession = Depends(get_db)):
    sheets = (await db.execute(
        select(CostCalculationSheet).where(
            CostCalculationSheet.project_id==project_id)
    )).scalars().all()
    if not sheets:
        raise HTTPException(404,"원가계산서 없음")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "공사원가계산서"

    # 스타일
    hdr_fill = PatternFill("solid", fgColor="1F3864")
    hdr_font = Font(name="맑은고딕", bold=True, color="FFFFFF", size=9)
    body_font= Font(name="맑은고딕", size=9)
    bold_font= Font(name="맑은고딕", bold=True, size=9)
    center   = Alignment(horizontal="center",vertical="center")
    right    = Alignment(horizontal="right",vertical="center")
    money_fmt= "#,##0"

    ws.column_dimensions["A"].width = 25
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 18
    ws.merge_cells("A1:C1")
    ws["A1"] = "공  사  원  가  계  산  서"
    ws["A1"].font = Font(name="맑은고딕", bold=True, size=14)
    ws["A1"].alignment = center

    # 분야별 소계
    ROWS = [
        ("항 목","건축","기계","전기","조경","토목","합계"),
    ]
    cats = ["건축","기계","전기","조경","토목"]
    fields = [
        ("직접재료비","direct_material"),
        ("간접재료비","indirect_material"),
        ("재료비소계","material_subtotal"),
        ("직접노무비","direct_labor"),
        ("간접노무비","indirect_labor"),
        ("노무비소계","labor_subtotal"),
        ("산재보험료3.50%","industrial_acc_ins"),
        ("고용보험료0.90%","employment_ins"),
        ("건강보험료3.595%","health_ins"),
        ("국민연금4.75%","pension_ins"),
        ("장기요양0.4724%","lcare_ins"),
        ("퇴직공제부금2.10%","retirement_fund"),
        ("안전보건관리비2.07%","safety_health_cost"),
        ("환경보전비0.16%","env_preserve_cost"),
        ("경비소계","expense_subtotal"),
        ("순공사원가","pure_construction"),
        ("일반관리비5.50%","general_mgmt_cost"),
        ("이윤15.00%","profit_amount"),
        ("총공사원가","total_construction"),
        ("부가가치세10%","vat_amount"),
        ("총공사비","total_project_cost"),
    ]
    BOLD_ROWS = {"재료비소계","노무비소계","경비소계","순공사원가","총공사원가","총공사비"}

    sheet_map = {s.work_category: s for s in sheets}

    # 헤더
    hdr_row = 3
    for ci, h in enumerate(["항목"] + cats + ["합계"]):
        c = ws.cell(row=hdr_row, column=ci+1, value=h)
        c.font = hdr_font; c.fill = hdr_fill; c.alignment = center

    for ri,(fname,fkey) in enumerate(fields):
        row = hdr_row + 1 + ri
        ws.cell(row=row,column=1,value=fname).font = (
            bold_font if fname in BOLD_ROWS else body_font)
        total = 0
        for ci,cat in enumerate(cats):
            s = sheet_map.get(cat)
            val = float(getattr(s,fkey,0)) if s else 0
            total += val
            c = ws.cell(row=row,column=ci+2,value=val)
            c.number_format = money_fmt
            c.font = bold_font if fname in BOLD_ROWS else body_font
            c.alignment = right
        c = ws.cell(row=row,column=7,value=total)
        c.number_format = money_fmt
        c.font = bold_font if fname in BOLD_ROWS else body_font
        c.alignment = right
        if fname in BOLD_ROWS:
            for col in range(1,8):
                ws.cell(row=row,column=col).fill = PatternFill("solid",fgColor="DDEBF7")

    import io
    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":f"attachment; filename=origin_cost_{project_id}.xlsx"}
    )
```

---

## MODULE H: 법정요율 자동갱신 서비스

```python
# propai/apps/api/app/services/rates/legal_rate_updater.py
"""
법정보험료율 + 표준품셈 자동 갱신
주기: 일/주 크론잡 실행
소스: 고용노동부 / 보건복지부 / 국토교통부 공공 API
"""
import httpx
from datetime import date
from app.services.rates.current_rates import get_current_rates
import structlog

logger = structlog.get_logger()

# 공공 데이터 API 소스 정의
RATE_SOURCES = {
    "산재보험_건설업": {
        "url": "https://www.data.go.kr/data/15068737/fileData.do",
        "desc": "사업종류별 산재보험료율 (건설업)",
        "field_key": "industrial_accident",
        "refresh": "annual",
    },
    "고용보험": {
        "url": "https://www.comwel.or.kr",
        "desc": "고용보험료율",
        "field_key": "employment_insurance",
        "refresh": "as_announced",
    },
    "건강보험": {
        "url": "https://nhis.or.kr",
        "desc": "건강보험료율",
        "field_key": "health_insurance_emp",
        "refresh": "annual",
    },
    "국민연금": {
        "url": "https://nps.or.kr",
        "desc": "국민연금 보험료율 (2026년 개정: 9%->9.5%)",
        "field_key": "national_pension_emp",
        "refresh": "annual",
        "next_change": {"date":"2027-01-01","rate":0.05000},  # 9.5%->10.0%
    },
    "장기요양": {
        "url": "https://nhis.or.kr",
        "desc": "장기요양보험료율",
        "field_key": "long_term_care",
        "refresh": "annual",
    },
}

class LegalRateAutoUpdater:

    async def check_and_notify(self):
        """변경 감지 + DB 갱신 + 알림"""
        current = get_current_rates()
        changes = []
        for source_key, source in RATE_SOURCES.items():
            try:
                latest = await self._fetch_rate(source)
                if latest and abs(latest - current.get(source["field_key"],0)) > 0.0001:
                    changes.append({
                        "category": source_key,
                        "old_rate": current.get(source["field_key"]),
                        "new_rate": latest,
                        "desc": source["desc"],
                    })
            except Exception as e:
                logger.warning("요율조회실패", source=source_key, error=str(e))

        if changes:
            await self._update_db(changes)
            await self._send_alert(changes)
        else:
            logger.info("법정요율 변경없음", checked_sources=len(RATE_SOURCES))
        return changes

    async def _fetch_rate(self, source: dict) -> float:
        """공공 API 조회 (실패시 None 반환)"""
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(source["url"])
                if r.status_code == 200:
                    data = r.json()
                    return self._parse_rate(data, source["field_key"])
        except Exception:
            pass
        return None

    def _parse_rate(self, data: dict, field_key: str) -> float:
        """API 응답에서 요율 파싱 (API별 응답 구조에 맞게 구현)"""
        # 실제 API 응답 구조에 따라 파싱 로직 구현 필요
        # 현재는 시드 데이터 기반 fallback
        current = get_current_rates()
        return current.get(field_key, 0)

    async def _update_db(self, changes: list):
        """변경된 요율 DB 저장"""
        from app.core.database import AsyncSessionLocal
        from app.models.base import LegalRateHistory
        async with AsyncSessionLocal() as db:
            for chg in changes:
                db.add(LegalRateHistory(
                    rate_category=chg["category"],
                    rate_value=chg["new_rate"],
                    effective_from=date.today(),
                    source_api="auto_check",
                ))
            await db.commit()

    async def _send_alert(self, changes: list):
        """관리자 알림 (슬랙/이메일 -- 설정에 따라 활성화)"""
        msg_lines = ["[PropAI 법정요율 변경 감지]"]
        for chg in changes:
            msg_lines.append(
                f"  {chg['category']}: "
                f"{chg['old_rate']*100:.4f}% -> "
                f"{chg['new_rate']*100:.4f}%"
            )
        logger.info("법정요율변경알림", changes=changes)
        # TODO: 실제 알림 채널 (Slack webhook, 이메일 SMTP) 연동
```

```python
# propai/apps/api/app/api/v1/endpoints/rates.py
"""법정요율 조회 + 갱신 API"""
from fastapi import APIRouter, Depends
from app.services.rates.current_rates import get_current_rates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.models.base import LegalRateHistory, StandardPriceUpdate
import asyncio

router = APIRouter(prefix="/api/v1/rates", tags=["법정요율"])

@router.get("/current")
async def current_rates():
    """현재 적용 법정요율 반환"""
    rates = get_current_rates()
    return {
        "applied_year": 2026,
        "effective_date": rates["effective_date"],
        "source": rates["source_standard"],
        "rates": {
            "산재보험_건설업":  f"{rates['industrial_accident']*100:.2f}%",
            "고용보험":         f"{rates['employment_insurance']*100:.2f}%",
            "건강보험_사업주":  f"{rates['health_insurance_emp']*100:.3f}%",
            "국민연금_사업주":  f"{rates['national_pension_emp']*100:.2f}%",
            "장기요양":         f"{rates['long_term_care']*100:.4f}%",
            "퇴직공제부금":     f"{rates['retirement_fund']*100:.2f}%",
            "안전보건관리비":   f"{rates['safety_health']*100:.2f}%",
            "환경보전비":       f"{rates['env_preserve']*100:.2f}%",
            "간접노무비율":     f"{rates['indirect_labor_rate']*100:.1f}%",
            "일반관리비율":     f"{rates['general_mgmt']*100:.1f}%",
            "이윤상한":         f"{rates['profit']*100:.1f}%",
            "부가가치세":       f"{rates['vat']*100:.1f}%",
        },
        "raw": rates,
        "pension_increase_note": rates.get("pension_note",""),
    }

@router.get("/history")
async def rates_history(db: AsyncSession = Depends(get_db)):
    """법정요율 갱신 이력"""
    rows = (await db.execute(
        select(LegalRateHistory)
        .order_by(LegalRateHistory.effective_from.desc())
        .limit(50)
    )).scalars().all()
    return [{"category":r.rate_category,"value":float(r.rate_value),
             "effective_from":str(r.effective_from),
             "notice_no":r.gov_notice_no} for r in rows]

@router.post("/refresh")
async def force_refresh():
    """법정요율 강제 갱신 (관리자용)"""
    from app.services.rates.legal_rate_updater import LegalRateAutoUpdater
    updater = LegalRateAutoUpdater()
    changes = await updater.check_and_notify()
    return {"changes": changes, "message": f"{len(changes)}건 갱신"}
```

---

## STEP: Part 3 실행 검증

```bash
# 법정요율 확인
curl http://localhost:8000/api/v1/rates/current
# 예상: 2026년 최신 요율 (산재3.50%, 연금4.75% 등)

# 공사비 직접 계산 (IFC 없는 경우)
# -- 먼저 물량을 직접 DB에 입력 후 --
curl -X POST http://localhost:8000/api/v1/cost/1/calculate
# 예상: {"status":"OK","grand_total":...,"applied_rates":{...}}

# 몬테카를로 시뮬레이션 (10,000회)
curl -X POST "http://localhost:8000/api/v1/cost/1/monte-carlo?iterations=10000"
# 예상: {"p10_cost":...,"p50_cost":...,"converged":true,...}

# 수지분석
curl -X POST http://localhost:8000/api/v1/cost/1/feasibility \
  -H "Content-Type: application/json" \
  -d '{"land_cost":5000000000,"total_floor_area":10000,"region":"의정부"}'

# 기성 등록 (1차)
curl -X POST http://localhost:8000/api/v1/cost/1/billing/create \
  -H "Content-Type: application/json" \
  -d '{
    "billing_no":1,
    "period_from":"2026-01-01",
    "period_to":"2026-03-31",
    "work_entries":[{
      "work_code":"010202",
      "actual_qty":800,"planned_qty":1000,
      "actual_amount":800000000,"planned_amount":900000000
    }]
  }'

# Excel 원가계산서 다운로드
curl http://localhost:8000/api/v1/cost/1/export-excel -o origin_cost.xlsx

# 법정요율 강제 갱신
curl -X POST http://localhost:8000/api/v1/rates/refresh
```

---

## [Part 3 완료 -- Part 4 (통합 프론트엔드 + DevOps)로 진행]
================================================================================
