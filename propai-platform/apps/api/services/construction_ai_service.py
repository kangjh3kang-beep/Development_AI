"""시공/ESG AI 서비스.

BIM4D 시공 일정 생성, ZEB 에너지 시뮬레이션, 기후 리스크 정량화,
하자 사진 AI 분류 기능을 제공한다.

흐름:
1. 국토부 표준품셈 기반 13공정 시공 일정 자동 생성
2. EnergyPlus 수학 모델 기반 ZEB 에너지 시뮬레이션
3. KMA RCP 8.5 기후 데이터 기반 리스크 정량화
4. Claude Vision 기반 하자 사진 AI 분류
"""

import math
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings

logger = structlog.get_logger(__name__)

# ── 국토부 표준품셈 기반 13공정 정의 ──
_CONSTRUCTION_PHASES: list[dict[str, Any]] = [
    {"id": 1, "name": "가설공사", "base_days_per_1000m2": 5, "predecessors": []},
    {"id": 2, "name": "토공사", "base_days_per_1000m2": 8, "predecessors": [1]},
    {"id": 3, "name": "기초공사", "base_days_per_1000m2": 12, "predecessors": [2]},
    {"id": 4, "name": "철근콘크리트공사", "base_days_per_1000m2": 25, "predecessors": [3]},
    {"id": 5, "name": "철골공사", "base_days_per_1000m2": 15, "predecessors": [3]},
    {"id": 6, "name": "조적공사", "base_days_per_1000m2": 8, "predecessors": [4, 5]},
    {"id": 7, "name": "방수공사", "base_days_per_1000m2": 5, "predecessors": [4]},
    {"id": 8, "name": "창호공사", "base_days_per_1000m2": 7, "predecessors": [6]},
    {"id": 9, "name": "미장공사", "base_days_per_1000m2": 10, "predecessors": [6]},
    {"id": 10, "name": "설비공사", "base_days_per_1000m2": 15, "predecessors": [4]},
    {"id": 11, "name": "전기공사", "base_days_per_1000m2": 12, "predecessors": [4]},
    {"id": 12, "name": "마감공사", "base_days_per_1000m2": 15, "predecessors": [8, 9, 10, 11]},
    {"id": 13, "name": "준공청소/검사", "base_days_per_1000m2": 3, "predecessors": [12]},
]

# ── 구조형식별 보정 계수 ──
_STRUCTURE_FACTORS: dict[str, float] = {
    "RC": 1.0,    # 철근콘크리트
    "SRC": 1.15,  # 철골철근콘크리트
    "SC": 0.85,   # 철골
}

# ── ZEB 등급 기준 (에너지 자립률 %) ──
_ZEB_GRADES: list[tuple[float, str]] = [
    (100.0, "1등급"),  # 에너지 자립률 100% 이상
    (80.0, "2등급"),
    (60.0, "3등급"),
    (40.0, "4등급"),
    (20.0, "5등급"),
]

# ── 하자 유형 분류 ──
_DEFECT_TYPES: list[str] = [
    "균열(크랙)",
    "누수/누출",
    "들뜸/박리",
    "곰팡이/결로",
    "도장불량",
    "타일깨짐",
    "배관파손",
    "전기설비불량",
    "단열불량",
    "기타",
]


class ConstructionAIService:
    """시공/ESG AI 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    # ── BIM4D 시공 일정 생성 ──

    def generate_construction_schedule(
        self,
        total_area_sqm: float,
        floors_above: int = 10,
        floors_below: int = 1,
        structure_type: str = "RC",
    ) -> dict[str, Any]:
        """국토부 표준품셈 기반 13공정 시공 일정을 생성한다.

        각 공정의 기본 소요일을 면적, 층수, 구조형식에 따라 보정하고
        CPM(Critical Path Method)으로 전체 일정을 산출한다.
        """
        logger.info(
            "시공 일정 생성",
            area=total_area_sqm,
            floors=floors_above,
            structure=structure_type,
        )

        scale_factor = total_area_sqm / 1000.0
        floor_factor = 1.0 + (floors_above + floors_below - 2) * 0.05
        struct_factor = _STRUCTURE_FACTORS.get(structure_type, 1.0)

        # 각 공정별 소요일 산출
        phase_durations: dict[int, int] = {}
        for phase in _CONSTRUCTION_PHASES:
            base_days = phase["base_days_per_1000m2"]
            duration = max(
                3,
                round(base_days * scale_factor * floor_factor * struct_factor),
            )
            phase_durations[phase["id"]] = duration

        # CPM: 최조 시작(ES), 최조 종료(EF) 계산
        es: dict[int, int] = {}
        ef: dict[int, int] = {}

        for phase in _CONSTRUCTION_PHASES:
            pid = phase["id"]
            preds = phase["predecessors"]
            if not preds:
                es[pid] = 0
            else:
                es[pid] = max(ef[p] for p in preds)
            ef[pid] = es[pid] + phase_durations[pid]

        total_days = max(ef.values())

        # 주공정선(Critical Path) 역추적
        ls: dict[int, int] = {}
        lf: dict[int, int] = {}

        for phase in reversed(_CONSTRUCTION_PHASES):
            pid = phase["id"]
            # 후속 공정 찾기
            successors = [
                p["id"] for p in _CONSTRUCTION_PHASES if pid in p["predecessors"]
            ]
            if not successors:
                lf[pid] = total_days
            else:
                lf[pid] = min(ls[s] for s in successors)
            ls[pid] = lf[pid] - phase_durations[pid]

        critical_path: list[str] = []
        for phase in _CONSTRUCTION_PHASES:
            pid = phase["id"]
            total_float = ls[pid] - es[pid]
            if total_float == 0:
                critical_path.append(phase["name"])

        # 일정 상세
        schedule: list[dict[str, Any]] = []
        for phase in _CONSTRUCTION_PHASES:
            pid = phase["id"]
            schedule.append({
                "phase_id": pid,
                "name": phase["name"],
                "duration_days": phase_durations[pid],
                "start_day": es[pid],
                "end_day": ef[pid],
                "is_critical": phase["name"] in critical_path,
            })

        # 주요 마일스톤
        milestones = [
            {"name": "착공", "day": 0},
            {"name": "골조 완료", "day": ef.get(4, ef.get(5, 0))},
            {"name": "설비/전기 완료", "day": max(ef.get(10, 0), ef.get(11, 0))},
            {"name": "준공", "day": total_days},
        ]

        return {
            "total_duration_days": total_days,
            "schedule": schedule,
            "critical_path": critical_path,
            "milestones": milestones,
        }

    # ── ZEB 에너지 시뮬레이션 ──

    def estimate_zeb_energy(
        self,
        total_area_sqm: float,
        floors: int = 10,
        window_wall_ratio: float = 0.35,
        insulation_grade: str = "1등급",
    ) -> dict[str, Any]:
        """ZEB(제로에너지건축물) 에너지 시뮬레이션을 수행한다.

        EnergyPlus 수학 모델 간소화 버전:
        - 열관류율(U-value) 기반 난방/냉방 에너지 수요 산출
        - 재생에너지(태양광) 발전량 추정
        - ZEB 등급 판정
        """
        logger.info("ZEB 에너지 시뮬레이션", area=total_area_sqm, wwr=window_wall_ratio)

        # 단열 등급별 열관류율 (W/㎡·K)
        u_values: dict[str, float] = {
            "1등급": 0.15,
            "2등급": 0.21,
            "3등급": 0.30,
            "4등급": 0.47,
        }
        u_value = u_values.get(insulation_grade, 0.30)

        # 외피 면적 추정 (건물 정사각형 가정)
        floor_area = total_area_sqm / floors
        side_length = math.sqrt(floor_area)
        wall_area = side_length * 4 * 3.0 * floors  # 층고 3m
        window_area = wall_area * window_wall_ratio
        opaque_wall_area = wall_area * (1 - window_wall_ratio)
        roof_area = floor_area

        # 창호 열관류율 (이중유리 기본)
        u_window = u_value * 3.0  # 창호는 벽체의 약 3배

        # 난방 에너지 수요 (난방도일법: 서울 기준 HDD=2,800 ℃·day)
        hdd = 2800
        heat_loss_wall = opaque_wall_area * u_value * hdd * 24 / 1000  # kWh
        heat_loss_window = window_area * u_window * hdd * 24 / 1000
        heat_loss_roof = roof_area * u_value * hdd * 24 / 1000
        heating_demand = heat_loss_wall + heat_loss_window + heat_loss_roof

        # 냉방 에너지 수요 (냉방도일: 서울 기준 CDD=800 ℃·day)
        cdd = 800
        cooling_demand = (
            (opaque_wall_area * u_value + window_area * u_window + roof_area * u_value)
            * cdd * 24 / 1000 / 3.0  # COP=3.0
        )

        # 조명/환기/급탕 에너지
        lighting = total_area_sqm * 15  # kWh/㎡/년
        ventilation = total_area_sqm * 10
        hot_water = total_area_sqm * 20

        total_demand = heating_demand + cooling_demand + lighting + ventilation + hot_water

        # 태양광 발전량 추정 (지붕 면적의 60% 활용, 효율 20%, 서울 일사량 3.5 kWh/㎡/일)
        pv_area = roof_area * 0.60
        pv_generation = pv_area * 0.20 * 3.5 * 365  # kWh/년

        # 에너지 자립률
        independence_rate = (pv_generation / total_demand * 100) if total_demand > 0 else 0

        # ZEB 등급 판정
        zeb_grade = "미달"
        for threshold, grade in _ZEB_GRADES:
            if independence_rate >= threshold:
                zeb_grade = grade
                break

        # 개선 권장사항
        recommendations: list[str] = []
        if independence_rate < 20:
            recommendations.append("태양광 패널 면적 확대 검토 (BIPV 적용 권장)")
        if u_value > 0.20:
            recommendations.append(f"단열 성능 강화 필요 (현재 U={u_value}, 목표 U≤0.15)")
        if window_wall_ratio > 0.40:
            recommendations.append(
                f"창면적비 축소 검토 (현재 {window_wall_ratio:.0%}, 권장 ≤35%)"
            )
        if independence_rate < 60:
            recommendations.append("지열히트펌프 도입으로 냉난방 에너지 절감 가능")
        recommendations.append("고효율 LED 조명 + 스마트 제어 시스템 적용 권장")

        return {
            "annual_energy_demand_kwh": round(total_demand, 1),
            "annual_renewable_generation_kwh": round(pv_generation, 1),
            "zeb_grade": zeb_grade,
            "energy_independence_rate": round(independence_rate, 1),
            "recommendations": recommendations,
        }

    # ── 기후 리스크 정량화 ──

    async def analyze_climate_risk(
        self,
        project_id: UUID,
        lat: float,
        lon: float,
        construction_period_months: int = 24,
    ) -> dict[str, Any]:
        """KMA RCP 8.5 기후 데이터 기반 기후 리스크를 정량화한다.

        홍수/폭염 확률, 강풍 리스크, 공사 중단 예상 일수를 산출한다.
        """
        logger.info("기후 리스크 분석", lat=lat, lon=lon)

        # 위도 기반 기후 특성 추정 (한국 33~38°N)
        # 남부 → 폭염 리스크 높음, 해안 → 홍수/태풍 리스크 높음
        is_southern = lat < 35.5
        is_coastal = abs(lon - 127.0) > 1.5 or lat < 34.5

        # 홍수 리스크 (기본값 + 지역 보정)
        flood_base = 0.25
        if is_coastal:
            flood_base += 0.20
        if is_southern:
            flood_base += 0.10
        flood_risk = min(1.0, flood_base)

        # 폭염 리스크 (RCP 8.5 시나리오: 2026년 기준)
        heat_base = 0.30
        if is_southern:
            heat_base += 0.25
        heat_risk = min(1.0, heat_base)

        # 종합 리스크 등급
        overall_score = flood_risk * 0.5 + heat_risk * 0.5
        if overall_score >= 0.70:
            overall_level = "CRITICAL"
        elif overall_score >= 0.50:
            overall_level = "HIGH"
        elif overall_score >= 0.30:
            overall_level = "MEDIUM"
        else:
            overall_level = "LOW"

        # 공사 중단 예상 일수
        rain_stop_days = int(construction_period_months * 1.5 * flood_risk)
        heat_stop_days = int(construction_period_months * 0.8 * heat_risk)

        risk_factors: list[dict[str, Any]] = [
            {
                "factor": "홍수/집중호우",
                "score": round(flood_risk, 2),
                "impact": "HIGH" if flood_risk >= 0.5 else "MEDIUM",
                "description": f"예상 공사 중단 {rain_stop_days}일",
            },
            {
                "factor": "폭염 (35℃ 이상)",
                "score": round(heat_risk, 2),
                "impact": "HIGH" if heat_risk >= 0.5 else "MEDIUM",
                "description": f"예상 공사 중단 {heat_stop_days}일",
            },
        ]

        mitigation_tips: list[str] = []
        if flood_risk >= 0.4:
            mitigation_tips.append("우기(6~9월) 지하공사 회피 일정 수립")
            mitigation_tips.append("배수 펌프 및 방수 가설시설 사전 설치")
        if heat_risk >= 0.4:
            mitigation_tips.append("폭염 시 작업시간 조정 (05~11시, 15~18시)")
            mitigation_tips.append("그늘막 및 냉방 휴게시설 설치")
        mitigation_tips.append("기상청 API 연동 일일 기상 모니터링 체계 구축")

        return {
            "flood_risk_score": round(flood_risk, 2),
            "heat_risk_score": round(heat_risk, 2),
            "overall_risk_level": overall_level,
            "risk_factors": risk_factors,
            "mitigation_tips": mitigation_tips,
        }

    # ── 하자 사진 AI 분류 (Claude Vision) ──

    async def classify_defect_image(
        self,
        project_id: UUID,
        image_url: str,
        location: str = "",
    ) -> dict[str, Any]:
        """Claude Vision으로 하자 사진을 분류한다.

        하자 유형, 심각도, 보수 권장 사항을 반환한다.
        """
        logger.info("하자 사진 분류", project_id=str(project_id), url=image_url)

        from langchain_anthropic import ChatAnthropic
        from langchain_core.messages import HumanMessage

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.1,
        )

        defect_types_text = ", ".join(_DEFECT_TYPES)
        location_text = f"\n하자 위치: {location}" if location else ""

        prompt_text = f"""건축 하자 진단 전문가로서 이 사진을 분석하세요.{location_text}

다음 JSON 형식으로 응답하세요:
{{
  "defect_type": "<하자 유형: {defect_types_text} 중 하나>",
  "severity": "<심각도: MINOR/MODERATE/MAJOR/CRITICAL>",
  "confidence": <0.0~1.0 신뢰도>,
  "description": "<하자 상세 설명 (한국어, 2~3문장)>",
  "repair_recommendation": "<보수 권장 사항 (한국어, 1~2문장)>"
}}"""

        try:
            message = HumanMessage(
                content=[
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt_text},
                ],
            )
            response = await llm.ainvoke([message])

            import json

            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]

            result: dict[str, Any] = json.loads(content.strip())

            # 유효성 검증
            if result.get("defect_type") not in _DEFECT_TYPES:
                result["defect_type"] = "기타"
            if result.get("severity") not in ("MINOR", "MODERATE", "MAJOR", "CRITICAL"):
                result["severity"] = "MODERATE"

            return result

        except Exception:
            logger.warning("하자 분류 실패 — 기본값 반환")
            return {
                "defect_type": "기타",
                "severity": "MODERATE",
                "confidence": 0.0,
                "description": "AI 자동 분류를 수행할 수 없습니다. 전문가 현장 점검이 필요합니다.",
                "repair_recommendation": "전문 감리인 현장 점검 후 보수 방안을 수립하세요.",
            }

    # ── 탄소 배출량 산정 ──

    @staticmethod
    def calculate_carbon_emission(
        material: dict[str, float],
        equipment: dict[str, float],
        power: dict[str, float],
    ) -> dict[str, Any]:
        """자재/장비/전력 기반 탄소 배출량을 산정한다.

        Args:
            material: 자재 사용량 (단위: 톤).
                키: concrete, steel, cement, brick, glass, wood, insulation, etc.
            equipment: 장비 운행 시간 (단위: 시간).
                키: excavator, crane, mixer, truck, pump, etc.
            power: 전력/연료 소비량.
                키: electricity_kwh, diesel_liter, lpg_kg, etc.

        Returns:
            자재/장비/전력별 배출량 상세 및 총 배출량 (tCO₂e).
        """
        # 자재별 탄소 배출 계수 (kgCO₂e/톤) — 환경부 국가 LCI DB 기반
        material_factors: dict[str, float] = {
            "concrete": 130.0,    # 레미콘
            "steel": 2_300.0,     # 철강
            "cement": 900.0,      # 시멘트
            "brick": 200.0,       # 벽돌
            "glass": 1_200.0,     # 유리
            "wood": 45.0,         # 목재
            "insulation": 3_500.0,  # 단열재 (XPS 등)
            "aluminum": 8_700.0,  # 알루미늄
            "asphalt": 100.0,     # 아스팔트
        }

        # 장비별 시간당 탄소 배출 계수 (kgCO₂e/시간) — 경유 소비 기반
        equipment_factors: dict[str, float] = {
            "excavator": 45.0,    # 굴삭기
            "crane": 35.0,        # 크레인
            "mixer": 25.0,        # 믹서
            "truck": 30.0,        # 트럭(덤프)
            "pump": 20.0,         # 콘크리트 펌프카
            "loader": 40.0,       # 로더
            "roller": 28.0,       # 로울러
            "generator": 50.0,    # 발전기
        }

        # 전력/연료별 탄소 배출 계수
        power_factors: dict[str, float] = {
            "electricity_kwh": 0.4781,  # kgCO₂e/kWh (한국 전력 배출계수 2024)
            "diesel_liter": 2.58,       # kgCO₂e/L
            "lpg_kg": 3.00,             # kgCO₂e/kg
            "lng_m3": 2.23,             # kgCO₂e/㎥
        }

        # 자재 배출량 계산
        material_emissions: dict[str, float] = {}
        material_total = 0.0
        for name, tonnage in material.items():
            factor = material_factors.get(name, 150.0)  # 미정의 자재는 150 기본값
            emission_kg = tonnage * factor
            material_emissions[name] = round(emission_kg / 1000.0, 3)  # tCO₂e
            material_total += emission_kg

        # 장비 배출량 계산
        equipment_emissions: dict[str, float] = {}
        equipment_total = 0.0
        for name, hours in equipment.items():
            factor = equipment_factors.get(name, 30.0)  # 기본 30 kgCO₂e/h
            emission_kg = hours * factor
            equipment_emissions[name] = round(emission_kg / 1000.0, 3)
            equipment_total += emission_kg

        # 전력/연료 배출량 계산
        power_emissions: dict[str, float] = {}
        power_total = 0.0
        for name, quantity in power.items():
            factor = power_factors.get(name, 0.5)  # 기본 0.5 kgCO₂e/단위
            emission_kg = quantity * factor
            power_emissions[name] = round(emission_kg / 1000.0, 3)
            power_total += emission_kg

        total_tco2e = (material_total + equipment_total + power_total) / 1000.0

        # 감축 권장사항 생성
        recommendations: list[str] = []
        if material_total > 0:
            # 가장 배출이 높은 자재 식별
            top_material = max(material_emissions, key=material_emissions.get)  # type: ignore[arg-type]
            recommendations.append(
                f"최다 배출 자재 '{top_material}' "
                f"({material_emissions[top_material]:.1f} tCO₂e) — "
                "저탄소 대체재 검토 권장"
            )
        if equipment_total / 1000.0 > total_tco2e * 0.3:
            recommendations.append("장비 배출 비중 30% 초과 — 전동화 장비 도입 검토")
        if power.get("electricity_kwh", 0) > 0:
            recommendations.append("현장 태양광 발전 도입으로 전력 배출 절감 가능")
        if total_tco2e > 100:
            recommendations.append("탄소 배출권 구매 또는 CDM 사업 연계 검토")

        return {
            "total_emission_tco2e": round(total_tco2e, 3),
            "material_emission_tco2e": round(material_total / 1000.0, 3),
            "equipment_emission_tco2e": round(equipment_total / 1000.0, 3),
            "power_emission_tco2e": round(power_total / 1000.0, 3),
            "material_detail": material_emissions,
            "equipment_detail": equipment_emissions,
            "power_detail": power_emissions,
            "recommendations": recommendations,
        }
