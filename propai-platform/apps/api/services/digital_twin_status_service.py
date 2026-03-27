"""v53 digital twin status engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
UTC = timezone.utc
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.digital_twin_anomaly import DigitalTwinAnomaly
from apps.api.database.models.phase_v53_operations import DigitalTwinStatusSnapshot
from apps.api.database.models.project import Project
from apps.api.services.digital_twin_service import DigitalTwinService

_SEVERITY_ORDER = {"info": 1, "warning": 2, "critical": 3}


class DigitalTwinStatusService:
    """Persisted project operations status for v53 digital twin workflows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def _sensor_health_ratio(sensor_count: int, online_sensor_count: int) -> float:
        total = max(sensor_count, 1)
        online = min(max(online_sensor_count, 0), total)
        return round(online / total, 4)

    @classmethod
    def _readiness_score(
        cls,
        *,
        eui_ratio: float,
        sensor_health_ratio: float,
        occupancy_rate: float,
        anomaly_count: int,
        critical_alarm_count: int,
    ) -> float:
        energy_penalty = max(eui_ratio - 1.0, 0.0) * 35.0
        sensor_penalty = (1.0 - sensor_health_ratio) * 30.0
        occupancy_penalty = max(0.85 - occupancy_rate, 0.0) * 40.0
        anomaly_penalty = min(anomaly_count * 4.0, 20.0)
        critical_penalty = min(critical_alarm_count * 12.0, 36.0)
        score = 100.0 - (
            energy_penalty
            + sensor_penalty
            + occupancy_penalty
            + anomaly_penalty
            + critical_penalty
        )
        return round(cls._clamp(score), 2)

    @staticmethod
    def _status_from_score(
        score: float,
        *,
        anomaly_count: int,
        critical_alarm_count: int,
    ) -> str:
        if critical_alarm_count > 0 or score < 60:
            return "critical"
        if anomaly_count >= 3 or score < 80:
            return "watch"
        return "healthy"

    @staticmethod
    def _recommendations(
        *,
        eui_ratio: float,
        sensor_health_ratio: float,
        anomaly_count: int,
        critical_alarm_count: int,
    ) -> list[str]:
        items: list[str] = []
        if eui_ratio > 1.0:
            items.append("Recommission HVAC and lighting schedules to reduce energy drift.")
        if sensor_health_ratio < 0.9:
            items.append("Restore offline IoT sensors before expanding anomaly automation.")
        if anomaly_count >= 3:
            items.append("Review recent anomaly clusters before issuing new occupancy targets.")
        if critical_alarm_count > 0:
            items.append("Escalate critical alarms into the maintenance command queue immediately.")
        if not items:
            items.append("Status remains healthy; keep weekly telemetry and energy reviews active.")
        return items

    async def _get_project(self, tenant_id: UUID, project_id: UUID) -> Project | None:
        result = await self.db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == tenant_id,
                Project.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _recent_anomaly_context(
        self,
        tenant_id: UUID,
        project_id: UUID,
    ) -> tuple[int, str]:
        cutoff = datetime.now(UTC) - timedelta(days=30)
        result = await self.db.execute(
            select(DigitalTwinAnomaly).where(
                DigitalTwinAnomaly.tenant_id == tenant_id,
                DigitalTwinAnomaly.project_id == project_id,
                DigitalTwinAnomaly.detected_at >= cutoff,
            )
        )
        anomalies = list(result.scalars().all())
        if not anomalies:
            return 0, "info"

        highest = max(
            anomalies,
            key=lambda item: _SEVERITY_ORDER.get(item.severity, 0),
        )
        return len(anomalies), highest.severity

    @staticmethod
    def _serialize(
        snapshot: DigitalTwinStatusSnapshot,
        *,
        project_name: str,
        benchmark_eui: float,
        sensor_health_ratio: float,
        highest_anomaly_severity: str,
    ) -> dict:
        return {
            "snapshot_id": snapshot.id,
            "project_id": snapshot.project_id,
            "project_name": project_name,
            "building_type": snapshot.building_type,
            "status": snapshot.status,
            "operational_readiness_score": snapshot.operational_readiness_score,
            "eui": snapshot.eui,
            "eui_grade": snapshot.eui_grade,
            "benchmark_eui": benchmark_eui,
            "sensor_health_ratio": sensor_health_ratio,
            "occupancy_rate": snapshot.occupancy_rate,
            "recent_anomaly_count": snapshot.latest_anomaly_count,
            "highest_anomaly_severity": highest_anomaly_severity,
            "critical_alarm_count": snapshot.critical_alarm_count,
            "predicted_next_day_energy_kwh": snapshot.predicted_next_day_energy_kwh,
            "recommendations": list(snapshot.recommendations_json or []),
            "created_at": snapshot.created_at,
        }

    async def snapshot(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        building_type: str,
        gross_floor_area_sqm: float,
        annual_energy_kwh: float,
        occupancy_rate: float,
        sensor_count: int,
        online_sensor_count: int,
        critical_alarm_count: int,
        recent_outdoor_temps_c: list[float],
        recent_energy_readings_kwh: list[float],
        target_outdoor_temp_c: float | None,
    ) -> dict:
        project = await self._get_project(tenant_id, project_id)
        if project is None:
            raise ValueError("Project was not found")

        anomaly_count, highest_anomaly_severity = await self._recent_anomaly_context(
            tenant_id,
            project_id,
        )
        eui = DigitalTwinService.calculate_eui(annual_energy_kwh, gross_floor_area_sqm)
        eui_grade_data = DigitalTwinService.grade_eui(eui, building_type)
        sensor_health_ratio = self._sensor_health_ratio(sensor_count, online_sensor_count)
        readiness_score = self._readiness_score(
            eui_ratio=eui_grade_data["ratio"],
            sensor_health_ratio=sensor_health_ratio,
            occupancy_rate=occupancy_rate,
            anomaly_count=anomaly_count,
            critical_alarm_count=critical_alarm_count,
        )
        status = self._status_from_score(
            readiness_score,
            anomaly_count=anomaly_count,
            critical_alarm_count=critical_alarm_count,
        )
        predicted_energy = None
        if (
            target_outdoor_temp_c is not None
            and len(recent_outdoor_temps_c) >= 2
            and len(recent_outdoor_temps_c) == len(recent_energy_readings_kwh)
        ):
            predicted_energy = DigitalTwinService.predict_energy(
                recent_outdoor_temps_c,
                recent_energy_readings_kwh,
                target_outdoor_temp_c,
            )

        recommendations = self._recommendations(
            eui_ratio=eui_grade_data["ratio"],
            sensor_health_ratio=sensor_health_ratio,
            anomaly_count=anomaly_count,
            critical_alarm_count=critical_alarm_count,
        )

        snapshot = DigitalTwinStatusSnapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            building_type=building_type,
            gross_floor_area_sqm=gross_floor_area_sqm,
            annual_energy_kwh=annual_energy_kwh,
            occupancy_rate=occupancy_rate,
            sensor_count=sensor_count,
            online_sensor_count=min(max(online_sensor_count, 0), max(sensor_count, 1)),
            latest_anomaly_count=anomaly_count,
            critical_alarm_count=critical_alarm_count,
            eui=eui,
            eui_grade=eui_grade_data["grade"],
            operational_readiness_score=readiness_score,
            status=status,
            predicted_next_day_energy_kwh=predicted_energy,
            status_summary_json={
                "benchmark_eui": eui_grade_data["benchmark"],
                "eui_ratio": eui_grade_data["ratio"],
                "sensor_health_ratio": sensor_health_ratio,
                "highest_anomaly_severity": highest_anomaly_severity,
            },
            recommendations_json=recommendations,
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)

        return self._serialize(
            snapshot,
            project_name=project.name,
            benchmark_eui=eui_grade_data["benchmark"],
            sensor_health_ratio=sensor_health_ratio,
            highest_anomaly_severity=highest_anomaly_severity,
        )

    async def get_latest(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
    ) -> dict | None:
        project = await self._get_project(tenant_id, project_id)
        if project is None:
            return None

        result = await self.db.execute(
            select(DigitalTwinStatusSnapshot)
            .where(
                DigitalTwinStatusSnapshot.tenant_id == tenant_id,
                DigitalTwinStatusSnapshot.project_id == project_id,
            )
            .order_by(DigitalTwinStatusSnapshot.created_at.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        if snapshot is None:
            return None

        summary = dict(snapshot.status_summary_json or {})
        return self._serialize(
            snapshot,
            project_name=project.name,
            benchmark_eui=float(summary.get("benchmark_eui", 0.0)),
            sensor_health_ratio=float(summary.get("sensor_health_ratio", 0.0)),
            highest_anomaly_severity=str(summary.get("highest_anomaly_severity", "info")),
        )
