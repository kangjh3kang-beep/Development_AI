"""Predictive maintenance service for G88."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_f_maintenance import (
    EquipmentSensor,
    PredictiveMaintenanceAlert,
    WorkOrder,
)


class MaintenanceService:
    """Create maintenance alerts and work orders from telemetry."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _evaluate(
        *,
        vibration_mm_s: float,
        temperature_c: float,
        energy_efficiency_ratio: float,
    ) -> tuple[float, int, float, str, str]:
        vibration_score = min(1.0, vibration_mm_s / 12.0)
        temperature_score = min(1.0, max(0.0, temperature_c - 24.0) / 18.0)
        efficiency_penalty = min(1.0, max(0.0, 1.0 - energy_efficiency_ratio) / 0.45)

        anomaly_score = round(
            min(1.0, vibration_score * 0.45 + temperature_score * 0.30 + efficiency_penalty * 0.25),
            4,
        )
        hvac_efficiency_score = round(max(0.0, min(100.0, energy_efficiency_ratio * 100.0)), 2)
        remaining_useful_life_days = max(7, round(365 * (1.0 - anomaly_score * 0.82)))

        if anomaly_score >= 0.78:
            severity = "critical"
            recommendation = "Open an immediate work order and inspect compressor, bearings, and balancing."
        elif anomaly_score >= 0.58:
            severity = "high"
            recommendation = "Schedule maintenance within 72 hours and verify airflow, belts, and refrigerant load."
        elif anomaly_score >= 0.35:
            severity = "medium"
            recommendation = "Increase monitoring cadence and prepare preventive maintenance for the next cycle."
        else:
            severity = "low"
            recommendation = "Continue routine monitoring; current telemetry is within acceptable range."

        return anomaly_score, remaining_useful_life_days, hvac_efficiency_score, severity, recommendation

    async def detect_anomaly(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        equipment_name: str,
        equipment_type: str,
        location: str | None,
        vibration_mm_s: float,
        temperature_c: float,
        energy_efficiency_ratio: float,
    ) -> tuple[PredictiveMaintenanceAlert, WorkOrder | None]:
        anomaly_score, remaining_useful_life_days, hvac_efficiency_score, severity, recommendation = self._evaluate(
            vibration_mm_s=vibration_mm_s,
            temperature_c=temperature_c,
            energy_efficiency_ratio=energy_efficiency_ratio,
        )

        sensor = EquipmentSensor(
            tenant_id=tenant_id,
            project_id=project_id,
            equipment_name=equipment_name,
            equipment_type=equipment_type,
            location=location,
            latest_reading_json={
                "vibration_mm_s": vibration_mm_s,
                "temperature_c": temperature_c,
                "energy_efficiency_ratio": energy_efficiency_ratio,
            },
            health_status="alert" if anomaly_score >= 0.35 else "normal",
            last_reading_at=datetime.now(UTC),
        )
        self.db.add(sensor)
        await self.db.flush()

        alert = PredictiveMaintenanceAlert(
            tenant_id=tenant_id,
            project_id=project_id,
            equipment_sensor_id=sensor.id,
            anomaly_score=anomaly_score,
            remaining_useful_life_days=remaining_useful_life_days,
            hvac_efficiency_score=hvac_efficiency_score,
            severity=severity,
            recommendation=recommendation,
            telemetry_json=sensor.latest_reading_json,
        )
        self.db.add(alert)
        await self.db.flush()

        work_order: WorkOrder | None = None
        if severity in {"high", "critical"}:
            work_order = WorkOrder(
                tenant_id=tenant_id,
                project_id=project_id,
                maintenance_alert_id=alert.id,
                title=f"{equipment_name} predictive maintenance",
                status="open",
                priority="urgent" if severity == "critical" else "high",
                assigned_team="facility-ops",
                details=recommendation,
            )
            self.db.add(work_order)

        await self.db.commit()
        await self.db.refresh(alert)
        if work_order is not None:
            await self.db.refresh(work_order)
        return alert, work_order
