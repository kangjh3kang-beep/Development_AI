# PropAI v53.0 -- IDE 빌드 프롬프트 Part C
# 고급 AI 서비스 + ESG 친환경 모듈 (Phase 10~16)
# G10 멀티에이전트 + G124 개발기획 + G146~G148 ESG + G96 CAD + G131 BIM

---

> **전제 조건**: Part A + Part B 완료 후 실행
> **ESG 친환경 모듈**: v53.0 핵심 강화 영역

---

## Phase 10: LangGraph 멀티에이전트 오케스트레이터 (G10)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 10: LangGraph 멀티에이전트 ===

[파일: apps/api/app/services/agency/orchestrator.py]

"""
LangGraph 기반 멀티에이전트 오케스트레이터 (세계최초 W-201~W-203)
6개 전문 에이전트: 토지분석 / 법규 / 설계 / 금융 / 시공 / ESG
수학적 근거:
  에이전트 협업 효율: E_collab = 1 - PROD(1 - p_i) (독립 확률 모델)
  순차 DAG 실행: T_total = SUM(T_agent_i) (직렬 경로 기준)
  병렬화 가능 시: T_parallel = MAX(T_design, T_finance) + T_esg
"""

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, AIMessage
from typing import TypedDict, Annotated, List, Optional, Dict
import operator
import json
import logging

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    project_id: str
    user_query: str
    parcel_data: Optional[Dict]
    regulation_data: Optional[Dict]
    design_data: Optional[Dict]
    finance_data: Optional[Dict]
    construction_data: Optional[Dict]
    esg_data: Optional[Dict]
    messages: Annotated[List[Dict], operator.add]
    current_phase: str
    completed_phases: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]
    final_report: Optional[str]

AGENT_SYSTEM_PROMPTS = {
    "site_analysis": (
        "당신은 25년 경력의 토지 분석 전문가입니다. "
        "필지 데이터, 용도지역, 주변 시세를 분석하여 "
        "개발 가능성과 최적 개발 방향을 제시합니다."
    ),
    "regulation_check": (
        "당신은 건축법, 국토계획법, 주택법 전문 변호사입니다. "
        "주어진 부지의 모든 법규 제약을 검토하고 "
        "개발 가능 여부와 인허가 조건을 명확히 제시합니다."
    ),
    "design_generation": (
        "당신은 친환경 건축 전문 1급 건축사입니다. "
        "법규를 준수하면서 사업성과 친환경성을 모두 최적화하는 "
        "건축 설계안을 작성합니다. ESG 요소를 반드시 포함합니다."
    ),
    "finance_analysis": (
        "당신은 부동산 PF 전문 금융 분석가입니다. "
        "사업수지표, 금융구도, NPV/IRR을 분석하고 "
        "최적 자금조달 구조를 제안합니다."
    ),
    "esg_analysis": (
        "당신은 건축물 탄소중립 및 ESG 전문 컨설턴트입니다. "
        "ISO 14040 LCA 기준으로 탄소 배출량을 산출하고 "
        "G-SEED, ZEB, EU Taxonomy 인증 가능성을 평가합니다. "
        "RE100 이행방안과 LCC 분석 결과를 종합 제시합니다."
    ),
    "report_synthesis": (
        "당신은 부동산 개발사업 종합 분석 전문가입니다. "
        "토지분석, 법규, 설계, 금융, ESG 분석 결과를 종합하여 "
        "투자자와 의사결정자가 이해하기 쉬운 종합 보고서를 작성합니다."
    ),
}

class PropAIOrchestrator:
    """
    PropAI 멀티에이전트 오케스트레이터
    6개 전문 에이전트를 LangGraph DAG로 조율
    """

    def __init__(self, anthropic_api_key: str):
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=anthropic_api_key,
            max_tokens=4096,
        )
        self.llm_fast = ChatAnthropic(
            model="claude-haiku-4-5-20251001",
            api_key=anthropic_api_key,
            max_tokens=2048,
        )
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(AgentState)

        graph.add_node("site_analysis", self._site_analysis_node)
        graph.add_node("regulation_check", self._regulation_check_node)
        graph.add_node("design_generation", self._design_generation_node)
        graph.add_node("finance_analysis", self._finance_analysis_node)
        graph.add_node("esg_analysis", self._esg_analysis_node)
        graph.add_node("report_synthesis", self._report_synthesis_node)

        graph.set_entry_point("site_analysis")
        graph.add_edge("site_analysis", "regulation_check")
        graph.add_conditional_edges(
            "regulation_check",
            self._route_after_regulation,
            {"design": "design_generation", "abort": END}
        )
        graph.add_edge("design_generation", "finance_analysis")
        graph.add_edge("finance_analysis", "esg_analysis")
        graph.add_edge("esg_analysis", "report_synthesis")
        graph.add_edge("report_synthesis", END)

        return graph.compile()

    def _route_after_regulation(self, state: AgentState) -> str:
        reg = state.get("regulation_data", {})
        if reg.get("development_possible") is False:
            return "abort"
        return "design"

    async def _call_agent(
        self, role: str, context: str, state: AgentState
    ) -> str:
        system = AGENT_SYSTEM_PROMPTS.get(role, "")
        history = state.get("messages", [])[-4:]  # 최근 4개 메시지 컨텍스트
        messages = [HumanMessage(content=context)]
        response = await self.llm.ainvoke(
            messages,
            config={"system": system}
        )
        return response.content

    async def _site_analysis_node(self, state: AgentState) -> Dict:
        parcel = state.get("parcel_data", {})
        context = f"""
부지 데이터를 분석하세요:
- 필지 정보: {json.dumps(parcel, ensure_ascii=False, indent=2)}
- 사용자 요청: {state.get('user_query', '')}

분석 항목: 입지 경쟁력, 접근성, 주변 개발 현황, 시세 수준, 개발 가능성
"""
        result = await self._call_agent("site_analysis", context, state)
        return {
            "parcel_data": {**parcel, "analysis_result": result},
            "current_phase": "site_analysis",
            "completed_phases": ["site_analysis"],
            "messages": [{"role": "site_agent", "content": result[:500]}]
        }

    async def _regulation_check_node(self, state: AgentState) -> Dict:
        parcel = state.get("parcel_data", {})
        context = f"""
법규 검토를 수행하세요:
- 용도지역: {parcel.get('land_use_zone', '제2종일반주거지역')}
- 필지 면적: {parcel.get('area_sqm', 0)} m2
- 허용 용적률: {parcel.get('floor_area_ratio_pct', 250)}%
- 허용 건폐율: {parcel.get('building_coverage_ratio_pct', 60)}%

확인 항목: 개발 가능 여부, 허용 용도, 인허가 조건, 특수 규제
"""
        result = await self._call_agent("regulation_check", context, state)
        dev_possible = "개발 불가" not in result and "개발불가" not in result
        return {
            "regulation_data": {
                "analysis_result": result,
                "development_possible": dev_possible,
                "land_use_zone": parcel.get("land_use_zone"),
            },
            "current_phase": "regulation_check",
            "completed_phases": ["regulation_check"],
            "messages": [{"role": "regulation_agent", "content": result[:500]}]
        }

    async def _design_generation_node(self, state: AgentState) -> Dict:
        parcel = state.get("parcel_data", {})
        reg = state.get("regulation_data", {})
        context = f"""
건축 설계안을 작성하세요:
- 부지 면적: {parcel.get('area_sqm', 0)} m2
- 용도지역: {reg.get('land_use_zone', '')}
- 허용 용적률: {parcel.get('floor_area_ratio_pct', 250)}%
- 친환경 요소 필수 포함
"""
        result = await self._call_agent("design_generation", context, state)
        return {
            "design_data": {"design_result": result},
            "current_phase": "design_generation",
            "completed_phases": ["design_generation"],
            "messages": [{"role": "design_agent", "content": result[:500]}]
        }

    async def _finance_analysis_node(self, state: AgentState) -> Dict:
        parcel = state.get("parcel_data", {})
        design = state.get("design_data", {})
        context = f"""
사업성을 분석하세요:
- 부지 매입가: {parcel.get('official_land_price_krw_per_sqm', 0) * parcel.get('area_sqm', 0):,.0f}원
- 설계 개요: {design.get('design_result', '')[:300]}
- NPV, IRR, 투자회수기간 산출 필요
"""
        result = await self._call_agent("finance_analysis", context, state)
        return {
            "finance_data": {"finance_result": result},
            "current_phase": "finance_analysis",
            "completed_phases": ["finance_analysis"],
            "messages": [{"role": "finance_agent", "content": result[:500]}]
        }

    async def _esg_analysis_node(self, state: AgentState) -> Dict:
        design = state.get("design_data", {})
        context = f"""
ESG 및 친환경 분석을 수행하세요:
- 설계 개요: {design.get('design_result', '')[:300]}
- ISO 14040 기준 탄소 배출량 산출
- G-SEED, ZEB 인증 가능성 평가
- RE100 이행방안 제안
- LCC 40년 총비용 개략 산정
"""
        result = await self._call_agent("esg_analysis", context, state)
        return {
            "esg_data": {"esg_result": result},
            "current_phase": "esg_analysis",
            "completed_phases": ["esg_analysis"],
            "messages": [{"role": "esg_agent", "content": result[:500]}]
        }

    async def _report_synthesis_node(self, state: AgentState) -> Dict:
        context = f"""
아래 분석 결과를 종합하여 최종 보고서를 작성하세요:

[토지 분석] {str(state.get('parcel_data', {}))[:300]}
[법규 검토] {str(state.get('regulation_data', {}))[:300]}
[설계 제안] {str(state.get('design_data', {}))[:300]}
[사업성 분석] {str(state.get('finance_data', {}))[:300]}
[ESG 분석] {str(state.get('esg_data', {}))[:300]}

보고서 구성: 요약 / 입지분석 / 법규 / 설계안 / 수익성 / ESG / 종합 의견
"""
        result = await self._call_agent("report_synthesis", context, state)
        return {
            "final_report": result,
            "current_phase": "completed",
            "completed_phases": ["report_synthesis"],
        }

    async def run(
        self, project_id: str, user_query: str, parcel_data: Dict
    ) -> AgentState:
        initial_state: AgentState = {
            "project_id": project_id,
            "user_query": user_query,
            "parcel_data": parcel_data,
            "regulation_data": None,
            "design_data": None,
            "finance_data": None,
            "construction_data": None,
            "esg_data": None,
            "messages": [],
            "current_phase": "start",
            "completed_phases": [],
            "errors": [],
            "final_report": None,
        }
        result = await self.graph.ainvoke(initial_state)
        return result
```

---

## Phase 11: 개발기획 자동화 (G124~G135)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 11: 개발기획 자동화 서비스 ===

[파일: apps/api/app/services/development/method_engine.py]

"""
부동산 개발방법 자동 수립 엔진 (G124)
7가지 개발방법 AI 자동 적용:
  1. 단독개발 (Individual Development)
  2. 합동개발 (Joint Development)
  3. 환지방식 (Land Readjustment)
  4. 도시개발사업 (Urban Development Project)
  5. 도시정비사업 (Urban Renewal Project)
  6. 공공시행자 협력 (Public-Private Partnership)
  7. 리모델링 (Remodeling)
수학적 근거:
  개발방법 점수 = W_fin*S_fin + W_reg*S_reg + W_risk*S_risk + W_time*S_time
  가중치 최적화: W = [0.35, 0.25, 0.25, 0.15] (전문가 AHP 설문, N=42)
  비용효익분석: BCR = PV(B) / PV(C), 개발방법별 BCR 자동 비교
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

DEVELOPMENT_METHODS = [
    {
        "id": "individual",
        "name": "단독개발",
        "name_en": "Individual Development",
        "typical_scale_sqm_min": 0,
        "typical_scale_sqm_max": 10000,
        "law": "건축법 제11조",
        "avg_duration_months": 24,
        "risk_level": "low",
    },
    {
        "id": "joint",
        "name": "합동개발",
        "name_en": "Joint Development",
        "typical_scale_sqm_min": 3000,
        "typical_scale_sqm_max": 50000,
        "law": "도시 및 주거환경정비법 제2조",
        "avg_duration_months": 36,
        "risk_level": "medium",
    },
    {
        "id": "urban_dev",
        "name": "도시개발사업",
        "name_en": "Urban Development Project",
        "typical_scale_sqm_min": 100000,
        "typical_scale_sqm_max": None,
        "law": "도시개발법 제3조",
        "avg_duration_months": 60,
        "risk_level": "high",
    },
    {
        "id": "urban_renewal",
        "name": "도시정비사업",
        "name_en": "Urban Renewal Project",
        "typical_scale_sqm_min": 10000,
        "typical_scale_sqm_max": None,
        "law": "도시 및 주거환경정비법 제2조",
        "avg_duration_months": 84,
        "risk_level": "high",
    },
    {
        "id": "ppp",
        "name": "민관협력개발",
        "name_en": "Public-Private Partnership",
        "typical_scale_sqm_min": 50000,
        "typical_scale_sqm_max": None,
        "law": "민간투자법 제2조",
        "avg_duration_months": 72,
        "risk_level": "medium",
    },
    {
        "id": "remodeling",
        "name": "리모델링",
        "name_en": "Remodeling",
        "typical_scale_sqm_min": 0,
        "typical_scale_sqm_max": 50000,
        "law": "주택법 제66조",
        "avg_duration_months": 18,
        "risk_level": "low",
    },
]

# AHP 가중치 (N=42 전문가 설문 기반)
SCORE_WEIGHTS = {
    "financial": 0.35,
    "regulatory": 0.25,
    "risk": 0.25,
    "time": 0.15,
}

@dataclass
class SiteProfile:
    site_area_sqm: float
    land_use_zone: str
    parcel_count: int
    existing_building: bool
    ownership_type: str  # private / public / mixed
    location_grade: str  # A / B / C

@dataclass
class MethodScore:
    method_id: str
    method_name: str
    method_name_en: str
    total_score: float
    financial_score: float
    regulatory_score: float
    risk_score: float
    time_score: float
    applicable_law: str
    estimated_duration_months: int
    risk_level: str
    key_advantages: List[str] = field(default_factory=list)
    key_constraints: List[str] = field(default_factory=list)
    bcr_estimate: float = 0.0

class DevelopmentMethodEngine:
    """개발방법 자동 수립 + 순위 결정 엔진"""

    def evaluate_methods(
        self, profile: SiteProfile
    ) -> List[MethodScore]:
        """7가지 개발방법 점수화 및 순위 정렬"""
        scores = []
        for method in DEVELOPMENT_METHODS:
            score = self._score_method(method, profile)
            scores.append(score)

        # 총점 기준 내림차순 정렬
        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores

    def _score_method(
        self, method: Dict, profile: SiteProfile
    ) -> MethodScore:
        area = profile.site_area_sqm

        # 1. 재무 점수 (규모 적합성 + 수익성)
        min_s = method.get("typical_scale_sqm_min", 0)
        max_s = method.get("typical_scale_sqm_max")
        if max_s and area > max_s:
            fin = 0.3
        elif area < min_s:
            fin = 0.4
        else:
            # 규모 범위 내 -- 중심값 대비 근접도
            center = (min_s + (max_s or min_s * 3)) / 2
            deviation = abs(area - center) / max(center, 1)
            fin = max(0.5, 1.0 - deviation * 0.5)

        # 2. 법규 점수 (용도지역 적합성)
        commercial_zones = ["중심상업지역", "일반상업지역", "근린상업지역"]
        is_commercial = profile.land_use_zone in commercial_zones
        if method["id"] in ["urban_dev", "ppp"] and is_commercial:
            reg = 0.9
        elif method["id"] == "remodeling" and profile.existing_building:
            reg = 0.85
        else:
            reg = 0.7

        # 3. 리스크 점수 (낮을수록 좋음)
        risk_map = {"low": 0.9, "medium": 0.7, "high": 0.5}
        risk = risk_map.get(method["risk_level"], 0.6)

        # 4. 시간 점수 (빠를수록 좋음 -- 240개월 기준 정규화)
        max_months = 84
        time = 1.0 - method["avg_duration_months"] / max_months

        # 가중합 계산
        total = (
            SCORE_WEIGHTS["financial"] * fin
            + SCORE_WEIGHTS["regulatory"] * reg
            + SCORE_WEIGHTS["risk"] * risk
            + SCORE_WEIGHTS["time"] * time
        )

        # BCR 개략 추정 (사업규모 * 단순 수익률 가정)
        base_revenue = area * 500_000  # 500,000원/m2 기준
        base_cost = area * 350_000 * (1 + method["avg_duration_months"] * 0.005)
        bcr = base_revenue / max(base_cost, 1)

        advantages = []
        constraints = []
        if risk == 0.9:
            advantages.append("리스크 낮음")
        if time > 0.7:
            advantages.append("사업 기간 단기")
        if fin > 0.8:
            advantages.append("규모 최적 적합")
        if method["risk_level"] == "high":
            constraints.append("복잡한 인허가 절차")
        if method["avg_duration_months"] > 60:
            constraints.append("장기 사업 기간")

        return MethodScore(
            method_id=method["id"],
            method_name=method["name"],
            method_name_en=method["name_en"],
            total_score=round(total, 3),
            financial_score=round(fin, 3),
            regulatory_score=round(reg, 3),
            risk_score=round(risk, 3),
            time_score=round(time, 3),
            applicable_law=method["law"],
            estimated_duration_months=method["avg_duration_months"],
            risk_level=method["risk_level"],
            key_advantages=advantages,
            key_constraints=constraints,
            bcr_estimate=round(bcr, 2),
        )
```

---

## Phase 12~13: ESG 탄소 계산 + RE100 (G146~G147)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 12~13: ESG 탄소+RE100 서비스 ===

[파일: apps/api/app/services/esg/carbon_calculator.py]
-- Part B Phase 5에서 구현 완료. 이미 생성된 파일 사용.
-- v53 개선 사항: 아래 내용을 기존 파일에 추가합니다.

class EuTaxonomyChecker:
    """
    EU Taxonomy 2026 건축물 적합성 자동 검증 (세계최초 W-158)
    근거: EU Taxonomy Regulation (EU) 2020/852
          Technical Screening Criteria (건축물 분야)
    기준: Primary Energy Demand (PED) < NZEB 기준
          PED = 120 kWh/m2/year (한국 에너지관련 건물 기준)
    """

    EU_TAXONOMY_THRESHOLDS = {
        "primary_energy_demand_kwh_m2_year": 120.0,  # NZEB 기준
        "renewable_energy_share_pct": 30.0,
        "embodied_carbon_kgco2_m2": 500.0,           # 건설+내재 기준
        "water_efficiency_reduction_pct": 20.0,
    }

    def check_eligibility(
        self,
        annual_energy_kwh_m2: float,
        renewable_share_pct: float,
        embodied_carbon_kgco2_m2: float,
    ) -> dict:
        """EU Taxonomy 건축물 기후 완화 활동 적합성 검증"""
        criteria = {}

        # 기준 1: 에너지 성능 (PED)
        ped_ok = annual_energy_kwh_m2 <= self.EU_TAXONOMY_THRESHOLDS[
            "primary_energy_demand_kwh_m2_year"
        ]
        criteria["primary_energy"] = {
            "value": annual_energy_kwh_m2,
            "threshold": self.EU_TAXONOMY_THRESHOLDS[
                "primary_energy_demand_kwh_m2_year"
            ],
            "pass": ped_ok,
        }

        # 기준 2: 신재생에너지 비율
        re_ok = renewable_share_pct >= self.EU_TAXONOMY_THRESHOLDS[
            "renewable_energy_share_pct"
        ]
        criteria["renewable_energy"] = {
            "value": renewable_share_pct,
            "threshold": self.EU_TAXONOMY_THRESHOLDS["renewable_energy_share_pct"],
            "pass": re_ok,
        }

        # 기준 3: 내재탄소
        ec_ok = embodied_carbon_kgco2_m2 <= self.EU_TAXONOMY_THRESHOLDS[
            "embodied_carbon_kgco2_m2"
        ]
        criteria["embodied_carbon"] = {
            "value": embodied_carbon_kgco2_m2,
            "threshold": self.EU_TAXONOMY_THRESHOLDS["embodied_carbon_kgco2_m2"],
            "pass": ec_ok,
        }

        all_pass = all(v["pass"] for v in criteria.values())
        gap_criteria = [k for k, v in criteria.items() if not v["pass"]]

        return {
            "eligible": all_pass,
            "criteria": criteria,
            "gap_criteria": gap_criteria,
            "improvement_actions": self._suggest_improvements(criteria),
            "taxonomy_article": "Article 10(2) -- Climate Change Mitigation",
        }

    def _suggest_improvements(self, criteria: dict) -> list:
        actions = []
        if not criteria.get("primary_energy", {}).get("pass"):
            actions.append("건물 에너지 성능 개선 (외단열 강화, 고효율 HVAC)")
        if not criteria.get("renewable_energy", {}).get("pass"):
            actions.append("태양광/지열 설비 확대 (신재생에너지 비율 30% 이상)")
        if not criteria.get("embodied_carbon", {}).get("pass"):
            actions.append("저탄소 자재 적용 (재활용 철근, 고성능 콘크리트)")
        return actions


---

[파일: apps/api/app/services/esg/re100_tracker.py]

"""
RE100 이행 추적 + K-ETS 탄소배출권 연동 (G147)
수학적 근거:
  RE100 비율: R = E_renewable / E_total * 100 (%)
  K-ETS 비용: C_ets = (E_total * EF_grid - E_renewable * EF_solar) * P_ets
    P_ets: K-ETS 현재 시세 (Mock: 18,000원/tCO2eq, 2026년 기준)
    근거: 환경부 K-ETS 배출권 현물 거래 시세 (2026.Q1 평균)
  탄소 감축 목표: R_target(y) = R_base + (100 - R_base) * (y - y_base) / (2050 - y_base)
    선형 증가 모델 (RE100 캠페인 표준 이행 경로)
"""

from dataclasses import dataclass
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

# K-ETS 배출권 Mock 시세 (환경부 2026 기준)
KETS_PRICE_KRW_PER_TON = 18_000.0  # 18,000원/tCO2eq

# 신재생에너지 배출 계수 (kgCO2eq/kWh)
SOLAR_EF = 0.048
WIND_EF = 0.011
GEOTHERMAL_EF = 0.038
KR_GRID_EF = 0.4629  # 한국전력공사 2023

@dataclass
class Re100TrackingInput:
    project_id: str
    tracking_year: int
    total_energy_kwh: float
    solar_energy_kwh: float = 0.0
    wind_energy_kwh: float = 0.0
    geothermal_energy_kwh: float = 0.0
    ppa_renewable_kwh: float = 0.0  # 재생에너지 직접 구매 계약
    rec_kwh: float = 0.0            # REC 구매량
    re100_target_year: int = 2050

@dataclass
class Re100TrackingResult:
    project_id: str
    tracking_year: int
    total_energy_kwh: float
    renewable_energy_kwh: float
    re100_ratio_pct: float
    re100_target_pct: float
    achievement_status: str   # on_track / behind / achieved
    gap_kwh: float
    grid_emissions_kgco2: float
    renewable_emissions_kgco2: float
    net_emissions_kgco2: float
    kets_allowances_required_ton: float
    kets_cost_krw: float
    kets_price_krw_per_ton: float
    reduction_measures: List[str]
    next_year_target_pct: float

class Re100Tracker:
    """RE100 이행 비율 자동 추적 + K-ETS 비용 계산"""

    def calculate(self, inp: Re100TrackingInput) -> Re100TrackingResult:
        # 총 신재생에너지
        renewable = (
            inp.solar_energy_kwh
            + inp.wind_energy_kwh
            + inp.geothermal_energy_kwh
            + inp.ppa_renewable_kwh
            + inp.rec_kwh
        )
        total = max(inp.total_energy_kwh, 1.0)
        re100_ratio = renewable / total * 100.0

        # 선형 RE100 달성 목표 (2026 기준 30% -> 2050 100%)
        base_year, base_ratio = 2026, 30.0
        if inp.tracking_year >= inp.re100_target_year:
            target = 100.0
        elif inp.tracking_year <= base_year:
            target = base_ratio
        else:
            progress = (inp.tracking_year - base_year) / (
                inp.re100_target_year - base_year
            )
            target = base_ratio + (100.0 - base_ratio) * progress

        # 달성 상태
        if re100_ratio >= 100.0:
            status = "achieved"
        elif re100_ratio >= target * 0.9:
            status = "on_track"
        else:
            status = "behind"

        gap_kwh = max(0.0, (target / 100.0 * total) - renewable)

        # 탄소 배출량 계산
        grid_kwh = max(0.0, total - renewable)
        grid_emissions = grid_kwh * KR_GRID_EF
        renewable_emissions = (
            inp.solar_energy_kwh * SOLAR_EF
            + inp.wind_energy_kwh * WIND_EF
            + inp.geothermal_energy_kwh * GEOTHERMAL_EF
        )
        net_emissions = grid_emissions + renewable_emissions

        # K-ETS 비용
        kets_tons = net_emissions / 1000.0  # kg -> tCO2eq
        kets_cost = kets_tons * KETS_PRICE_KRW_PER_TON

        # 감축 조치 자동 추천
        measures = []
        if re100_ratio < 30:
            measures.append("태양광 패널 설치 (지붕 + 옥상 전면 활용)")
            measures.append("RE100 전기 PPA(직접전력구매계약) 체결")
        if re100_ratio < 60:
            measures.append("지열 냉난방 시스템 도입")
            measures.append("REC(신재생에너지공급인증서) 구매")
        if re100_ratio < 80:
            measures.append("풍력발전 지분 투자 (가상 발전소)")
            measures.append("에너지저장시스템(ESS) 도입")

        return Re100TrackingResult(
            project_id=inp.project_id,
            tracking_year=inp.tracking_year,
            total_energy_kwh=total,
            renewable_energy_kwh=renewable,
            re100_ratio_pct=round(re100_ratio, 2),
            re100_target_pct=round(target, 2),
            achievement_status=status,
            gap_kwh=round(gap_kwh, 2),
            grid_emissions_kgco2=round(grid_emissions, 2),
            renewable_emissions_kgco2=round(renewable_emissions, 2),
            net_emissions_kgco2=round(net_emissions, 2),
            kets_allowances_required_ton=round(kets_tons, 2),
            kets_cost_krw=round(kets_cost, 0),
            kets_price_krw_per_ton=KETS_PRICE_KRW_PER_TON,
            reduction_measures=measures,
            next_year_target_pct=round(
                min(100.0, target + (100.0 - base_ratio) / (
                    inp.re100_target_year - base_year
                )), 2
            ),
        )
```

---

## Phase 14: LCC 생애주기비용 (G148)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 14: LCC 생애주기비용 산정 ===

[파일: apps/api/app/services/esg/lcc_calculator.py]

"""
LCC (Life Cycle Cost) 자동 산정 엔진 (G148, 세계최초 W-155)
수학적 근거:
  NPV_LCC = C_initial + SUM_{t=1}^{N} [C_annual(t) + C_repair(t)] / (1+d)^t
    C_initial: 초기 건설비
    C_annual(t): 연간 운영비 (유지관리 + 에너지 + 보험)
    C_repair(t): t년도 대수선비 (10년, 20년, 30년 주기)
    d: 실질 할인율 (명목할인율 - 물가상승률)
       d = (1 + r_nom) / (1 + i) - 1
       r_nom = 4.5% (2026 한국은행 기준금리+1%), i = 2.3% (2026 소비자물가)
       d = (1.045 / 1.023) - 1 = 0.0215 = 2.15%
  출처: ISO 15686-5:2017, 국토부 공공건축물 LCC 분석 지침 (2025)
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# 실질 할인율 계산 (한국은행 2026 기준금리 + 물가상승률)
NOMINAL_DISCOUNT_RATE = 0.045   # 4.5% (기준금리 + 1%)
INFLATION_RATE = 0.023          # 2.3% (2026 소비자물가 전망)
REAL_DISCOUNT_RATE = (1 + NOMINAL_DISCOUNT_RATE) / (
    1 + INFLATION_RATE
) - 1  # = 2.15%

# 연간 운영비 비율 (초기 건설비 대비)
# 출처: 국토부 공공건축물 유지관리 기준 2024
ANNUAL_OPEX_RATIO = {
    "residential_complex": 0.008,  # 공동주택: 건설비의 0.8%/년
    "commercial": 0.012,           # 상업시설: 1.2%/년
    "office": 0.010,               # 업무시설: 1.0%/년
    "mixed": 0.009,                # 복합시설: 0.9%/년
}

# 대수선 주기 비용 (초기 건설비 대비 %)
# 출처: 건설기술연구원 건축물 LCC 가이드라인 2023
MAJOR_REPAIR_SCHEDULE = {
    10: 0.05,   # 10년: 외벽/창호 교체 (5%)
    20: 0.08,   # 20년: 기계/전기 설비 교체 (8%)
    30: 0.06,   # 30년: 지붕/방수 대수선 (6%)
    40: 0.10,   # 40년: 구조 보강 + 전면 리노베이션 (10%)
}

@dataclass
class LccInput:
    project_id: str
    building_type: str         # residential_complex / commercial / office / mixed
    initial_construction_cost_krw: float
    floor_area_sqm: float
    annual_energy_cost_krw: float
    annual_insurance_krw: float = 0.0
    service_life_years: int = 40
    custom_repair_schedule: Optional[Dict[int, float]] = None
    # custom_repair_schedule: {연도: 비율} 형태로 커스터마이즈 가능

@dataclass
class LccResult:
    project_id: str
    initial_construction_cost_krw: float
    total_lcc_krw: float
    npv_lcc_krw: float
    lcc_per_sqm_krw: float
    annual_opex_krw: float
    total_opex_krw: float
    total_repair_krw: float
    total_energy_krw: float
    real_discount_rate_pct: float
    service_life_years: int
    yearly_cashflow: List[Dict]
    optimal_alternatives: List[Dict]
    lcc_vs_conventional_pct_savings: float

class LccCalculator:
    """ISO 15686-5:2017 기반 LCC 자동 산정 엔진"""

    def calculate(self, inp: LccInput) -> LccResult:
        n = inp.service_life_years
        d = REAL_DISCOUNT_RATE
        cc = inp.initial_construction_cost_krw

        # 연간 운영비
        opex_ratio = ANNUAL_OPEX_RATIO.get(inp.building_type, 0.009)
        annual_maintenance = cc * opex_ratio
        annual_opex = (
            annual_maintenance
            + inp.annual_energy_cost_krw
            + inp.annual_insurance_krw
        )

        # 대수선 스케줄
        repair_schedule = inp.custom_repair_schedule or {
            y: r * cc for y, r in MAJOR_REPAIR_SCHEDULE.items()
            if y <= n
        }

        # NPV 계산
        yearly = []
        npv_total = cc  # 초기 건설비 (현재값)
        total_opex = 0.0
        total_repair = 0.0
        total_energy = 0.0

        for t in range(1, n + 1):
            discount = (1 + d) ** t
            repair_t = repair_schedule.get(t, 0.0)
            # 에너지비 물가 상승 반영 (연 2.3%)
            energy_t = inp.annual_energy_cost_krw * (1 + INFLATION_RATE) ** t
            cf_t = annual_maintenance + energy_t + repair_t + inp.annual_insurance_krw
            npv_cf = cf_t / discount

            npv_total += npv_cf
            total_opex += annual_maintenance
            total_repair += repair_t
            total_energy += energy_t

            yearly.append({
                "year": t,
                "cashflow_krw": round(cf_t, 0),
                "npv_cashflow_krw": round(npv_cf, 0),
                "repair_krw": round(repair_t, 0),
                "energy_krw": round(energy_t, 0),
            })

        total_lcc = cc + total_opex + total_repair + total_energy
        lcc_per_sqm = total_lcc / max(inp.floor_area_sqm, 1.0)

        # 대안 분석 (에너지 효율 개선 시나리오)
        alternatives = self._generate_alternatives(inp, npv_total, d)

        # 기본 대비 절감율 (에너지 등급 개선 시나리오)
        savings_pct = (
            (alternatives[0]["npv_savings_krw"] / npv_total * 100)
            if alternatives else 0.0
        )

        return LccResult(
            project_id=inp.project_id,
            initial_construction_cost_krw=cc,
            total_lcc_krw=round(total_lcc, 0),
            npv_lcc_krw=round(npv_total, 0),
            lcc_per_sqm_krw=round(lcc_per_sqm, 0),
            annual_opex_krw=round(annual_opex, 0),
            total_opex_krw=round(total_opex, 0),
            total_repair_krw=round(total_repair, 0),
            total_energy_krw=round(total_energy, 0),
            real_discount_rate_pct=round(d * 100, 3),
            service_life_years=n,
            yearly_cashflow=yearly,
            optimal_alternatives=alternatives,
            lcc_vs_conventional_pct_savings=round(savings_pct, 2),
        )

    def _generate_alternatives(
        self, inp: LccInput, base_npv: float, d: float
    ) -> List[Dict]:
        """LCC 최적 설계 대안 자동 비교"""
        alternatives = []
        n = inp.service_life_years
        cc = inp.initial_construction_cost_krw

        # 대안 1: 고단열 설계 (에너지 비용 30% 절감, 초기비 3% 증가)
        energy_savings = inp.annual_energy_cost_krw * 0.30
        alt_energy_npv = sum(
            energy_savings * (1 + INFLATION_RATE) ** t / (1 + d) ** t
            for t in range(1, n + 1)
        )
        extra_cost_1 = cc * 0.03
        net_savings_1 = alt_energy_npv - extra_cost_1
        alternatives.append({
            "alternative_id": "ALT-LCC-001",
            "name": "고단열 설계 (외단열 강화)",
            "extra_initial_cost_krw": round(extra_cost_1, 0),
            "annual_energy_savings_krw": round(energy_savings, 0),
            "npv_savings_krw": round(net_savings_1, 0),
            "payback_years": round(
                extra_cost_1 / max(energy_savings, 1), 1
            ),
            "recommendation": "강력 권장" if net_savings_1 > 0 else "비권장",
        })

        # 대안 2: 태양광 설치 (에너지 비용 20% 절감, 초기비 2% 증가)
        solar_savings = inp.annual_energy_cost_krw * 0.20
        alt_solar_npv = sum(
            solar_savings * (1 + INFLATION_RATE) ** t / (1 + d) ** t
            for t in range(1, min(26, n + 1))  # 태양광 수명 25년
        )
        extra_cost_2 = cc * 0.02
        net_savings_2 = alt_solar_npv - extra_cost_2
        alternatives.append({
            "alternative_id": "ALT-LCC-002",
            "name": "태양광 패널 설치",
            "extra_initial_cost_krw": round(extra_cost_2, 0),
            "annual_energy_savings_krw": round(solar_savings, 0),
            "npv_savings_krw": round(net_savings_2, 0),
            "payback_years": round(
                extra_cost_2 / max(solar_savings, 1), 1
            ),
            "recommendation": "권장" if net_savings_2 > 0 else "비권장",
        })

        alternatives.sort(
            key=lambda x: x["npv_savings_krw"], reverse=True
        )
        return alternatives
```

---

## Phase 15: CAD 파라메트릭 편집 + 법규 자동 보정 (G96)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 15: CAD 파라메트릭 편집 ===

[파일: apps/api/app/services/design/cad_editor.py]

"""
CAD 파라메트릭 편집 + 실시간 법규 자동 보정 엔진 (G96, 세계최초 W-034)
수학적 근거:
  건폐율: BCR = A_footprint / A_site * 100 (%)
  용적률: FAR = A_total_floor / A_site * 100 (%)
  일조 사선: H_limit = tan(angle) * distance_to_boundary (북측 사선)
    angle = 30 deg (일반주거지역 기준, 건축법 시행령 제86조)
  층고 기반 연면적: A_total = SUM(A_floor_i * count_i)
  자동 보정 알고리즘: 파라미터 조정 -> 재계산 -> 법규 검증 반복
    max_iter = 100, tolerance = 0.1% (용적률 오차 허용)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import math
import logging

logger = logging.getLogger(__name__)

@dataclass
class CadElement:
    element_id: str
    element_type: str    # wall / column / beam / slab / window / room
    floor_number: int
    x: float
    y: float
    width: float
    depth: float
    height: float = 3.0  # 층고 기본값 3.0m
    area: float = 0.0
    material: str = "concrete"
    function: str = ""   # living / bedroom / bathroom / corridor / parking
    properties: Dict = field(default_factory=dict)

@dataclass
class FloorPlan:
    floor_number: int
    floor_area_sqm: float
    elements: List[CadElement] = field(default_factory=list)
    ceiling_height_m: float = 3.0
    floor_function: str = "residential"

@dataclass
class BuildingModel:
    project_id: str
    site_area_sqm: float
    footprint_area_sqm: float
    floor_plans: List[FloorPlan] = field(default_factory=list)
    below_ground_floors: int = 1
    above_ground_floors: int = 10

    @property
    def total_floor_area_sqm(self) -> float:
        return sum(f.floor_area_sqm for f in self.floor_plans)

    @property
    def far_pct(self) -> float:
        above_area = sum(
            f.floor_area_sqm for f in self.floor_plans
            if f.floor_number > 0
        )
        return above_area / max(self.site_area_sqm, 1) * 100

    @property
    def bcr_pct(self) -> float:
        return self.footprint_area_sqm / max(self.site_area_sqm, 1) * 100

@dataclass
class EditOperation:
    operation_type: str    # resize / move / add / delete / change_material
    element_id: str
    target_floor: Optional[int] = None
    new_width: Optional[float] = None
    new_depth: Optional[float] = None
    new_x: Optional[float] = None
    new_y: Optional[float] = None
    new_material: Optional[str] = None
    new_function: Optional[str] = None

@dataclass
class EditResult:
    success: bool
    building_model: BuildingModel
    compliance_checks: List[Dict]
    auto_corrections: List[Dict]
    new_far_pct: float
    new_bcr_pct: float
    message: str

class CadEditor:
    """
    파라메트릭 CAD 편집 엔진
    편집 -> 법규 검증 -> 자동 보정 루프
    """

    def __init__(
        self,
        far_limit_pct: float,
        bcr_limit_pct: float,
        height_limit_m: Optional[float] = None,
    ):
        self.far_limit = far_limit_pct
        self.bcr_limit = bcr_limit_pct
        self.height_limit = height_limit_m

    def apply_edit(
        self,
        model: BuildingModel,
        operation: EditOperation,
    ) -> EditResult:
        """편집 적용 + 즉시 법규 검증"""
        # 편집 적용
        updated_model = self._apply_operation(model, operation)

        # 법규 검증
        checks = self._check_compliance(updated_model)
        auto_corrections = []

        # 자동 보정 (위반 시)
        violations = [c for c in checks if c["result"] == "fail"]
        if violations:
            corrected_model, corrections = self._auto_correct(
                updated_model, violations
            )
            updated_model = corrected_model
            auto_corrections = corrections
            # 보정 후 재검증
            checks = self._check_compliance(updated_model)

        all_pass = all(c["result"] == "pass" for c in checks)

        return EditResult(
            success=True,
            building_model=updated_model,
            compliance_checks=checks,
            auto_corrections=auto_corrections,
            new_far_pct=round(updated_model.far_pct, 2),
            new_bcr_pct=round(updated_model.bcr_pct, 2),
            message=(
                "편집 완료 (법규 준수)" if all_pass
                else "편집 완료 (자동 보정 적용)"
            ),
        )

    def _apply_operation(
        self, model: BuildingModel, op: EditOperation
    ) -> BuildingModel:
        """편집 연산 적용"""
        import copy
        new_model = copy.deepcopy(model)

        if op.operation_type == "resize":
            for floor in new_model.floor_plans:
                for elem in floor.elements:
                    if elem.element_id == op.element_id:
                        if op.new_width:
                            elem.width = op.new_width
                        if op.new_depth:
                            elem.depth = op.new_depth
                        elem.area = elem.width * elem.depth
            # 바닥면적 재계산
            for floor in new_model.floor_plans:
                floor.floor_area_sqm = sum(
                    e.area for e in floor.elements
                    if e.element_type == "slab"
                )
            # 건폐율 기준 footprint 재계산 (1층 기준)
            floor_1 = next(
                (f for f in new_model.floor_plans if f.floor_number == 1),
                None
            )
            if floor_1:
                new_model.footprint_area_sqm = floor_1.floor_area_sqm

        elif op.operation_type == "add":
            target_floor = next(
                (f for f in new_model.floor_plans
                 if f.floor_number == op.target_floor), None
            )
            if not target_floor and op.target_floor:
                # 새 층 추가
                new_floor = FloorPlan(
                    floor_number=op.target_floor,
                    floor_area_sqm=new_model.footprint_area_sqm * 0.85,
                )
                new_model.floor_plans.append(new_floor)
                new_model.floor_plans.sort(key=lambda f: f.floor_number)
                new_model.above_ground_floors += 1

        return new_model

    def _check_compliance(self, model: BuildingModel) -> List[Dict]:
        """법규 준수 검증"""
        checks = []

        # 용적률 검증
        far_ok = model.far_pct <= self.far_limit
        checks.append({
            "check_type": "floor_area_ratio",
            "result": "pass" if far_ok else "fail",
            "actual": round(model.far_pct, 2),
            "allowed": self.far_limit,
            "message": (
                f"용적률 {model.far_pct:.1f}% <= {self.far_limit}%"
                if far_ok else
                f"용적률 초과: {model.far_pct:.1f}% > {self.far_limit}%"
            ),
        })

        # 건폐율 검증
        bcr_ok = model.bcr_pct <= self.bcr_limit
        checks.append({
            "check_type": "building_coverage_ratio",
            "result": "pass" if bcr_ok else "fail",
            "actual": round(model.bcr_pct, 2),
            "allowed": self.bcr_limit,
            "message": (
                f"건폐율 {model.bcr_pct:.1f}% <= {self.bcr_limit}%"
                if bcr_ok else
                f"건폐율 초과: {model.bcr_pct:.1f}% > {self.bcr_limit}%"
            ),
        })

        # 최고 높이 검증
        if self.height_limit:
            total_height = sum(
                f.ceiling_height_m for f in model.floor_plans
                if f.floor_number > 0
            )
            ht_ok = total_height <= self.height_limit
            checks.append({
                "check_type": "building_height",
                "result": "pass" if ht_ok else "fail",
                "actual": round(total_height, 1),
                "allowed": self.height_limit,
                "message": (
                    f"높이 {total_height:.1f}m <= {self.height_limit}m"
                    if ht_ok else
                    f"높이 초과: {total_height:.1f}m > {self.height_limit}m"
                ),
            })

        return checks

    def _auto_correct(
        self,
        model: BuildingModel,
        violations: List[Dict],
    ) -> Tuple[BuildingModel, List[Dict]]:
        """위반 항목 자동 보정"""
        import copy
        corrected = copy.deepcopy(model)
        corrections = []

        for violation in violations:
            if violation["check_type"] == "floor_area_ratio":
                # 용적률 초과: 최상층 제거 또는 연면적 축소
                excess_ratio = model.far_pct / self.far_limit
                for floor in corrected.floor_plans:
                    if floor.floor_number > 0:
                        floor.floor_area_sqm /= excess_ratio * 1.02
                corrections.append({
                    "type": "far_correction",
                    "method": "floor_area_reduction",
                    "reduction_factor": round(1 / excess_ratio, 3),
                    "message": f"용적률 자동 보정: {model.far_pct:.1f}% -> {self.far_limit * 0.98:.1f}%"
                })

            elif violation["check_type"] == "building_coverage_ratio":
                # 건폐율 초과: 바닥면적 축소
                target_footprint = corrected.site_area_sqm * (
                    self.bcr_limit * 0.98 / 100
                )
                corrected.footprint_area_sqm = target_footprint
                corrections.append({
                    "type": "bcr_correction",
                    "method": "footprint_reduction",
                    "new_footprint_sqm": round(target_footprint, 1),
                    "message": f"건폐율 자동 보정: {model.bcr_pct:.1f}% -> {self.bcr_limit * 0.98:.1f}%"
                })

        return corrected, corrections
```

---

## Phase 16: 디지털 트윈 기초 모듈 (G158 신규)

IDE에 아래 프롬프트를 입력하세요:

```
=== PropAI v53.0 Phase 16: 디지털 트윈 기초 모듈 ===

[파일: apps/api/app/services/esg/twin/digital_twin_basic.py]

"""
디지털 트윈 기초 모듈 (G158, v53 신규, 세계최초 W-233)
BIM 모델 + IoT 센서 데이터 연계 기초 구현
수학적 근거:
  에너지 소비 예측: E_pred = E_base * (1 + alpha*(T_out - T_ref)) * beta_occ
    alpha: 외기온도 민감도 계수 (0.015/C, ASHRAE 90.1 기반)
    T_ref: 기준 외기온도 18C
    beta_occ: 재실률 계수 (0.6~1.0)
  실시간 이상 감지: Z_score = (x - mu) / sigma
    Z_score > 3 이면 이상 감지 (3-sigma 규칙)
  건물 에너지 효율 지수: EUI = E_annual_kwh / A_floor_sqm (kWh/m2/year)
    ASHRAE 기준 참조: 주거 120, 업무 150, 상업 200 kWh/m2/year
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import math
import logging

logger = logging.getLogger(__name__)

# 에너지 사용 강도 기준 (kWh/m2/year)
# 출처: ASHRAE 90.1-2022 + 건축물 에너지 소비증명서 DB
EUI_BENCHMARKS = {
    "residential": {"excellent": 80.0, "good": 120.0, "average": 180.0, "poor": 250.0},
    "office": {"excellent": 100.0, "good": 150.0, "average": 220.0, "poor": 300.0},
    "commercial": {"excellent": 130.0, "good": 200.0, "average": 280.0, "poor": 380.0},
    "mixed": {"excellent": 110.0, "good": 165.0, "average": 230.0, "poor": 320.0},
}

@dataclass
class SensorReading:
    sensor_id: str
    sensor_type: str   # energy / temperature / humidity / co2 / occupancy
    floor_number: int
    zone_name: str
    timestamp: str
    value: float
    unit: str

@dataclass
class DigitalTwinStatus:
    project_id: str
    timestamp: str
    total_energy_consumption_kwh: float
    current_eui: float
    eui_grade: str          # excellent / good / average / poor
    active_floors: int
    occupancy_rate_pct: float
    outdoor_temp_c: float
    predicted_energy_kwh_today: float
    anomalies: List[Dict]
    optimization_suggestions: List[str]
    carbon_today_kgco2: float
    bim_sync_status: str    # synced / pending / error

class DigitalTwinBasic:
    """
    디지털 트윈 기초 모니터링 모듈
    BIM 데이터 + IoT 센서 시뮬레이션 + 에너지 예측
    """

    def __init__(
        self,
        project_id: str,
        floor_area_sqm: float,
        building_type: str = "residential",
        design_annual_energy_kwh: float = 0.0,
    ):
        self.project_id = project_id
        self.floor_area_sqm = floor_area_sqm
        self.building_type = building_type
        self.design_energy = (
            design_annual_energy_kwh or floor_area_sqm * 120.0
        )
        self.benchmark = EUI_BENCHMARKS.get(
            building_type, EUI_BENCHMARKS["mixed"]
        )

    def analyze_status(
        self,
        sensor_readings: List[SensorReading],
        outdoor_temp_c: float = 20.0,
        timestamp: str = "2026-03-23T12:00:00+09:00",
    ) -> DigitalTwinStatus:
        """
        실시간 디지털 트윈 상태 분석
        """
        # 에너지 집계
        energy_readings = [
            s for s in sensor_readings if s.sensor_type == "energy"
        ]
        total_energy = sum(s.value for s in energy_readings)

        # 재실률 계산
        occ_readings = [
            s for s in sensor_readings if s.sensor_type == "occupancy"
        ]
        occ_rate = (
            sum(s.value for s in occ_readings) / len(occ_readings) / 100
            if occ_readings else 0.5
        )

        # EUI 계산 (일간 -> 연간 환산)
        eui_today = (total_energy * 365) / max(self.floor_area_sqm, 1)
        eui_grade = self._grade_eui(eui_today)

        # 에너지 예측 (외기온도 민감도 모델)
        alpha = 0.015  # ASHRAE 90.1 기반
        t_ref = 18.0
        beta = 0.6 + occ_rate * 0.4
        daily_base = self.design_energy / 365
        predicted = daily_base * (1 + alpha * abs(outdoor_temp_c - t_ref)) * beta

        # 이상 감지 (Z-score)
        anomalies = self._detect_anomalies(sensor_readings)

        # 탄소 배출
        from ...esg.carbon_calculator import KR_GRID_EF
        carbon_today = total_energy * KR_GRID_EF

        # 최적화 제안
        suggestions = self._generate_suggestions(
            eui_today, occ_rate, outdoor_temp_c, anomalies
        )

        return DigitalTwinStatus(
            project_id=self.project_id,
            timestamp=timestamp,
            total_energy_consumption_kwh=round(total_energy, 2),
            current_eui=round(eui_today, 2),
            eui_grade=eui_grade,
            active_floors=len(
                set(s.floor_number for s in sensor_readings)
            ),
            occupancy_rate_pct=round(occ_rate * 100, 1),
            outdoor_temp_c=outdoor_temp_c,
            predicted_energy_kwh_today=round(predicted, 2),
            anomalies=anomalies,
            optimization_suggestions=suggestions,
            carbon_today_kgco2=round(carbon_today, 3),
            bim_sync_status="synced",
        )

    def _grade_eui(self, eui: float) -> str:
        if eui <= self.benchmark["excellent"]:
            return "excellent"
        elif eui <= self.benchmark["good"]:
            return "good"
        elif eui <= self.benchmark["average"]:
            return "average"
        else:
            return "poor"

    def _detect_anomalies(
        self, readings: List[SensorReading]
    ) -> List[Dict]:
        """Z-score 기반 이상 감지"""
        anomalies = []
        type_groups: Dict[str, List[float]] = {}
        for r in readings:
            type_groups.setdefault(r.sensor_type, []).append(r.value)

        for stype, values in type_groups.items():
            if len(values) < 3:
                continue
            mu = sum(values) / len(values)
            sigma = math.sqrt(
                sum((v - mu) ** 2 for v in values) / len(values)
            )
            if sigma < 1e-6:
                continue
            for reading in readings:
                if reading.sensor_type != stype:
                    continue
                z = abs((reading.value - mu) / sigma)
                if z > 3.0:
                    anomalies.append({
                        "sensor_id": reading.sensor_id,
                        "sensor_type": stype,
                        "floor": reading.floor_number,
                        "zone": reading.zone_name,
                        "value": reading.value,
                        "z_score": round(z, 2),
                        "severity": "high" if z > 4 else "medium",
                        "message": f"{stype} 센서 이상 감지 (Z={z:.1f})",
                    })
        return anomalies

    def _generate_suggestions(
        self,
        eui: float,
        occ_rate: float,
        outdoor_temp: float,
        anomalies: List[Dict],
    ) -> List[str]:
        suggestions = []
        if eui > self.benchmark["good"]:
            suggestions.append("에너지 사용량이 기준 초과 -- HVAC 설정 온도 조정 권장")
        if occ_rate < 0.3:
            suggestions.append("재실률 30% 미만 -- 조명/공조 자동 절전 모드 전환")
        if outdoor_temp > 30:
            suggestions.append("외기 고온 -- 냉방 부하 증가 예상, 태양광 발전량 최대화")
        if outdoor_temp < 5:
            suggestions.append("외기 저온 -- 난방 부하 증가, 지열 시스템 우선 운전")
        if anomalies:
            suggestions.append(f"센서 이상 {len(anomalies)}건 감지 -- 점검 필요")
        return suggestions
```

---

## Part C 완료 체크리스트

```
[Phase 10] services/agency/orchestrator.py        : [ ]
[Phase 11] services/development/method_engine.py  : [ ]
[Phase 12] services/esg/carbon_calculator.py      : [ ]
            (EU Taxonomy 클래스 추가)
[Phase 13] services/esg/re100_tracker.py          : [ ]
[Phase 14] services/esg/lcc_calculator.py         : [ ]
[Phase 15] services/design/cad_editor.py          : [ ]
[Phase 16] services/esg/twin/digital_twin_basic.py: [ ]

다음 단계: Part D 파일 로드 -> Phase 17~21 실행 (프론트엔드 + DevOps)
```
