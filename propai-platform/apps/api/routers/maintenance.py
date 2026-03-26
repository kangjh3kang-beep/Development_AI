"""Maintenance router for G88."""

from fastapi import APIRouter, Depends
from packages.schemas.models import MaintenanceAnomalyRequest, MaintenanceAnomalyResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.maintenance_service import MaintenanceService

router = APIRouter()


@router.post("/detect-anomaly", response_model=MaintenanceAnomalyResponse)
async def detect_maintenance_anomaly(
    body: MaintenanceAnomalyRequest,
    current_user: CurrentUser = Depends(RequirePermission("maintenance", "write")),
    db: AsyncSession = Depends(get_db),
) -> MaintenanceAnomalyResponse:
    """Detect predictive maintenance anomalies from telemetry."""
    service = MaintenanceService(db)
    alert, work_order = await service.detect_anomaly(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        equipment_name=body.equipment_name,
        equipment_type=body.equipment_type,
        location=body.location,
        vibration_mm_s=body.vibration_mm_s,
        temperature_c=body.temperature_c,
        energy_efficiency_ratio=body.energy_efficiency_ratio,
    )
    return MaintenanceAnomalyResponse(
        alert_id=alert.id,
        project_id=alert.project_id,
        anomaly_score=alert.anomaly_score,
        remaining_useful_life_days=alert.remaining_useful_life_days,
        hvac_efficiency_score=alert.hvac_efficiency_score,
        severity=alert.severity,
        recommendation=alert.recommendation or "",
        work_order_id=work_order.id if work_order is not None else None,
    )
