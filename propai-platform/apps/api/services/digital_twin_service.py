"""디지털 트윈 운영 이상 감지 서비스 (G114).

sklearn IsolationForest 기반 IoT 센서 이상 감지.
[B06 버그 패치] predict() 호출 전 데이터 길이(60일분 권장)가
충분히 모였을 때만 fit()을 먼저 실행하도록 순서를 보장.
- asyncio.to_thread()로 ML 추론 논블로킹 처리

추가 기능:
- EUI (Energy Use Intensity) 벤치마크 평가 (ASHRAE 기준)
- Z-score 기반 이상 감지 (3σ 규칙)
- 외기온도 민감도 기반 에너지 예측 (단순 선형회귀)
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
UTC = timezone.utc
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from apps.api.config import get_settings
from apps.api.database.models.digital_twin_anomaly import DigitalTwinAnomaly

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# B06 패치: 최소 데이터 포인트 수 (60일 × 24시간 = 1440, 최소 100)
_MIN_DATA_POINTS_FOR_FIT = 100
_RECOMMENDED_DATA_POINTS = 1440  # 60일분 시간별 데이터

# ASHRAE 기준 EUI 벤치마크 (kWh/m²/yr)
EUI_BENCHMARKS = {
    "office": {"benchmark": 200, "good": 150, "excellent": 100, "label": "오피스"},
    "residential": {"benchmark": 150, "good": 100, "excellent": 70, "label": "주거"},
    "retail": {"benchmark": 250, "good": 180, "excellent": 120, "label": "리테일"},
    "hotel": {"benchmark": 300, "good": 220, "excellent": 150, "label": "호텔"},
    "hospital": {"benchmark": 350, "good": 280, "excellent": 200, "label": "병원"},
    "education": {"benchmark": 180, "good": 130, "excellent": 90, "label": "교육"},
    "warehouse": {"benchmark": 100, "good": 70, "excellent": 50, "label": "물류"},
}

# EUI 등급 기준
EUI_GRADES = {
    "A+": "excellent 이하",
    "A": "good 이하",
    "B": "benchmark 이하",
    "C": "benchmark 초과 ~50%",
    "D": "benchmark 50% 이상 초과",
}


def _fit_and_predict(
    historical_data: list[list[float]],
    current_features: list[float],
) -> tuple[float, bool]:
    """IsolationForest 학습 + 예측을 동기적으로 실행한다.

    [B06 패치] predict()를 호출하기 전 반드시 fit()을 먼저 실행한다.
    데이터 길이가 _MIN_DATA_POINTS_FOR_FIT 미만이면 학습을 거부한다.

    이 함수는 반드시 asyncio.to_thread()를 통해 호출해야 한다.

    Returns
    -------
    tuple[float, bool]
        (anomaly_score, is_anomaly)
        anomaly_score: decision_function 값 (음수일수록 이상)
        is_anomaly: True이면 이상 감지
    """
    import numpy as np
    from sklearn.ensemble import IsolationForest

    x_train = np.array(historical_data)

    # IsolationForest 모델 생성
    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42,
        n_jobs=-1,
    )

    # [B06 핵심] fit() → predict() 순서 보장
    # fit()을 호출하지 않고 predict()를 호출하면 NotFittedError 발생
    model.fit(x_train)

    # 현재 데이터 예측
    x_current = np.array([current_features])
    prediction = model.predict(x_current)  # 1=정상, -1=이상
    score = float(model.decision_function(x_current)[0])

    is_anomaly = int(prediction[0]) == -1

    return score, is_anomaly


class DigitalTwinService:
    """디지털 트윈 IoT 센서 이상 감지 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    # ── EUI 벤치마크 + Z-score 이상 감지 ──

    @staticmethod
    def calculate_eui(energy_kwh: float, area_sqm: float) -> float:
        """EUI (Energy Use Intensity)를 계산한다."""
        if area_sqm <= 0:
            return 0.0
        return round(energy_kwh / area_sqm, 2)

    @staticmethod
    def grade_eui(eui: float, building_type: str = "office") -> dict:
        """EUI를 벤치마크 대비 등급으로 평가한다.

        Returns:
            {"eui": float, "grade": str, "benchmark": float, "ratio": float, "label": str}
        """
        benchmark_data = EUI_BENCHMARKS.get(building_type, EUI_BENCHMARKS["office"])
        benchmark = benchmark_data["benchmark"]
        ratio = round(eui / benchmark, 4) if benchmark > 0 else 0.0

        if eui <= benchmark_data["excellent"]:
            grade = "A+"
        elif eui <= benchmark_data["good"]:
            grade = "A"
        elif eui <= benchmark:
            grade = "B"
        elif eui <= benchmark * 1.5:
            grade = "C"
        else:
            grade = "D"

        return {
            "eui": eui,
            "grade": grade,
            "benchmark": benchmark,
            "ratio": ratio,
            "building_type": building_type,
            "label": benchmark_data["label"],
        }

    @staticmethod
    def detect_anomaly_zscore(
        readings: list[float], threshold: float = 3.0
    ) -> list[dict]:
        """Z-score 기반 이상 감지.

        |z| > threshold인 데이터 포인트를 이상으로 판정한다.
        3σ 규칙 기본 적용 (threshold=3.0).

        Args:
            readings: 센서 읽기 값 리스트 (시계열)
            threshold: Z-score 임계값 (기본 3.0)

        Returns:
            이상 감지된 항목 리스트 [{"index": int, "value": float, "z_score": float, "is_anomaly": bool}]
        """
        if len(readings) < 2:
            return []

        import statistics

        mean = statistics.mean(readings)
        stdev = statistics.stdev(readings)

        if stdev == 0:
            return []

        anomalies = []
        for i, value in enumerate(readings):
            z = (value - mean) / stdev
            if abs(z) > threshold:
                anomalies.append({
                    "index": i,
                    "value": value,
                    "z_score": round(z, 4),
                    "is_anomaly": True,
                })
        return anomalies

    @staticmethod
    def predict_energy(
        outdoor_temps: list[float],
        energy_readings: list[float],
        target_temp: float,
    ) -> float:
        """외기온도 민감도 기반 에너지 예측 (단순 선형회귀).

        Args:
            outdoor_temps: 외기 온도 리스트 (°C)
            energy_readings: 대응하는 에너지 사용량 리스트 (kWh)
            target_temp: 예측할 외기 온도 (°C)

        Returns:
            예측 에너지 사용량 (kWh)
        """
        n = len(outdoor_temps)
        if n < 2 or n != len(energy_readings):
            return 0.0

        # 단순 선형회귀: energy = a + b * temp
        sum_x = sum(outdoor_temps)
        sum_y = sum(energy_readings)
        sum_xy = sum(x * y for x, y in zip(outdoor_temps, energy_readings))
        sum_x2 = sum(x * x for x in outdoor_temps)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return sum_y / n  # 모든 온도 동일 → 평균 반환

        b = (n * sum_xy - sum_x * sum_y) / denominator
        a = (sum_y - b * sum_x) / n

        prediction = a + b * target_temp
        return round(max(0, prediction), 2)

    # ── 에너지 효율 계산 ──

    @staticmethod
    def calculate_efficiency(energy_used: float, baseline: float) -> float:
        """에너지 효율을 계산한다 (baseline 대비 절감률 %).

        B05: baseline 0일 때 Division by Zero 방어.
        """
        if baseline == 0:
            return 0.0
        return (baseline - energy_used) / baseline * 100.0

    # ── IsolationForest 기반 이상 감지 ──

    async def detect_anomaly(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        sensor_type: str,
        current_features: list[float],
        historical_data: list[list[float]],
    ) -> DigitalTwinAnomaly:
        """IoT 센서 데이터의 이상 여부를 감지한다.

        [B06 패치] 데이터가 충분하지 않으면 fit()을 수행하지 않고
        안전하게 'insufficient_data' 상태를 반환한다.
        """
        data_points = len(historical_data)

        logger.info(
            "디지털 트윈 이상 감지 시작",
            sensor_type=sensor_type,
            data_points=data_points,
            min_required=_MIN_DATA_POINTS_FOR_FIT,
        )

        # [B06 패치] 데이터 길이 검증 — fit() 전 반드시 확인
        if data_points < _MIN_DATA_POINTS_FOR_FIT:
            logger.warning(
                "학습 데이터 부족 — 이상 감지 건너뜀",
                data_points=data_points,
                min_required=_MIN_DATA_POINTS_FOR_FIT,
                recommended=_RECOMMENDED_DATA_POINTS,
            )
            anomaly = DigitalTwinAnomaly(
                tenant_id=tenant_id,
                project_id=project_id,
                sensor_type=sensor_type,
                anomaly_score=0.0,
                is_anomaly=False,
                data_points_used=data_points,
                feature_values_json={"features": current_features},
                severity="info",
                detected_at=datetime.now(UTC),
            )
            self.db.add(anomaly)
            await self.db.commit()
            await self.db.refresh(anomaly)
            return anomaly

        if data_points < _RECOMMENDED_DATA_POINTS:
            logger.info(
                "학습 데이터가 권장량 미만 — 정확도 저하 가능",
                data_points=data_points,
                recommended=_RECOMMENDED_DATA_POINTS,
            )

        # ML 추론 — CPU 블로킹이므로 to_thread
        anomaly_score, is_anomaly = await asyncio.to_thread(
            _fit_and_predict, historical_data, current_features,
        )

        # 심각도 판정
        if is_anomaly and anomaly_score < -0.3:
            severity = "critical"
        elif is_anomaly:
            severity = "warning"
        else:
            severity = "info"

        anomaly_record = DigitalTwinAnomaly(
            tenant_id=tenant_id,
            project_id=project_id,
            sensor_type=sensor_type,
            anomaly_score=round(anomaly_score, 6),
            is_anomaly=is_anomaly,
            data_points_used=data_points,
            feature_values_json={"features": current_features},
            severity=severity,
            detected_at=datetime.now(UTC),
        )
        self.db.add(anomaly_record)
        await self.db.commit()
        await self.db.refresh(anomaly_record)

        logger.info(
            "디지털 트윈 이상 감지 완료",
            is_anomaly=is_anomaly,
            score=round(anomaly_score, 6),
            severity=severity,
        )

        return anomaly_record

    # ── v57 Phase 16 확장: IFC 파싱, 센서 수집, 운영 탄소 ──

    @staticmethod
    def parse_ifc_metadata(ifc_data: dict) -> dict:
        """IFC 메타데이터를 파싱한다.

        ifcopenshell 미설치 환경에서는 JSON dict 입력을 직접 처리한다.

        Args:
            ifc_data: IFC 데이터 (JSON dict)

        Returns:
            {"building_name", "site_area", "gross_area", "num_floors", "materials", "height"}
        """
        return {
            "building_name": ifc_data.get("name", "Unknown"),
            "site_area": ifc_data.get("site_area_sqm", 0),
            "gross_area": ifc_data.get("gross_floor_area_sqm", 0),
            "num_floors": ifc_data.get("num_floors", 0),
            "materials": ifc_data.get("materials", []),
            "height": ifc_data.get("building_height_m", 0),
        }

    async def ingest_sensor_reading(
        self,
        *,
        tenant_id,
        project_id,
        sensor_type: str,
        value: float,
        timestamp=None,
    ) -> dict:
        """개별 센서 데이터를 수집하여 DB에 저장한다 (MQTT 메시지 호환).

        Args:
            tenant_id: 테넌트 ID
            project_id: 프로젝트 ID
            sensor_type: 센서 유형 (temperature, humidity 등)
            value: 센서 값
            timestamp: 타임스탬프 (None이면 현재 시각)

        Returns:
            {"sensor_type": str, "value": float, "timestamp": str, "stored": bool}
        """
        ts = timestamp or datetime.now(UTC)

        record = DigitalTwinAnomaly(
            tenant_id=tenant_id,
            project_id=project_id,
            sensor_type=sensor_type,
            anomaly_score=0.0,
            is_anomaly=False,
            data_points_used=1,
            feature_values_json={"value": value, "timestamp": ts.isoformat()},
            severity="info",
            detected_at=ts,
        )
        self.db.add(record)
        await self.db.commit()
        return {
            "sensor_type": sensor_type,
            "value": value,
            "timestamp": ts.isoformat(),
            "stored": True,
        }

    @staticmethod
    def calculate_operational_carbon(
        energy_readings: list[dict],
        grid_ef: float = 0.4629,
    ) -> dict:
        """실제 에너지 사용량 기반 운영 탄소 배출량을 산출한다.

        Args:
            energy_readings: [{"month": "2026-01", "kwh": 15000}, ...]
            grid_ef: 전력배출계수 (kgCO2eq/kWh) -- 한국 기본값 0.4629

        Returns:
            {"total_carbon_kg": float, "monthly": [...], "trend": "increasing"|"decreasing"|"stable"}
        """
        monthly = []
        for r in energy_readings:
            carbon_kg = r["kwh"] * grid_ef
            monthly.append({
                "month": r["month"],
                "kwh": r["kwh"],
                "carbon_kg": round(carbon_kg, 2),
            })

        total = sum(m["carbon_kg"] for m in monthly)

        # 트렌드 판정 (최근 3개월 vs 이전 3개월)
        if len(monthly) >= 6:
            recent = sum(m["carbon_kg"] for m in monthly[-3:])
            earlier = sum(m["carbon_kg"] for m in monthly[-6:-3])
            if recent > earlier * 1.05:
                trend = "increasing"
            elif recent < earlier * 0.95:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return {
            "total_carbon_kg": round(total, 2),
            "monthly": monthly,
            "trend": trend,
        }
