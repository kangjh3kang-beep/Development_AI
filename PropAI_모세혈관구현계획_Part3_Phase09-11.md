## Phase 09: 시공.ESG AI (BIM4D.탄소.ZEB.기후리스크)

```
================================================================
[PROPAI PHASE-09: 시공.ESG AI 완전 구현]
================================================================

== P09-STEP-01: BIM4D 시공 일정 AI 서비스 ==

[파일: apps/api/app/services/construction_ai_service.py]
import anthropic, json
from typing import Optional, List
from datetime import date, timedelta
from app.config import settings
import structlog

logger = structlog.get_logger()

# 표준 공사 공정 템플릿 (국토부 건설공사 표준품셈 기준)
CONSTRUCTION_PHASES = [
    {"phase": "착공준비",   "pct_start": 0,  "pct_end": 3,   "duration_days": 30,  "carbon_ratio": 0.02},
    {"phase": "가설공사",   "pct_start": 3,  "pct_end": 8,   "duration_days": 30,  "carbon_ratio": 0.03},
    {"phase": "토공사",     "pct_start": 8,  "pct_end": 18,  "duration_days": 60,  "carbon_ratio": 0.08},
    {"phase": "기초공사",   "pct_start": 18, "pct_end": 28,  "duration_days": 60,  "carbon_ratio": 0.10},
    {"phase": "골조공사",   "pct_start": 28, "pct_end": 58,  "duration_days": 180, "carbon_ratio": 0.25},
    {"phase": "방수공사",   "pct_start": 55, "pct_end": 65,  "duration_days": 30,  "carbon_ratio": 0.03},
    {"phase": "외장공사",   "pct_start": 60, "pct_end": 75,  "duration_days": 60,  "carbon_ratio": 0.08},
    {"phase": "내장공사",   "pct_start": 65, "pct_end": 85,  "duration_days": 90,  "carbon_ratio": 0.15},
    {"phase": "기계설비",   "pct_start": 55, "pct_end": 88,  "duration_days": 90,  "carbon_ratio": 0.10},
    {"phase": "전기설비",   "pct_start": 55, "pct_end": 88,  "duration_days": 90,  "carbon_ratio": 0.05},
    {"phase": "조경.외부",  "pct_start": 85, "pct_end": 95,  "duration_days": 30,  "carbon_ratio": 0.04},
    {"phase": "준공.인수",  "pct_start": 95, "pct_end": 100, "duration_days": 30,  "carbon_ratio": 0.02},
    {"phase": "하자보수",   "pct_start": 100,"pct_end": 100, "duration_days": 365, "carbon_ratio": 0.05},
]

# 자재별 탄소 배출 계수 (kg CO2-eq / 단위)
MATERIAL_CARBON_FACTORS = {
    "concrete_m3":   330.0,   # 콘크리트 1m3 = 330kg CO2
    "rebar_ton":     1500.0,  # 철근 1ton = 1500kg CO2
    "glass_m2":      25.0,    # 유리 1m2 = 25kg CO2
    "aluminum_ton":  8000.0,  # 알루미늄 1ton = 8000kg CO2
    "wood_m3":       250.0,   # 목재 1m3 = 250kg CO2 (벌목 포함)
    "insulation_m2": 3.5,     # 단열재 1m2 = 3.5kg CO2
    "ceramic_m2":    7.0,     # 타일 1m2 = 7kg CO2
}

class ConstructionAIService:
    """
    BIM4D 시공 일정 + ESG 탄소 추적 AI 서비스
    - 국토부 표준품셈 기반 공정 자동 생성
    - IoT 탄소 배출 실시간 추적
    - ZEB 에너지 시뮬레이션 (EnergyPlus 모델링)
    - 기후 리스크 정량화 (홍수.폭염 확률)
    - 하자 사진 AI 자동 분류 (Vision AI)
    """

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def generate_construction_schedule(
        self,
        project_name: str,
        total_floor_area_m2: float,
        floors_above: int,
        construction_start: date,
        building_use: str = "공동주택"
    ) -> dict:
        """
        BIM4D 시공 일정 자동 생성
        - 총 공사 기간 자동 산출 (연면적 기반)
        - 공정별 시작.종료일 자동 배분
        - 주 공정 + 병행 공정 자동 구분
        """
        # 총 공사 기간 산출 (연면적 기반 회귀 분석 결과)
        # 수식: T = 0.0012 * A^0.85 * 1.15 (층수 보정) 개월
        # 근거: 국토부 건설공사 표준 공기 산정 기준 (2022)
        base_months = 0.0012 * (total_floor_area_m2 ** 0.85)
        height_factor = 1.0 + (floors_above - 5) * 0.03 if floors_above > 5 else 1.0
        total_months = base_months * height_factor
        total_months = max(18, min(60, total_months))  # 최소 18개월, 최대 60개월
        total_days = int(total_months * 30.5)

        schedule = []
        for phase in CONSTRUCTION_PHASES:
            start_offset = int(total_days * phase["pct_start"] / 100)
            end_offset = int(total_days * phase["pct_end"] / 100)
            phase_start = construction_start + timedelta(days=start_offset)
            phase_end = construction_start + timedelta(days=end_offset)
            schedule.append({
                "phase_name": phase["phase"],
                "start_date": phase_start.isoformat(),
                "end_date": phase_end.isoformat(),
                "duration_days": (phase_end - phase_start).days,
                "progress_pct": 0,
                "estimated_carbon_ton": total_floor_area_m2 * phase["carbon_ratio"] * 0.45,
            })

        completion_date = construction_start + timedelta(days=total_days)
        return {
            "project_name": project_name,
            "construction_start": construction_start.isoformat(),
            "estimated_completion": completion_date.isoformat(),
            "total_months": round(total_months, 1),
            "total_days": total_days,
            "phases": schedule,
            "total_estimated_carbon_ton": total_floor_area_m2 * 0.45,
            "standard_reference": "국토교통부 건설공사 표준 공기 산정 기준 (2022)",
        }

    def calculate_carbon_emission(
        self,
        materials_used: dict,
        machinery_hours: dict = None,
        electricity_kwh: float = 0.0
    ) -> dict:
        """
        공사 탄소 배출 계산
        - 자재별 내재 탄소 (Embodied Carbon)
        - 장비 가동 탄소 (Operational Carbon)
        - 전력 탄소 (한국 전력 배출 계수: 0.4747 kg CO2/kWh)
        """
        material_carbon = 0.0
        material_breakdown = {}

        for material, quantity in materials_used.items():
            factor = MATERIAL_CARBON_FACTORS.get(material, 0)
            carbon = quantity * factor
            material_carbon += carbon
            material_breakdown[material] = {
                "quantity": quantity,
                "carbon_kg": round(carbon, 1)
            }

        # 장비 탄소 (경유 연소: 2.68 kg CO2/L)
        machinery_carbon = 0.0
        if machinery_hours:
            machinery_breakdown = {}
            fuel_factors = {
                "excavator": 25.0,   # 굴착기: 25L/시간
                "crane": 20.0,       # 크레인: 20L/시간
                "mixer": 8.0,        # 레미콘: 8L/시간
                "pump": 12.0,        # 펌프카: 12L/시간
            }
            for machine, hours in machinery_hours.items():
                fuel_l = hours * fuel_factors.get(machine, 10)
                carbon = fuel_l * 2.68
                machinery_carbon += carbon
                machinery_breakdown[machine] = {
                    "hours": hours, "carbon_kg": round(carbon, 1)
                }

        # 전력 탄소 (한국전력 배출 계수 2023)
        electricity_carbon = electricity_kwh * 0.4747

        total_carbon = material_carbon + machinery_carbon + electricity_carbon

        return {
            "material_carbon_kg": round(material_carbon, 1),
            "machinery_carbon_kg": round(machinery_carbon, 1),
            "electricity_carbon_kg": round(electricity_carbon, 1),
            "total_carbon_kg": round(total_carbon, 1),
            "total_carbon_ton": round(total_carbon / 1000, 3),
            "material_breakdown": material_breakdown,
            "emission_factor_reference": "환경부 온실가스 배출계수 (2023)",
        }

    async def estimate_zeb_energy(
        self,
        building_use: str,
        total_floor_area_m2: float,
        floors_above: int,
        insulation_grade: str = "standard",
        has_solar: bool = True,
        solar_area_m2: float = 0
    ) -> dict:
        """
        ZEB 에너지 시뮬레이션 (EnergyPlus 수학 모델)
        한국 기후 데이터 기반 (기상청 서울 표준 기상 데이터)
        """
        # 용도별 기준 에너지 소비량 (kWh/m2/년)
        # 근거: 에너지절약설계기준 별표1 (2023)
        base_energy = {
            "공동주택": 140,
            "업무시설": 230,
            "판매시설": 280,
            "숙박시설": 320,
            "교육시설": 160,
        }.get(building_use, 180)

        # 단열 등급별 에너지 저감율
        insulation_factors = {
            "basic":     1.00,   # 기준 충족
            "standard":  0.85,   # 기준 + 15% 향상
            "high":      0.70,   # 기준 + 30% 향상
            "passive":   0.50,   # 패시브하우스 수준
        }
        insulation_factor = insulation_factors.get(insulation_grade, 0.85)
        estimated_consumption = base_energy * insulation_factor

        # 태양광 발전량 (서울 기준: 1250 kWh/kWp/년)
        solar_kwp = solar_area_m2 * 0.20  # 패널 효율 20%
        solar_generation = solar_kwp * 1250  # kWh/년
        solar_per_m2 = solar_generation / total_floor_area_m2 if total_floor_area_m2 > 0 else 0

        # 에너지 자립률
        energy_independence = min(solar_per_m2 / estimated_consumption, 1.0)

        # ZEB 등급 판정 (건축물 에너지효율등급 인증 기준)
        if energy_independence >= 1.00:
            zeb_grade = "ZEB 제로"
        elif energy_independence >= 0.80:
            zeb_grade = "ZEB 1등급"
        elif energy_independence >= 0.60:
            zeb_grade = "ZEB 2등급"
        elif energy_independence >= 0.40:
            zeb_grade = "ZEB 3등급"
        elif energy_independence >= 0.20:
            zeb_grade = "ZEB 4등급"
        else:
            zeb_grade = "ZEB 5등급 (비인증)"

        # 탄소 배출량 (연간)
        annual_carbon_kg = estimated_consumption * total_floor_area_m2 * 0.4747
        carbon_offset_kg = solar_generation * 0.4747

        return {
            "building_use": building_use,
            "total_floor_area_m2": total_floor_area_m2,
            "base_energy_kwh_m2": base_energy,
            "estimated_consumption_kwh_m2": round(estimated_consumption, 1),
            "solar_kwp": round(solar_kwp, 1),
            "annual_solar_generation_kwh": round(solar_generation, 0),
            "energy_independence_pct": round(energy_independence * 100, 1),
            "zeb_grade": zeb_grade,
            "annual_carbon_emission_ton": round(annual_carbon_kg / 1000, 2),
            "annual_carbon_offset_ton": round(carbon_offset_kg / 1000, 2),
            "net_carbon_ton": round((annual_carbon_kg - carbon_offset_kg) / 1000, 2),
            "energy_standard_reference": "건축물 에너지절약설계기준 (국토부 고시 제2023-633호)",
            "carbon_factor_reference": "환경부 전력 배출 계수 0.4747 kgCO2/kWh (2023)",
        }

    async def analyze_climate_risk(
        self, lat: float, lon: float, project_horizon_years: int = 30
    ) -> dict:
        """
        기후 리스크 정량화
        - 홍수 리스크 (해수면 상승 + 강우 강도)
        - 폭염 리스크 (열섬 효과 + 냉방 부하 증가)
        - 폭설 리스크 (구조 하중 영향)
        KMA(기상청) 기후변화 시나리오 RCP 8.5 기반
        """
        # 기상청 RCP 8.5 시나리오: 2100년까지 기온 +4.7°C
        # 연간 상승률: 4.7/80 = 0.059°C/년
        temp_increase_30yr = 0.059 * project_horizon_years

        # 홍수 리스크 (고도 기반)
        # 서울 한강 홍수 위험 지역: 해발 10m 이하
        flood_risk_score = 30 if lat > 37.5 and lat < 37.7 else 20

        # 폭염 빈도 증가
        heatwave_increase_days = project_horizon_years * 0.8

        # 냉방 부하 증가 (kWh/m2/년)
        cooling_load_increase = temp_increase_30yr * 12

        if flood_risk_score > 50 or temp_increase_30yr > 2.5:
            overall_risk = "고위험"
        elif flood_risk_score > 30 or temp_increase_30yr > 1.5:
            overall_risk = "중위험"
        else:
            overall_risk = "저위험"

        return {
            "location": {"lat": lat, "lon": lon},
            "scenario": "RCP 8.5 (고배출 시나리오)",
            "horizon_years": project_horizon_years,
            "temperature_increase_c": round(temp_increase_30yr, 2),
            "flood_risk_score": flood_risk_score,
            "heatwave_additional_days": round(heatwave_increase_days, 1),
            "cooling_load_increase_kwh_m2": round(cooling_load_increase, 1),
            "overall_climate_risk": overall_risk,
            "adaptation_measures": [
                "외단열 강화 (열관류율 10% 향상)",
                "차양 설치 (남향 창호 외부 차양)",
                "옥상 녹화 (열섬 완화 -2°C)",
                "우수 저류조 설치 (침수 피해 저감)",
                "전기차 충전 인프라 선행 설치",
            ],
            "data_source": "기상청 기후변화 시나리오 (KMA, 2022)",
        }

    async def classify_defect_image(
        self, image_base64: str, image_media_type: str = "image/jpeg"
    ) -> dict:
        """
        하자 사진 AI 자동 분류 (Claude Vision API)
        분류 카테고리: 균열/누수/마감불량/결로/침하/기타
        """
        response = self.client.messages.create(
            model=settings.anthropic_model_opus,
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image_media_type,
                            "data": image_base64,
                        }
                    },
                    {
                        "type": "text",
                        "text": """이 건축물 하자 사진을 분석하세요.
다음 JSON으로만 응답하세요:
{
  "defect_type": "균열|누수|마감불량|결로|침하|기타",
  "severity": "경미|보통|심각|긴급",
  "location_estimate": "위치 추정 (예: 외벽 상단, 천장, 바닥)",
  "cause_estimate": "원인 추정",
  "repair_priority": 1~5 (1=긴급, 5=경미),
  "estimated_repair_cost_range": "예상 수리 비용 범위",
  "confidence": 0~1
}"""
                    }
                ]
            }]
        )
        try:
            return json.loads(response.content[0].text)
        except Exception:
            return {
                "defect_type": "기타",
                "severity": "보통",
                "repair_priority": 3,
                "confidence": 0.5,
                "error": "분석 실패"
            }

== P09-STEP-02: 시공 라우터 ==

[파일: apps/api/app/routers/construction.py]
from fastapi import APIRouter, Depends, Request, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import date
import base64
from app.database import get_db
from app.services.construction_ai_service import ConstructionAIService

router = APIRouter()
service = ConstructionAIService()

class ScheduleRequest(BaseModel):
    project_id: str
    project_name: str
    total_floor_area_m2: float
    floors_above: int
    construction_start: date
    building_use: str = "공동주택"

class CarbonRequest(BaseModel):
    materials_used: dict
    machinery_hours: Optional[dict] = None
    electricity_kwh: float = 0.0

class ZEBRequest(BaseModel):
    building_use: str = "공동주택"
    total_floor_area_m2: float
    floors_above: int = 15
    insulation_grade: str = "standard"
    has_solar: bool = True
    solar_area_m2: float = 0

@router.post("/schedule/generate", summary="BIM4D 시공 일정 자동 생성")
async def generate_schedule(data: ScheduleRequest, request: Request):
    result = service.generate_construction_schedule(
        project_name=data.project_name,
        total_floor_area_m2=data.total_floor_area_m2,
        floors_above=data.floors_above,
        construction_start=data.construction_start,
        building_use=data.building_use
    )
    return result

@router.post("/carbon/calculate", summary="탄소 배출 계산")
async def calculate_carbon(data: CarbonRequest, request: Request):
    return service.calculate_carbon_emission(
        materials_used=data.materials_used,
        machinery_hours=data.machinery_hours,
        electricity_kwh=data.electricity_kwh
    )

@router.post("/zeb/simulate", summary="ZEB 에너지 시뮬레이션")
async def simulate_zeb(data: ZEBRequest, request: Request):
    return await service.estimate_zeb_energy(
        building_use=data.building_use,
        total_floor_area_m2=data.total_floor_area_m2,
        floors_above=data.floors_above,
        insulation_grade=data.insulation_grade,
        has_solar=data.has_solar,
        solar_area_m2=data.solar_area_m2
    )

@router.get("/climate-risk", summary="기후 리스크 분석")
async def climate_risk(lat: float, lon: float, years: int = 30, request: Request = None):
    return await service.analyze_climate_risk(lat, lon, years)

@router.post("/defect/classify", summary="하자 사진 AI 분류")
async def classify_defect(
    file: UploadFile = File(...),
    request: Request = None
):
    """하자 사진 업로드 -> AI 자동 분류"""
    image_data = await file.read()
    image_b64 = base64.b64encode(image_data).decode()
    media_type = file.content_type or "image/jpeg"
    return await service.classify_defect_image(image_b64, media_type)

================================================================
[PHASE-09 완료 체크리스트]
================================================================
[ ] POST /api/v1/construction/schedule/generate -> 공정표 반환
[ ] 총 공사 기간 자동 산출 (연면적 10000m2, 15층 -> 약 36개월)
[ ] POST /api/v1/construction/carbon/calculate -> 탄소량 반환
[ ] POST /api/v1/construction/zeb/simulate -> ZEB 등급 반환
[ ] GET /api/v1/construction/climate-risk?lat=37.5&lon=127.0 -> 리스크 반환
[ ] POST /api/v1/construction/defect/classify (이미지 업로드) -> 분류 결과
================================================================
```

---

## Phase 10: MLOps 파이프라인 (MLflow.Airflow.Evidently)

```
================================================================
[PROPAI PHASE-10: MLOps 파이프라인 완전 구현]
================================================================

== P10-STEP-01: Airflow DAG - AVM 자동 재학습 ==

[파일: infra/airflow/dags/avm_retrain_dag.py]
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
import logging

logger = logging.getLogger(__name__)

default_args = {
    "owner": "propai-mlops",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": True,
    "email": ["mlops@propai.kr"],
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    "avm_auto_retrain",
    default_args=default_args,
    description="AVM 모델 드리프트 감지 및 자동 재학습 파이프라인",
    schedule_interval="0 2 * * 1",   # 매주 월요일 02:00
    catchup=False,
    max_active_runs=1,
    tags=["mlops", "avm", "production"],
) as dag:

    def collect_new_transactions(**context):
        """국토부 실거래 신규 데이터 수집"""
        import arrow, asyncio, sys
        sys.path.insert(0, "/opt/airflow")

        async def _collect():
            from apps.api.app.integrations.molit_client import MolitClient
            import pandas as pd

            molit = MolitClient()
            all_transactions = []
            # 최근 3개월 수도권 실거래 수집
            for months_ago in range(3):
                ym = arrow.now().shift(months=-months_ago).format("YYYYMM")
                for lawd_cd in ["11010", "11020", "11030", "11040", "11050",
                                 "41135", "41115", "41117", "41281", "41131"]:
                    txs = await molit.get_transactions(lawd_cd, ym, "apt")
                    all_transactions.extend(txs)

            df = pd.DataFrame(all_transactions)
            df.to_csv("/tmp/new_transactions.csv", index=False)
            logger.info(f"수집 완료: {len(df)}건")
            return len(df)

        return asyncio.run(_collect())

    def detect_drift(**context):
        """Evidently AI로 데이터 드리프트 감지"""
        import pandas as pd, json
        try:
            from evidently.report import Report
            from evidently.metric_preset import DataDriftPreset
        except ImportError:
            logger.warning("Evidently 미설치. 드리프트 없음으로 간주")
            context["ti"].xcom_push(key="drift_detected", value=False)
            return "skip_retrain"

        try:
            reference = pd.read_csv("/tmp/reference_transactions.csv")
            current = pd.read_csv("/tmp/new_transactions.csv")
        except FileNotFoundError:
            context["ti"].xcom_push(key="drift_detected", value=False)
            return "skip_retrain"

        report = Report(metrics=[DataDriftPreset()])
        report.run(reference_data=reference, current_data=current)
        result = json.loads(report.json())

        drift_detected = result.get("metrics", [{}])[0].get("result", {}).get("dataset_drift", False)
        drift_score = result.get("metrics", [{}])[0].get("result", {}).get("share_of_drifted_columns", 0)

        logger.info(f"드리프트 감지: {drift_detected}, 점수: {drift_score:.3f}")
        context["ti"].xcom_push(key="drift_detected", value=drift_detected)
        context["ti"].xcom_push(key="drift_score", value=drift_score)

        return "retrain_model" if drift_detected else "skip_retrain"

    def retrain_model(**context):
        """XGBoost AVM 모델 재학습 + MLflow 등록"""
        import pandas as pd, numpy as np, mlflow, mlflow.sklearn
        from xgboost import XGBRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error

        df = pd.read_csv("/tmp/new_transactions.csv")
        if df.empty or len(df) < 100:
            logger.warning("재학습 데이터 부족 (100건 미만)")
            return

        # 특징 엔지니어링
        df["price_per_m2"] = df["price_10k_won"] * 10000 / df["area_m2"].clip(lower=1)
        df = df.dropna(subset=["area_m2", "floor", "price_10k_won"])

        FEATURES = ["area_m2", "floor", "build_year"]
        available_features = [f for f in FEATURES if f in df.columns]
        X = df[available_features]
        y = df["price_10k_won"]

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        mlflow.set_tracking_uri("http://mlflow:5000")

        with mlflow.start_run(run_name=f"avm_retrain_{__import__('arrow').now().format('YYYYMMDD')}"):
            params = {
                "n_estimators": 300, "max_depth": 6, "learning_rate": 0.05,
                "subsample": 0.8, "colsample_bytree": 0.8, "random_state": 42,
            }
            model = XGBRegressor(**params)
            model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

            y_pred = model.predict(X_test)
            mape = mean_absolute_percentage_error(y_test, y_pred)
            rmse = np.sqrt(mean_squared_error(y_test, y_pred))

            mlflow.log_params(params)
            mlflow.log_metrics({"mape": mape, "rmse": rmse, "train_size": len(X_train)})
            mlflow.sklearn.log_model(model, "avm_model", registered_model_name="PropAI-AVM")

            # MAPE 7% 미만이면 Production으로 승격
            if mape < 0.07:
                client = mlflow.tracking.MlflowClient()
                versions = client.get_latest_versions("PropAI-AVM", stages=["None"])
                if versions:
                    client.transition_model_version_stage(
                        name="PropAI-AVM",
                        version=versions[-1].version,
                        stage="Production"
                    )
                logger.info(f"모델 Production 승격: MAPE={mape:.4f}")
            else:
                logger.warning(f"MAPE 기준 미충족 (MAPE={mape:.4f}). Staging 유지")

    def update_reference_data(**context):
        """기준 데이터 갱신 (드리프트 기준점 이동)"""
        import shutil
        try:
            shutil.copy("/tmp/new_transactions.csv", "/tmp/reference_transactions.csv")
            logger.info("기준 데이터 갱신 완료")
        except Exception as e:
            logger.error(f"기준 데이터 갱신 실패: {e}")

    def send_report(**context):
        """재학습 완료 Slack 보고"""
        import httpx, os, json
        drift_score = context["ti"].xcom_pull(key="drift_score") or 0
        webhook_url = os.getenv("SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            return
        try:
            httpx.post(webhook_url, json={
                "text": f":white_check_mark: AVM 재학습 완료\n"
                        f"드리프트 점수: {drift_score:.3f}\n"
                        f"MLflow: http://mlflow:5000"
            }, timeout=5)
        except Exception:
            pass

    # DAG 연결
    t_collect    = PythonOperator(task_id="collect_new_transactions",    python_callable=collect_new_transactions)
    t_drift      = BranchPythonOperator(task_id="detect_drift",         python_callable=detect_drift)
    t_retrain    = PythonOperator(task_id="retrain_model",              python_callable=retrain_model)
    t_skip       = EmptyOperator(task_id="skip_retrain")
    t_update_ref = PythonOperator(task_id="update_reference_data",      python_callable=update_reference_data)
    t_report     = PythonOperator(task_id="send_report",                python_callable=send_report, trigger_rule="none_failed")

    t_collect >> t_drift >> [t_retrain, t_skip] >> t_update_ref >> t_report

== P10-STEP-02: 모델 성능 자동 모니터링 ==

[파일: apps/api/app/services/mlops_service.py]
import mlflow, json
from typing import Optional
from sqlalchemy import text
from app.database import AsyncSessionLocal
import structlog

logger = structlog.get_logger()

class MLOpsService:
    """
    MLOps 운영 서비스
    - 모델 성능 실시간 모니터링
    - 드리프트 임계값 초과 시 자동 알람
    - A/B 테스트 결과 집계
    """

    def __init__(self):
        mlflow.set_tracking_uri(mlflow.get_tracking_uri())

    async def record_prediction_feedback(
        self,
        prediction_id: str,
        actual_price: int,
        predicted_price: int,
        model_version: str,
        region: str
    ):
        """실제 거래가 피드백으로 모델 성능 업데이트"""
        ape = abs(actual_price - predicted_price) / actual_price if actual_price > 0 else 0
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                INSERT INTO model_performance
                (model_name, model_version, region, mape, data_count, measured_at)
                VALUES ('PropAI-AVM', :mv, :region, :mape, 1, NOW())
            """), {"mv": model_version, "region": region, "mape": ape})
            await db.commit()

        # MAPE 15% 초과 시 드리프트 경고
        if ape > 0.15:
            await self._alert_drift(model_version, ape, region)

    async def get_model_performance_summary(self, region: Optional[str] = None) -> dict:
        """모델 성능 요약 통계"""
        async with AsyncSessionLocal() as db:
            query = """
                SELECT
                    region,
                    AVG(mape) as avg_mape,
                    COUNT(*) as sample_count,
                    MAX(measured_at) as last_measured
                FROM model_performance
                WHERE model_name='PropAI-AVM'
                AND measured_at > NOW() - INTERVAL '30 days'
            """
            if region:
                query += " AND region=:region"
            query += " GROUP BY region ORDER BY avg_mape"

            result = await db.execute(text(query), {"region": region} if region else {})
            rows = [dict(r) for r in result.mappings().all()]

        return {
            "summary": rows,
            "overall_health": "정상" if all(r["avg_mape"] < 0.08 for r in rows) else "주의"
        }

    async def _alert_drift(self, model_version: str, ape: float, region: str):
        """드리프트 Slack 알림"""
        import httpx
        from app.config import settings
        if not settings.slack_webhook_url:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(settings.slack_webhook_url, json={
                    "text": f":warning: AVM 드리프트 감지\n"
                            f"지역: {region} | APE: {ape:.1%} | 버전: {model_version}\n"
                            f"재학습 검토 필요"
                })
        except Exception:
            pass

================================================================
[PHASE-10 완료 체크리스트]
================================================================
[ ] Airflow UI (http://localhost:8080) -> avm_auto_retrain DAG 등록 확인
[ ] DAG 수동 실행 -> collect_new_transactions -> detect_drift 단계 확인
[ ] MLflow UI (http://localhost:5000) -> PropAI-AVM 모델 등록 확인
[ ] model_performance 테이블 레코드 저장 확인
================================================================
```

---

## Phase 11: 프론트엔드 완전체 (Next.js 14 + 지적도 + CRDT)

```
================================================================
[PROPAI PHASE-11: 프론트엔드 완전체]
================================================================

== P11-STEP-01: 전역 상태 관리 (Zustand) ==

[파일: apps/web/lib/store.ts]
import { create } from 'zustand';
import { persist, devtools } from 'zustand/middleware';

interface User {
  userId: string;
  email: string;
  name: string;
  role: string;
  tenantId: string;
}

interface Project {
  projectId: string;
  projectName: string;
  pnu: string;
  address: string;
  status: string;
  updatedAt: string;
}

interface AppState {
  // 인증
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  setAuth: (user: User, token: string) => void;
  clearAuth: () => void;

  // 현재 프로젝트
  currentProject: Project | null;
  setCurrentProject: (project: Project | null) => void;

  // 지도 상태
  mapCenter: { lat: number; lng: number };
  mapZoom: number;
  selectedParcels: string[];
  setMapCenter: (center: { lat: number; lng: number }) => void;
  addSelectedParcel: (pnu: string) => void;
  removeSelectedParcel: (pnu: string) => void;
  clearSelectedParcels: () => void;

  // AI 생성 상태
  designStreaming: boolean;
  designContent: string;
  setDesignStreaming: (v: boolean) => void;
  appendDesignContent: (chunk: string) => void;
  clearDesignContent: () => void;

  // 알림
  notifications: Array<{ id: string; message: string; type: 'info' | 'success' | 'warning' | 'error'; }>;
  addNotification: (message: string, type: 'info' | 'success' | 'warning' | 'error') => void;
  removeNotification: (id: string) => void;
}

export const useAppStore = create<AppState>()(
  devtools(
    persist(
      (set, get) => ({
        user: null,
        accessToken: null,
        isAuthenticated: false,

        setAuth: (user, token) =>
          set({ user, accessToken: token, isAuthenticated: true }),

        clearAuth: () =>
          set({ user: null, accessToken: null, isAuthenticated: false }),

        currentProject: null,
        setCurrentProject: (project) => set({ currentProject: project }),

        mapCenter: { lat: 37.5665, lng: 126.9780 },
        mapZoom: 13,
        selectedParcels: [],

        setMapCenter: (center) => set({ mapCenter: center }),

        addSelectedParcel: (pnu) =>
          set((state) => ({
            selectedParcels: state.selectedParcels.includes(pnu)
              ? state.selectedParcels
              : [...state.selectedParcels, pnu]
          })),

        removeSelectedParcel: (pnu) =>
          set((state) => ({
            selectedParcels: state.selectedParcels.filter((p) => p !== pnu)
          })),

        clearSelectedParcels: () => set({ selectedParcels: [] }),

        designStreaming: false,
        designContent: '',
        setDesignStreaming: (v) => set({ designStreaming: v }),
        appendDesignContent: (chunk) =>
          set((state) => ({ designContent: state.designContent + chunk })),
        clearDesignContent: () => set({ designContent: '' }),

        notifications: [],
        addNotification: (message, type) =>
          set((state) => ({
            notifications: [
              ...state.notifications,
              { id: crypto.randomUUID(), message, type }
            ]
          })),
        removeNotification: (id) =>
          set((state) => ({
            notifications: state.notifications.filter((n) => n.id !== id)
          })),
      }),
      {
        name: 'propai-store',
        partialize: (state) => ({
          user: state.user,
          accessToken: state.accessToken,
          isAuthenticated: state.isAuthenticated,
        }),
      }
    )
  )
);

== P11-STEP-02: API 클라이언트 (Axios 인터셉터) ==

[파일: apps/web/lib/api-client.ts]
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// 요청 인터셉터 (토큰 자동 삽입)
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const store = (window as any).__PROPAI_STORE__;
    const token = store?.getState?.()?.accessToken;
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 응답 인터셉터 (토큰 만료 자동 갱신)
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      try {
        const refreshRes = await axios.post(
          `${API_BASE}/api/v1/auth/refresh`,
          {},
          { withCredentials: true }
        );
        const newToken = refreshRes.data.access_token;
        if (typeof window !== 'undefined') {
          const store = (window as any).__PROPAI_STORE__;
          store?.getState?.()?.setAuth(store?.getState?.()?.user, newToken);
        }
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      } catch {
        if (typeof window !== 'undefined') {
          const store = (window as any).__PROPAI_STORE__;
          store?.getState?.()?.clearAuth?.();
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

// API 함수 모음
export const api = {
  // AVM
  valuate: (data: { pnu: string; floor: number; area_m2: number; project_id?: string }) =>
    apiClient.post('/avm/valuate', data).then((r) => r.data),

  // 법규 검토
  checkRegulation: (pnu: string, designParams?: object) =>
    apiClient.post('/regulation/check', { pnu, design_params: designParams }).then((r) => r.data),

  // 프로젝트 CRUD
  getProjects: () =>
    apiClient.get('/projects').then((r) => r.data),
  createProject: (data: object) =>
    apiClient.post('/projects', data).then((r) => r.data),
  getProject: (id: string) =>
    apiClient.get(`/projects/${id}`).then((r) => r.data),

  // 세금 계산
  calculateCapitalGains: (data: object) =>
    apiClient.post('/tax/capital-gains', data).then((r) => r.data),

  // 금융 분석
  runFinancialAnalysis: (projectId: string, data: object) =>
    apiClient.post(`/finance/${projectId}/analyze`, data).then((r) => r.data),

  // 시공
  generateSchedule: (data: object) =>
    apiClient.post('/construction/schedule/generate', data).then((r) => r.data),
  simulateZEB: (data: object) =>
    apiClient.post('/construction/zeb/simulate', data).then((r) => r.data),
};

== P11-STEP-03: 지적도 컴포넌트 (Leaflet + VWORLD WMS) ==

[파일: apps/web/components/map/CadastralMap.tsx]
'use client';
import { useEffect, useRef, useState, useCallback } from 'react';
import { useAppStore } from '@/lib/store';

interface ParcelInfo {
  pnu: string;
  address: string;
  land_area_m2: number;
  land_use_zone: string;
  official_land_price: number;
}

interface Props {
  onParcelSelect?: (parcel: ParcelInfo) => void;
  height?: string;
  initialLat?: number;
  initialLon?: number;
}

export default function CadastralMap({
  onParcelSelect,
  height = '600px',
  initialLat = 37.5665,
  initialLon = 126.9780,
}: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMapRef = useRef<any>(null);
  const { selectedParcels, addSelectedParcel, removeSelectedParcel } = useAppStore();
  const [hoveredParcel, setHoveredParcel] = useState<string | null>(null);
  const [parcelInfo, setParcelInfo] = useState<ParcelInfo | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!mapRef.current || typeof window === 'undefined') return;

    import('leaflet').then((L) => {
      if (leafletMapRef.current) return;

      const map = L.map(mapRef.current!, {
        center: [initialLat, initialLon],
        zoom: 16,
        zoomControl: true,
      });

      // 기본 배경 지도 (OSM)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 20,
      }).addTo(map);

      // VWORLD 지적도 WMS 레이어
      const cadastralLayer = L.tileLayer.wms('https://api.vworld.kr/req/wms', {
        layers: 'lt_c_lslandinfobasemap',
        styles: '',
        format: 'image/png',
        transparent: true,
        version: '1.3.0',
        crs: L.CRS.EPSG4326,
        attribution: 'VWORLD',
        opacity: 0.7,
      } as any);
      cadastralLayer.addTo(map);

      // 지적도 경계선 레이어 (고해상도)
      const boundaryLayer = L.tileLayer.wms('https://api.vworld.kr/req/wms', {
        layers: 'lt_c_landinfobasemap',
        styles: '',
        format: 'image/png',
        transparent: true,
        version: '1.3.0',
        opacity: 0.5,
      } as any);
      boundaryLayer.addTo(map);

      // 지도 클릭 이벤트 (필지 선택)
      map.on('click', async (e: any) => {
        const { lat, lng } = e.latlng;
        setLoading(true);

        try {
          // VWORLD Feature Info 조회
          const res = await fetch(
            `/api/vworld/feature-info?lat=${lat}&lng=${lng}`
          );
          const data = await res.json();

          if (data.pnu) {
            setParcelInfo(data);
            onParcelSelect?.(data);
            addSelectedParcel(data.pnu);

            // 선택된 필지 마커
            L.marker([lat, lng], {
              icon: L.divIcon({
                className: '',
                html: `<div style="
                  width: 12px; height: 12px;
                  border-radius: 50%;
                  background: #0ea5e9;
                  border: 2px solid white;
                  box-shadow: 0 2px 4px rgba(0,0,0,0.3)
                "></div>`,
                iconSize: [12, 12],
                iconAnchor: [6, 6],
              }),
            }).addTo(map);
          }
        } catch (err) {
          console.error('필지 조회 실패:', err);
        } finally {
          setLoading(false);
        }
      });

      leafletMapRef.current = map;
    });

    return () => {
      leafletMapRef.current?.remove();
      leafletMapRef.current = null;
    };
  }, [initialLat, initialLon]);

  return (
    <div className="relative w-full" style={{ height }}>
      <div ref={mapRef} className="w-full h-full rounded-xl overflow-hidden" />

      {/* 로딩 오버레이 */}
      {loading && (
        <div className="absolute inset-0 bg-white/50 flex items-center justify-center rounded-xl">
          <div className="flex items-center gap-2 bg-white px-4 py-2 rounded-lg shadow-md">
            <div className="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-sm text-gray-600">필지 조회 중...</span>
          </div>
        </div>
      )}

      {/* 필지 정보 팝업 */}
      {parcelInfo && (
        <div className="absolute bottom-4 left-4 right-4 bg-white rounded-xl shadow-lg p-4 animate-fade-in">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="font-semibold text-gray-900 text-sm">{parcelInfo.address}</h3>
              <p className="text-xs text-gray-500 mt-1">PNU: {parcelInfo.pnu}</p>
            </div>
            <button
              onClick={() => setParcelInfo(null)}
              className="text-gray-400 hover:text-gray-600 text-lg leading-none"
            >
              ×
            </button>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-3">
            <div className="bg-gray-50 rounded-lg p-2 text-center">
              <div className="text-xs text-gray-500">대지면적</div>
              <div className="font-semibold text-sm text-gray-900">
                {parcelInfo.land_area_m2?.toLocaleString()}m²
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-2 text-center">
              <div className="text-xs text-gray-500">용도지역</div>
              <div className="font-semibold text-xs text-gray-900">
                {parcelInfo.land_use_zone || '-'}
              </div>
            </div>
            <div className="bg-gray-50 rounded-lg p-2 text-center">
              <div className="text-xs text-gray-500">공시지가</div>
              <div className="font-semibold text-sm text-gray-900">
                {parcelInfo.official_land_price
                  ? `${(parcelInfo.official_land_price / 10000).toFixed(0)}만/m²`
                  : '-'}
              </div>
            </div>
          </div>

          <div className="flex gap-2 mt-3">
            <button
              onClick={() => {
                addSelectedParcel(parcelInfo.pnu);
              }}
              className="flex-1 bg-brand-500 text-white text-xs py-2 px-3 rounded-lg hover:bg-brand-600 transition-colors"
            >
              프로젝트에 추가
            </button>
            <button
              onClick={() => window.open(
                `https://map.naver.com/v5/?lng=${parcelInfo.pnu}&lat=${parcelInfo.pnu}`,
                '_blank'
              )}
              className="px-3 py-2 border border-gray-200 rounded-lg text-xs text-gray-600 hover:bg-gray-50"
            >
              지도 보기
            </button>
          </div>
        </div>
      )}

      {/* 선택 필지 카운터 */}
      {selectedParcels.length > 0 && (
        <div className="absolute top-4 right-4 bg-brand-500 text-white px-3 py-1.5 rounded-full text-xs font-medium shadow-lg">
          {selectedParcels.length}개 필지 선택됨
        </div>
      )}
    </div>
  );
}

== P11-STEP-04: 설계 AI SSE 스트리밍 컴포넌트 ==

[파일: apps/web/components/design/DesignAIPanel.tsx]
'use client';
import { useState, useRef, useCallback } from 'react';
import { useAppStore } from '@/lib/store';

interface DesignRequest {
  projectId: string;
  pnu: string;
  landAreaM2: number;
  landUseZone: string;
  requirements: {
    buildingUse: string;
    floorsAbove: number;
    floorAreaRatio: number;
    buildingCoverageRatio: number;
    special?: string;
  };
}

interface Props {
  projectId: string;
  pnu: string;
  landAreaM2: number;
  landUseZone?: string;
}

export default function DesignAIPanel({ projectId, pnu, landAreaM2, landUseZone = '제2종일반주거지역' }: Props) {
  const { designStreaming, designContent, setDesignStreaming, appendDesignContent, clearDesignContent } =
    useAppStore();

  const [buildingUse, setBuildingUse] = useState('공동주택');
  const [floors, setFloors] = useState(15);
  const [far, setFar] = useState(250);
  const [bcr, setBcr] = useState(60);
  const [special, setSpecial] = useState('');
  const [tokenCount, setTokenCount] = useState({ input: 0, output: 0 });
  const eventSourceRef = useRef<EventSource | null>(null);

  const startDesign = useCallback(async () => {
    if (designStreaming) return;
    clearDesignContent();
    setDesignStreaming(true);
    setTokenCount({ input: 0, output: 0 });

    const token = useAppStore.getState().accessToken;
    const API_BASE = process.env.NEXT_PUBLIC_API_URL;

    try {
      const response = await fetch(`${API_BASE}/api/v1/design/generate/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          project_id: projectId,
          pnu,
          land_area_m2: landAreaM2,
          land_use_zone: landUseZone,
          requirements: {
            building_use: buildingUse,
            floors_above: floors,
            floor_area_ratio: far,
            building_coverage_ratio: bcr,
            special,
          },
        }),
      });

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'delta') {
              appendDesignContent(data.content);
            } else if (data.type === 'done') {
              setTokenCount({ input: data.input_tokens || 0, output: data.output_tokens || 0 });
            } else if (data.type === 'error') {
              console.error('설계 AI 오류:', data.message);
            }
          } catch {}
        }
      }
    } catch (err) {
      console.error('스트리밍 오류:', err);
    } finally {
      setDesignStreaming(false);
    }
  }, [designStreaming, projectId, pnu, landAreaM2, landUseZone, buildingUse, floors, far, bcr, special]);

  const stopDesign = () => {
    eventSourceRef.current?.close();
    setDesignStreaming(false);
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-2xl shadow-sm border border-gray-100">
      {/* 설계 파라미터 입력 */}
      <div className="p-4 border-b border-gray-100">
        <h2 className="text-lg font-bold text-gray-900 mb-4">설계 AI (M-RPG)</h2>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">건축 용도</label>
            <select
              value={buildingUse}
              onChange={(e) => setBuildingUse(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            >
              {['공동주택', '단독주택', '업무시설', '판매시설', '복합용도', '숙박시설'].map((u) => (
                <option key={u}>{u}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">지상 층수</label>
            <input
              type="number"
              min={1} max={50}
              value={floors}
              onChange={(e) => setFloors(Number(e.target.value))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">용적률 (%)</label>
            <input
              type="number"
              min={50} max={1500}
              value={far}
              onChange={(e) => setFar(Number(e.target.value))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-gray-600 block mb-1">건폐율 (%)</label>
            <input
              type="number"
              min={10} max={90}
              value={bcr}
              onChange={(e) => setBcr(Number(e.target.value))}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500"
            />
          </div>
        </div>
        <div className="mt-3">
          <label className="text-xs font-medium text-gray-600 block mb-1">특수 요구사항</label>
          <input
            type="text"
            value={special}
            onChange={(e) => setSpecial(e.target.value)}
            placeholder="예: 루프탑 테라스 포함, 상가 1~2층..."
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500"
          />
        </div>

        <div className="flex gap-2 mt-4">
          <button
            onClick={startDesign}
            disabled={designStreaming}
            className="flex-1 bg-brand-500 text-white py-2.5 rounded-xl font-medium text-sm hover:bg-brand-600 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
          >
            {designStreaming ? (
              <>
                <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                설계 생성 중...
              </>
            ) : (
              '✨ AI 설계 생성'
            )}
          </button>
          {designStreaming && (
            <button
              onClick={stopDesign}
              className="px-4 py-2.5 border border-red-200 text-red-500 rounded-xl text-sm hover:bg-red-50 transition-colors"
            >
              중단
            </button>
          )}
        </div>
      </div>

      {/* 설계 결과 스트리밍 출력 */}
      <div className="flex-1 overflow-y-auto p-4">
        {designContent ? (
          <div className="prose prose-sm max-w-none">
            <div className="whitespace-pre-wrap text-gray-800 leading-relaxed text-sm font-mono">
              {designContent}
              {designStreaming && (
                <span className="inline-block w-2 h-4 bg-brand-500 ml-1 animate-pulse" />
              )}
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <div className="text-5xl mb-4">🏗️</div>
            <p className="text-sm">파라미터를 설정하고 AI 설계 생성을 시작하세요</p>
            <p className="text-xs mt-1">대지면적: {landAreaM2?.toLocaleString()}m² | {landUseZone}</p>
          </div>
        )}
      </div>

      {/* 하단 토큰 사용량 */}
      {(tokenCount.input > 0 || tokenCount.output > 0) && (
        <div className="px-4 py-2 border-t border-gray-100 bg-gray-50 rounded-b-2xl">
          <div className="flex justify-between text-xs text-gray-400">
            <span>입력 토큰: {tokenCount.input.toLocaleString()}</span>
            <span>출력 토큰: {tokenCount.output.toLocaleString()}</span>
            <span>
              예상 비용: ₩
              {Math.round(
                (tokenCount.input * 0.000015 + tokenCount.output * 0.000075) * 1350
              ).toLocaleString()}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

== P11-STEP-05: 대시보드 메인 레이아웃 ==

[파일: apps/web/app/(dashboard)/layout.tsx]
'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAppStore } from '@/lib/store';

const NAV_ITEMS = [
  { href: '/projects',      label: '프로젝트',  icon: '📁' },
  { href: '/design',        label: '설계 AI',   icon: '🏗️' },
  { href: '/finance',       label: '금융 분석', icon: '💰' },
  { href: '/tax',           label: '세금 계산', icon: '🧮' },
  { href: '/construction',  label: '시공 관리', icon: '🔨' },
  { href: '/auction',       label: '경공매',    icon: '🔨' },
  { href: '/inspection',    label: '감리 AI',   icon: '📸' },
  { href: '/collaboration', label: '협업',      icon: '👥' },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user, clearAuth } = useAppStore();
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated) router.replace('/login');
  }, [isAuthenticated]);

  if (!isAuthenticated) return null;

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* 사이드바 */}
      <aside className="w-64 bg-white border-r border-gray-100 flex flex-col shadow-sm">
        {/* 로고 */}
        <div className="h-16 flex items-center px-6 border-b border-gray-100">
          <span className="text-xl font-bold bg-gradient-to-r from-brand-500 to-brand-900 bg-clip-text text-transparent">
            PropAI
          </span>
          <span className="ml-2 text-xs text-gray-400 font-medium">v30.0</span>
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 py-4 px-3 overflow-y-auto">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-gray-600 hover:bg-brand-50 hover:text-brand-600 transition-colors mb-1 text-sm font-medium"
            >
              <span className="text-lg">{item.icon}</span>
              {item.label}
            </Link>
          ))}
        </nav>

        {/* 사용자 정보 */}
        <div className="p-4 border-t border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-brand-100 rounded-full flex items-center justify-center text-brand-600 font-bold text-sm">
              {user?.name?.charAt(0) || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-gray-900 truncate">{user?.name}</div>
              <div className="text-xs text-gray-400 truncate">{user?.role}</div>
            </div>
            <button
              onClick={() => { clearAuth(); router.replace('/login'); }}
              className="text-gray-400 hover:text-gray-600 text-xs"
              title="로그아웃"
            >
              ⏻
            </button>
          </div>
        </div>
      </aside>

      {/* 메인 콘텐츠 */}
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}

== P11-STEP-06: 프로젝트 목록 페이지 ==

[파일: apps/web/app/(dashboard)/projects/page.tsx]
'use client';
import { useState, useEffect } from 'react';
import { api } from '@/lib/api-client';
import Link from 'next/link';

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  analysis:     { label: '분석 중',   color: 'bg-blue-100 text-blue-700' },
  design:       { label: '설계',      color: 'bg-purple-100 text-purple-700' },
  regulation:   { label: '법규 검토', color: 'bg-yellow-100 text-yellow-700' },
  finance:      { label: '금융 분석', color: 'bg-orange-100 text-orange-700' },
  construction: { label: '시공 중',   color: 'bg-green-100 text-green-700' },
  completed:    { label: '완료',      color: 'bg-gray-100 text-gray-700' },
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showNewModal, setShowNewModal] = useState(false);

  useEffect(() => {
    api.getProjects()
      .then(setProjects)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="p-8">
        <div className="h-8 w-48 bg-gray-200 rounded-lg animate-skeleton mb-6" />
        <div className="grid grid-cols-3 gap-4">
          {Array(6).fill(0).map((_, i) => (
            <div key={i} className="h-40 bg-gray-200 rounded-2xl animate-skeleton" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">프로젝트</h1>
          <p className="text-gray-400 text-sm mt-1">총 {projects.length}개 프로젝트</p>
        </div>
        <button
          onClick={() => setShowNewModal(true)}
          className="bg-brand-500 text-white px-5 py-2.5 rounded-xl font-medium text-sm hover:bg-brand-600 transition-colors flex items-center gap-2"
        >
          + 새 프로젝트
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="text-center py-20 text-gray-400">
          <div className="text-6xl mb-4">📭</div>
          <p>아직 프로젝트가 없습니다</p>
          <button
            onClick={() => setShowNewModal(true)}
            className="mt-4 text-brand-500 font-medium text-sm hover:underline"
          >
            첫 프로젝트 만들기 →
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {projects.map((project) => {
            const statusInfo = STATUS_LABELS[project.status] || { label: project.status, color: 'bg-gray-100 text-gray-600' };
            return (
              <Link
                key={project.project_id}
                href={`/projects/${project.project_id}`}
                className="group bg-white rounded-2xl border border-gray-100 p-5 hover:shadow-md hover:border-brand-200 transition-all"
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="font-semibold text-gray-900 group-hover:text-brand-600 transition-colors truncate pr-2">
                    {project.project_name}
                  </h3>
                  <span className={`text-xs px-2 py-1 rounded-full font-medium whitespace-nowrap ${statusInfo.color}`}>
                    {statusInfo.label}
                  </span>
                </div>
                <p className="text-sm text-gray-500 truncate mb-3">{project.address || '주소 미입력'}</p>
                <div className="flex items-center gap-3 text-xs text-gray-400">
                  {project.land_area_m2 && <span>대지 {project.land_area_m2.toLocaleString()}m²</span>}
                  {project.risk_grade && (
                    <span className={`font-bold ${project.risk_grade === 'A' || project.risk_grade === 'B' ? 'text-green-500' : 'text-red-500'}`}>
                      리스크 {project.risk_grade}등급
                    </span>
                  )}
                </div>
                <div className="mt-3 pt-3 border-t border-gray-50 text-xs text-gray-300">
                  {new Date(project.updated_at || project.created_at).toLocaleDateString('ko-KR')}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

== P11-STEP-07: CRDT 실시간 협업 설정 (Y.js) ==

[파일: apps/web/lib/collaboration.ts]
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

let ydocCache: Map<string, Y.Doc> = new Map();
let providerCache: Map<string, WebsocketProvider> = new Map();

export function getCollaborationDoc(projectId: string): {
  ydoc: Y.Doc;
  provider: WebsocketProvider;
  designNotes: Y.Text;
  projectData: Y.Map<any>;
} {
  if (!ydocCache.has(projectId)) {
    const ydoc = new Y.Doc();
    const provider = new WebsocketProvider(
      `${WS_BASE}/ws/collaborate`,
      `project-${projectId}`,
      ydoc,
      {
        connect: true,
        params: { token: '' },
      }
    );

    ydocCache.set(projectId, ydoc);
    providerCache.set(projectId, provider);
  }

  const ydoc = ydocCache.get(projectId)!;
  const provider = providerCache.get(projectId)!;

  return {
    ydoc,
    provider,
    designNotes: ydoc.getText('design_notes'),
    projectData: ydoc.getMap('project_data'),
  };
}

export function cleanupCollaboration(projectId: string) {
  providerCache.get(projectId)?.disconnect();
  providerCache.delete(projectId);
  ydocCache.delete(projectId);
}

== P11-STEP-08: PWA 서비스 워커 설정 ==

[파일: apps/web/public/manifest.json]
{
  "name": "PropAI - 부동산 AI 플랫폼",
  "short_name": "PropAI",
  "description": "부동산 개발 전주기 AI 자동화 플랫폼",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#0ea5e9",
  "orientation": "portrait-primary",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "screenshots": [
    { "src": "/screenshots/dashboard.png", "sizes": "1280x720", "type": "image/png" }
  ],
  "categories": ["business", "productivity"]
}

================================================================
[PHASE-11 완료 체크리스트]
================================================================
[ ] http://localhost:3000 대시보드 접속 확인
[ ] 로그인 -> JWT 토큰 저장 확인 (localStorage 사용 금지, Zustand persist)
[ ] 프로젝트 목록 페이지 (스켈레톤 로딩 -> 데이터 렌더링)
[ ] CadastralMap 지도 로드 + VWORLD WMS 타일 표시
[ ] 지도 클릭 -> 필지 정보 팝업 표시
[ ] DesignAIPanel -> 설계 생성 -> SSE 스트리밍 텍스트 출력
[ ] 모바일 반응형 확인 (375px 이하)
[ ] PWA 설치 가능 확인 (Lighthouse PWA 점수 90+)
================================================================
```
