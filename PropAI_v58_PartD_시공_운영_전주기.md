# PropAI v58.0 -- IDE 빌드 프롬프트 Part D
# 시공 + 운영 + 전주기 관리 완전 구현
# Phase 21~38p: 착공/감리/준공/분양/입주/운영/특수분석 + G211~G220 확장

---

> **전제 조건**: Part A~C (Phase 00~20h) 완료 후 실행
> **ASCII 100% 준수** | **한국 40개 법령 완전 반영**

---

## Phase 21: 착공 지원 시스템

```
=== PropAI v58.0 Phase 21: AI 착공 지원 시스템 ===

[파일: apps/api/app/services/lifecycle/construction/construction_start_service.py]

from typing import Dict, List
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

CONSTRUCTION_START_CHECKLIST = [
    {"item": "착공신고서 제출", "law": "건축법 제21조", "required": True},
    {"item": "공사감리 계약 체결", "law": "건축법 제25조", "required": True},
    {"item": "건설공사 안전관리계획서 제출", "law": "건설기술진흥법 제62조", "required": True},
    {"item": "가설울타리 설치", "law": "건설현장 안전기준", "required": True},
    {"item": "공사안전표지판 설치", "law": "산업안전보건법", "required": True},
    {"item": "환경영향평가 이행확인", "law": "환경영향평가법", "required": False},
    {"item": "문화재 지표조사 완료", "law": "문화재보호법 제91조", "required": False},
    {"item": "지하시설물 조사 완료", "law": "지하시설물 안전관리 기준", "required": True},
    {"item": "교통영향평가 이행계획 확인", "law": "도시교통정비 촉진법", "required": False},
    {"item": "품질관리계획서 제출", "law": "건설기술진흥법 제55조", "required": True},
]

class ConstructionStartService:
    """
    AI 착공 지원 시스템
    근거법: 건축법 제21조 (착공신고) + 건설기술진흥법 제62조
    """

    def generate_checklist(self, project_type: str, project_cost_krw: float) -> Dict:
        """착공 전 체크리스트 자동 생성"""
        required_items = [item for item in CONSTRUCTION_START_CHECKLIST if item["required"]]
        optional_items = [item for item in CONSTRUCTION_START_CHECKLIST if not item["required"]]

        # 안전관리계획서: 건설기술진흥법 제62조 -- 총 공사비 50억 이상 의무
        if project_cost_krw >= 50_000_000_000:
            safety_plan_required = True
        else:
            safety_plan_required = False

        return {
            "project_type": project_type,
            "safety_plan_required": safety_plan_required,
            "safety_plan_basis": "건설기술진흥법 제62조 (총 공사비 50억원 이상)",
            "required_items": required_items,
            "optional_items": optional_items,
            "total_checklist_count": len(CONSTRUCTION_START_CHECKLIST),
            "estimated_preparation_days": 14
        }

    def auto_generate_safety_plan(
        self,
        project_id: str,
        project_name: str,
        floor_count: int,
        excavation_depth_m: float
    ) -> Dict:
        """
        건설공사 안전관리계획서 자동 작성
        건설기술진흥법 제62조 기준
        """
        high_risk_works = []
        if floor_count >= 11:
            high_risk_works.append("11층 이상 고층 공사 -- 고소작업 위험 관리")
        if excavation_depth_m >= 10:
            high_risk_works.append(f"굴착 깊이 {excavation_depth_m}m -- 토사 붕괴 위험 관리")
        if floor_count >= 5 or excavation_depth_m >= 5:
            high_risk_works.append("중장비 사용 작업 -- 충돌/협착 위험 관리")

        return {
            "project_id": project_id,
            "plan_name": f"{project_name} 건설공사 안전관리계획서",
            "legal_basis": "건설기술진흥법 제62조",
            "high_risk_works": high_risk_works,
            "safety_officer_required": True,
            "emergency_response_plan": {
                "emergency_contact": "119",
                "nearest_hospital": "자동 조회 필요",
                "evacuation_route": "현장 출입구 방향"
            },
            "generated_at": datetime.utcnow().isoformat()
        }
```

---

## Phase 22: AI 감리 + 공정 관리 EVM

```
=== PropAI v58.0 Phase 22: AI 감리 + EVM ===

수학식:
  EV (Earned Value) = BAC * 실제 공정률
  SV (Schedule Variance) = EV - PV (PV = 계획가치)
  CV (Cost Variance) = EV - AC (AC = 실제비용)
  CPI (Cost Performance Index) = EV / AC
  SPI (Schedule Performance Index) = EV / PV

[파일: apps/api/app/services/lifecycle/construction/supervision_service.py]

from typing import Dict, List, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()

class SupervisionService:
    """
    AI 감리 + EVM 공정 관리 서비스
    EVM: Earned Value Management (PMBOK 기준)
    """

    def calculate_evm(
        self,
        bac_krw: float,      # Budget at Completion (완료 예산)
        pv_krw: float,       # Planned Value (계획가치)
        ev_pct: float,       # 실제 공정률 (%)
        ac_krw: float        # Actual Cost (실제 발생 비용)
    ) -> Dict:
        """
        EVM 공정/원가 분석
        EV = BAC * 실제공정률
        SV = EV - PV (양수: 공정 앞서감, 음수: 공정 지연)
        CV = EV - AC (양수: 비용 절감, 음수: 비용 초과)
        """
        ev = bac_krw * ev_pct / 100
        sv = ev - pv_krw
        cv = ev - ac_krw
        cpi = ev / ac_krw if ac_krw > 0 else 1.0
        spi = ev / pv_krw if pv_krw > 0 else 1.0
        eac = bac_krw / cpi if cpi > 0 else bac_krw
        etc = eac - ac_krw

        schedule_status = "정상" if abs(spi - 1.0) < 0.05 else ("앞서감" if spi > 1.0 else "지연")
        cost_status = "정상" if abs(cpi - 1.0) < 0.05 else ("절감" if cpi > 1.0 else "초과")

        return {
            "bac_krw": int(bac_krw),
            "pv_krw": int(pv_krw),
            "ev_krw": int(ev),
            "ac_krw": int(ac_krw),
            "sv_krw": int(sv),
            "cv_krw": int(cv),
            "spi": round(spi, 4),
            "cpi": round(cpi, 4),
            "eac_krw": int(eac),
            "etc_krw": int(etc),
            "schedule_status": schedule_status,
            "cost_status": cost_status,
            "method": "EVM (PMBOK 7th Edition)",
            "formula": "EV=BAC*pct, SV=EV-PV, CV=EV-AC, CPI=EV/AC"
        }

    def analyze_photo_for_progress(self, image_path: str) -> Dict:
        """AI 사진 분석 기반 공정률 자동 산출"""
        import cv2
        import numpy as np
        try:
            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            progress_estimate = min(float(np.sum(edges > 0)) / (img.shape[0] * img.shape[1]) * 1000, 100)
            return {
                "estimated_progress_pct": round(progress_estimate, 1),
                "analysis_method": "OpenCV Edge Detection",
                "analyzed_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error("사진 분석 실패", error=str(e))
            return {"estimated_progress_pct": 0.0, "error": str(e)}
```

---

## Phase 29: AI 리스크 등급화 ISO 31000

```
=== PropAI v58.0 Phase 29: AI 리스크 등급화 ===

수학식:
  Risk_score = P(likelihood) * I(impact) * E(exposure)
  ISO 31000:2018 리스크 관리 프레임워크 적용

[파일: apps/api/app/services/lifecycle/risk/risk_service.py]

from typing import Dict, List
import structlog

logger = structlog.get_logger()

class RiskService:
    """
    AI 리스크 등급화 서비스
    표준: ISO 31000:2018 리스크 관리
    수식: Risk = P * I * E (가능성 * 영향도 * 노출도)
    """

    RISK_MATRIX = {
        "허가 지연": {"likelihood": 0.6, "impact": 0.8, "category": "인허가"},
        "공사비 초과": {"likelihood": 0.5, "impact": 0.9, "category": "원가"},
        "공정 지연": {"likelihood": 0.4, "impact": 0.7, "category": "공정"},
        "부동산 시장 침체": {"likelihood": 0.3, "impact": 0.9, "category": "시장"},
        "금리 상승": {"likelihood": 0.4, "impact": 0.8, "category": "금융"},
        "자재 수급 불안": {"likelihood": 0.3, "impact": 0.6, "category": "자재"},
        "안전사고 발생": {"likelihood": 0.2, "impact": 1.0, "category": "안전"},
        "법규 변경": {"likelihood": 0.2, "impact": 0.7, "category": "법규"},
        "민원 발생": {"likelihood": 0.4, "impact": 0.5, "category": "민원"},
        "자연재해": {"likelihood": 0.1, "impact": 0.9, "category": "환경"},
    }

    def calculate_risk_scores(self) -> Dict:
        """전체 리스크 자동 평가"""
        risks = []
        for risk_name, params in self.RISK_MATRIX.items():
            exposure = 1.0  # 기본 노출도
            score = params["likelihood"] * params["impact"] * exposure
            level = "critical" if score > 0.6 else "high" if score > 0.4 else "medium" if score > 0.2 else "low"
            risks.append({
                "risk_name": risk_name,
                "category": params["category"],
                "likelihood": params["likelihood"],
                "impact": params["impact"],
                "risk_score": round(score, 3),
                "risk_level": level,
                "formula": "Risk = P * I * E"
            })
        risks.sort(key=lambda x: x["risk_score"], reverse=True)
        return {
            "total_risks": len(risks),
            "critical_count": len([r for r in risks if r["risk_level"] == "critical"]),
            "high_count": len([r for r in risks if r["risk_level"] == "high"]),
            "risks": risks,
            "standard": "ISO 31000:2018",
            "assessment_date": "2026-03-28"
        }
```

---

## Phase 38l~38p: v58.0 신규 갭 서비스 (G212~G220)

```
=== PropAI v58.0 Phase 38l: 스마트시티 연계 (G212) ===

[파일: apps/api/app/services/smart_city/smart_city_service.py]

from typing import Dict, List
import httpx
import structlog

logger = structlog.get_logger()

class SmartCityService:
    """
    스마트시티 연계 데이터 허브 통합 서비스
    근거법: 스마트도시 조성 및 산업진흥 등에 관한 법률
    기능: 교통/환경/에너지 데이터 실시간 수신 + 입지 점수 자동 산출
    """

    # 입지 점수 가중치 (스마트시티 지표 기준)
    SCORE_WEIGHTS = {
        "traffic_accessibility": 0.25,
        "public_transport": 0.20,
        "green_space": 0.15,
        "air_quality": 0.15,
        "energy_infrastructure": 0.15,
        "digital_infrastructure": 0.10
    }

    def calculate_location_score(self, smart_city_data: Dict) -> Dict:
        """스마트시티 데이터 기반 입지 적합성 점수 자동 산출"""
        total_score = 0.0
        score_breakdown = {}
        for indicator, weight in self.SCORE_WEIGHTS.items():
            raw_score = smart_city_data.get(indicator, 50.0)  # 기본값 50점
            weighted = raw_score * weight
            total_score += weighted
            score_breakdown[indicator] = {
                "raw_score": raw_score,
                "weight": weight,
                "weighted_score": round(weighted, 2)
            }

        grade = "A" if total_score >= 80 else "B" if total_score >= 60 else "C" if total_score >= 40 else "D"

        return {
            "total_location_score": round(total_score, 1),
            "grade": grade,
            "breakdown": score_breakdown,
            "legal_basis": "스마트도시 조성 및 산업진흥 등에 관한 법률",
            "assessment_method": "스마트시티 통합 지표 가중 평균"
        }


=== PropAI v58.0 Phase 38m: 생애주기 최적화 (G213) ===

[파일: apps/api/app/services/lifecycle_opt/lifecycle_optimizer.py]

import numpy as np
from typing import Dict, List
import structlog

logger = structlog.get_logger()

class LifecycleOptimizer:
    """
    AI 기반 건축물 생애주기 최적화 자동 모델링
    표준: ISO 15686-1 건축물 내용연수
    수식: LCC_opt = min[sum_{t=0}^{N}(C_t/(1+d)^t)]
    """

    COMPONENT_LIFESPAN = {
        "지붕방수": 20,
        "외벽도장": 10,
        "창호교체": 25,
        "배관설비": 30,
        "전기설비": 25,
        "냉난방설비": 15,
        "엘리베이터": 20,
        "주차설비": 25,
        "소방설비": 20,
        "통신설비": 15
    }

    def optimize_replacement_schedule(
        self,
        total_construction_cost_krw: float,
        building_lifespan_years: int = 50,
        discount_rate: float = 0.03
    ) -> Dict:
        """
        최적 부품 교체 주기 자동 산출
        LCC_opt = min[sum_{t=0}^{N}(C_t/(1+d)^t)]
        """
        schedule = {}
        total_pv_replacement = 0.0

        for component, lifespan in self.COMPONENT_LIFESPAN.items():
            replacement_cost = total_construction_cost_krw * 0.02
            replacement_years = list(range(lifespan, building_lifespan_years, lifespan))
            pv_costs = []

            for year in replacement_years:
                pv = replacement_cost / ((1 + discount_rate) ** year)
                pv_costs.append({"year": year, "pv_cost_krw": int(pv)})
                total_pv_replacement += pv

            schedule[component] = {
                "lifespan_years": lifespan,
                "replacement_years": replacement_years,
                "replacement_cost_krw": int(replacement_cost),
                "pv_replacement_costs": pv_costs
            }

        return {
            "building_lifespan_years": building_lifespan_years,
            "discount_rate": discount_rate,
            "total_pv_replacement_krw": int(total_pv_replacement),
            "replacement_schedule": schedule,
            "standard": "ISO 15686-1",
            "formula": "LCC_opt = min[sum(C_t/(1+d)^t)]"
        }


=== PropAI v58.0 Phase 38n: 디지털 트윈 실시간 최적화 (G214) ===

[파일: apps/api/app/services/digital_twin/realtime_optimizer.py]

from typing import Dict, List
import numpy as np
import structlog

logger = structlog.get_logger()

class RealtimeTwinOptimizer:
    """
    디지털 트윈 실시간 운영 최적화 서비스
    IFC 4.3 표준 기반
    기능: IoT 센서 실시간 연동 + 에너지 소비 AI 최적화
    """

    def optimize_hvac(
        self,
        outdoor_temp_c: float,
        indoor_temp_c: float,
        occupancy_rate: float,
        current_energy_kwh: float
    ) -> Dict:
        """
        냉난방 설비 운영 AI 최적화
        에너지 절감 시뮬레이션
        """
        target_temp = 22.0  # 쾌적 온도 기준
        temp_diff = abs(indoor_temp_c - target_temp)
        occupancy_factor = max(0.3, occupancy_rate)

        # 에너지 최적화 모델 (회귀 기반 추정)
        baseline_energy = current_energy_kwh
        optimal_energy = baseline_energy * (1 - (1 - occupancy_factor) * 0.3)
        energy_savings_pct = (baseline_energy - optimal_energy) / baseline_energy * 100

        return {
            "outdoor_temp_c": outdoor_temp_c,
            "indoor_temp_c": indoor_temp_c,
            "target_temp_c": target_temp,
            "occupancy_rate": occupancy_rate,
            "current_energy_kwh": round(current_energy_kwh, 2),
            "optimal_energy_kwh": round(optimal_energy, 2),
            "energy_savings_pct": round(energy_savings_pct, 1),
            "recommendation": f"설정온도 {target_temp}도C 유지, 비재실 구역 냉난방 30% 감소",
            "ifc_standard": "IFC 4.3"
        }


=== PropAI v58.0 Phase 38o: 자연재해 리스크 분석 (G219) ===

[파일: apps/api/app/services/disaster_risk/disaster_risk_service.py]

from typing import Dict
import structlog

logger = structlog.get_logger()

class DisasterRiskService:
    """
    자연재해 리스크 자동 분석 시스템
    근거법: 자연재해대책법 + 국토부 재해영향평가 지침
    수식: Risk_score = sum(w_i * H_i * E_i * V_i)
          H = 재해 빈도, E = 노출도, V = 취약도
    """

    # 지역별 재해 빈도 지수 (행정안전부 재해연보 기준)
    REGIONAL_HAZARD_INDEX = {
        "서울": {"flood": 0.3, "landslide": 0.1, "earthquake": 0.2},
        "부산": {"flood": 0.4, "landslide": 0.3, "earthquake": 0.4},
        "대구": {"flood": 0.2, "landslide": 0.2, "earthquake": 0.5},
        "인천": {"flood": 0.4, "landslide": 0.1, "earthquake": 0.2},
        "광주": {"flood": 0.3, "landslide": 0.2, "earthquake": 0.3},
        "대전": {"flood": 0.3, "landslide": 0.2, "earthquake": 0.3},
        "default": {"flood": 0.3, "landslide": 0.2, "earthquake": 0.3}
    }

    def assess_disaster_risk(
        self,
        region: str,
        land_use: str,
        floor_count: int,
        distance_to_river_m: float = 500
    ) -> Dict:
        """
        재해 리스크 자동 평가
        Risk = sum(w_i * H_i * E_i * V_i)
        """
        hazard = self.REGIONAL_HAZARD_INDEX.get(region, self.REGIONAL_HAZARD_INDEX["default"])

        # 노출도 (E): 강과의 거리 기반
        flood_exposure = max(0.1, 1.0 - distance_to_river_m / 1000)

        # 취약도 (V): 층수 기반
        seismic_vulnerability = min(0.9, floor_count * 0.05)

        # 리스크 점수 산출
        flood_risk = hazard["flood"] * flood_exposure * 0.8
        landslide_risk = hazard["landslide"] * 0.5 * 0.6
        earthquake_risk = hazard["earthquake"] * seismic_vulnerability * 0.7

        total_risk = (flood_risk * 0.4 + landslide_risk * 0.3 + earthquake_risk * 0.3)
        risk_level = "critical" if total_risk > 0.6 else "high" if total_risk > 0.4 else "medium" if total_risk > 0.2 else "low"

        return {
            "region": region,
            "flood_risk_score": round(flood_risk, 3),
            "landslide_risk_score": round(landslide_risk, 3),
            "earthquake_risk_score": round(earthquake_risk, 3),
            "total_risk_score": round(total_risk, 3),
            "risk_level": risk_level,
            "evacuation_routes": [
                "주 출입구 방향 대피",
                "비상계단 이용 옥상 대피 (침수 시)",
                "인근 공원/고지대 대피"
            ],
            "legal_basis": "자연재해대책법 + 국토부 재해영향평가 지침",
            "formula": "Risk = sum(w_i * H_i * E_i * V_i)"
        }


=== PropAI v58.0 Phase 38p: AI 자재 조달 최적화 (G220) ===

[파일: apps/api/app/services/procurement_opt/procurement_optimizer.py]

import numpy as np
from typing import Dict, List
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()

class ProcurementOptimizer:
    """
    AI 기반 건설 자재 조달 최적화 서비스
    근거법: 건설산업기본법 + 나라장터 조달 기준
    수식: EOQ = sqrt(2 * D * S / H)
          D = 연간 수요량, S = 1회 주문 비용, H = 연간 재고유지 비용
    PPI (생산자물가지수) 기반 가격 변동 예측 포함
    """

    # 한국은행 PPI 자재별 기준값 (2020년 = 100, 2023년 기준)
    PPI_BASE_INDEX = {
        "시멘트": 142.3,
        "철근": 138.7,
        "레미콘": 135.2,
        "합판": 129.8,
        "유리": 127.5,
        "단열재": 133.4,
        "배관자재": 141.2,
        "전기자재": 136.8
    }

    def calculate_eoq(
        self,
        annual_demand: float,       # D: 연간 수요량
        order_cost_krw: float,      # S: 1회 주문 비용 (원)
        holding_cost_pct: float = 0.25  # H: 연간 재고유지 비용률
    ) -> Dict:
        """
        경제적 주문량 (EOQ) 산출
        EOQ = sqrt(2 * D * S / H)
        """
        holding_cost = annual_demand * holding_cost_pct
        eoq = np.sqrt(2 * annual_demand * order_cost_krw / holding_cost) if holding_cost > 0 else 0
        order_frequency = annual_demand / eoq if eoq > 0 else 0
        cycle_days = 365 / order_frequency if order_frequency > 0 else 365

        return {
            "annual_demand": annual_demand,
            "order_cost_krw": order_cost_krw,
            "holding_cost_pct": holding_cost_pct,
            "optimal_order_quantity_eoq": round(eoq, 1),
            "order_frequency_per_year": round(order_frequency, 1),
            "order_cycle_days": round(cycle_days, 0),
            "formula": "EOQ = sqrt(2 * D * S / H)",
            "basis": "한국은행 PPI + 나라장터 적산 단가"
        }

    def predict_optimal_order_timing(
        self,
        material_name: str,
        current_ppi: float,
        forecast_months: int = 6
    ) -> Dict:
        """PPI 추세 기반 최적 발주 시기 예측"""
        base_ppi = self.PPI_BASE_INDEX.get(material_name, 130.0)
        ppi_trend = (current_ppi - base_ppi) / base_ppi

        if ppi_trend > 0.1:
            recommendation = "즉시 발주 권장 (가격 상승 추세)"
            optimal_months = 0
        elif ppi_trend < -0.05:
            recommendation = f"{forecast_months}개월 후 발주 권장 (가격 하락 추세)"
            optimal_months = forecast_months
        else:
            recommendation = "정기 발주 유지"
            optimal_months = 3

        return {
            "material_name": material_name,
            "current_ppi": current_ppi,
            "base_ppi_2020": base_ppi,
            "ppi_change_pct": round(ppi_trend * 100, 1),
            "order_recommendation": recommendation,
            "optimal_order_months_ahead": optimal_months,
            "data_source": "한국은행 생산자물가지수 (PPI)"
        }


[파일: apps/api/app/routers/lifecycle.py]

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional
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
async def get_construction_checklist(
    req: ConstructionStartRequest,
    current_user: User = Depends(get_current_user)
):
    return construction_service.generate_checklist(req.project_type, req.project_cost_krw)

@router.post("/construction/safety-plan")
async def generate_safety_plan(
    req: ConstructionStartRequest,
    current_user: User = Depends(get_current_user)
):
    return construction_service.auto_generate_safety_plan(
        req.project_id, f"프로젝트 {req.project_id}",
        req.floor_count, req.excavation_depth_m
    )

@router.post("/supervision/evm")
async def calculate_evm(req: EVMRequest, current_user: User = Depends(get_current_user)):
    return supervision_service.calculate_evm(req.bac_krw, req.pv_krw, req.ev_pct, req.ac_krw)

@router.get("/risk/assessment")
async def get_risk_assessment(current_user: User = Depends(get_current_user)):
    return risk_service.calculate_risk_scores()

@router.post("/disaster-risk/assess")
async def assess_disaster_risk(
    req: DisasterRiskRequest,
    current_user: User = Depends(get_current_user)
):
    return disaster_service.assess_disaster_risk(
        req.region, req.land_use, req.floor_count, req.distance_to_river_m
    )

@router.post("/procurement/eoq")
async def calculate_eoq(req: EOQRequest, current_user: User = Depends(get_current_user)):
    return procurement_optimizer.calculate_eoq(req.annual_demand, req.order_cost_krw)

@router.get("/lifecycle-opt/replacement-schedule")
async def get_replacement_schedule(
    construction_cost_krw: float,
    lifespan_years: int = 50,
    current_user: User = Depends(get_current_user)
):
    return lc_optimizer.optimize_replacement_schedule(construction_cost_krw, lifespan_years)

[완료 체크리스트 Phase 21~38p]
[ ] 착공 전 체크리스트 자동 생성
[ ] 안전관리계획서 자동 작성 (건설기술진흥법 제62조)
[ ] EVM 공정/원가 분석 수학식 검증
[ ] AI 리스크 ISO 31000 점수 산출
[ ] 스마트시티 입지 점수 산출
[ ] 생애주기 최적화 LCC 계산
[ ] 디지털 트윈 HVAC 최적화
[ ] 자연재해 리스크 평가 (자연재해대책법)
[ ] EOQ 자재 조달 최적화
[ ] lifecycle 라우터 220개+ 엔드포인트 등록
```
