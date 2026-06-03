"""Digital twin router for G90 and v53 status operations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from packages.schemas.models import (
    AssetIntelligenceRequest,
    AssetIntelligenceResponse,
    DigitalTwinStatusRequest,
    DigitalTwinStatusResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission
from apps.api.database.session import get_db
from apps.api.services.asset_intelligence_service import AssetIntelligenceService
from apps.api.services.digital_twin_status_service import DigitalTwinStatusService

router = APIRouter()


@router.post("/status/snapshot", response_model=DigitalTwinStatusResponse)
async def create_digital_twin_status_snapshot(
    body: DigitalTwinStatusRequest,
    current_user: CurrentUser = Depends(RequirePermission("digital_twin_status", "write")),
    db: AsyncSession = Depends(get_db),
) -> DigitalTwinStatusResponse:
    """Persist a v53 digital twin operations snapshot."""
    service = DigitalTwinStatusService(db)
    try:
        result = await service.snapshot(
            tenant_id=current_user.tenant_id,
            project_id=body.project_id,
            building_type=body.building_type,
            gross_floor_area_sqm=body.gross_floor_area_sqm,
            annual_energy_kwh=body.annual_energy_kwh,
            occupancy_rate=body.occupancy_rate,
            sensor_count=body.sensor_count,
            online_sensor_count=body.online_sensor_count,
            critical_alarm_count=body.critical_alarm_count,
            recent_outdoor_temps_c=body.recent_outdoor_temps_c,
            recent_energy_readings_kwh=body.recent_energy_readings_kwh,
            target_outdoor_temp_c=body.target_outdoor_temp_c,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return DigitalTwinStatusResponse.model_validate(result)


@router.get("/status/{project_id}/latest", response_model=DigitalTwinStatusResponse)
async def get_latest_digital_twin_status(
    project_id: UUID,
    current_user: CurrentUser = Depends(RequirePermission("digital_twin_status", "read")),
    db: AsyncSession = Depends(get_db),
) -> DigitalTwinStatusResponse:
    """Return the latest persisted digital twin status snapshot."""
    service = DigitalTwinStatusService(db)
    result = await service.get_latest(
        tenant_id=current_user.tenant_id,
        project_id=project_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Latest digital twin status snapshot was not found",
        )
    return DigitalTwinStatusResponse.model_validate(result)


@router.post("/asset-intelligence", response_model=AssetIntelligenceResponse)
async def analyze_asset_intelligence(
    body: AssetIntelligenceRequest,
    current_user: CurrentUser = Depends(RequirePermission("asset_intelligence", "write")),
    db: AsyncSession = Depends(get_db),
) -> AssetIntelligenceResponse:
    """Generate an asset intelligence snapshot and capex plan."""
    service = AssetIntelligenceService(db)
    snapshot, capex_results = await service.analyze(
        tenant_id=current_user.tenant_id,
        project_id=body.project_id,
        base_value_krw=body.base_value_krw,
        maintenance_score=body.maintenance_score,
        tenant_score=body.tenant_score,
        market_score=body.market_score,
        climate_score=body.climate_score,
    )
    return AssetIntelligenceResponse(
        snapshot_id=snapshot.id,
        project_id=snapshot.project_id,
        composite_score=snapshot.composite_score,
        grade=snapshot.grade,
        adjusted_value_krw=snapshot.adjusted_value_krw,
        component_scores=dict(snapshot.component_scores_json or {}),
        capex_recommendations=[
            {
                "strategy_name": result.strategy_name,
                "expected_roi": result.expected_roi,
                "payback_months": result.payback_months,
            }
            for result in capex_results
        ],
        created_at=snapshot.created_at,
    )


@router.get("/anomalies")
async def get_digital_twin_anomalies(
    project_id: UUID | None = None,
    current_user: CurrentUser = Depends(RequirePermission("digital_twin_status", "read")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """최근 30일 디지털트윈 이상탐지 시계열 + 요약(프론트 DigitalTwinDashboardData 형태)."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from apps.api.database.models.digital_twin_anomaly import DigitalTwinAnomaly

    utc = timezone.utc
    since = datetime.now(utc) - timedelta(days=30)
    query = select(DigitalTwinAnomaly).where(
        DigitalTwinAnomaly.tenant_id == current_user.tenant_id,
        DigitalTwinAnomaly.detected_at >= since,
    )
    if project_id:
        query = query.where(DigitalTwinAnomaly.project_id == project_id)
    query = query.order_by(DigitalTwinAnomaly.detected_at.asc())

    rows = list((await db.execute(query)).scalars().all())

    anomalies = [
        {
            "timestamp": r.detected_at.isoformat(),
            "sensor_type": r.sensor_type,
            "value": float(next(iter((r.feature_values_json or {}).values()), r.anomaly_score)),
            "anomaly_score": r.anomaly_score,
            "is_anomaly": r.is_anomaly,
            "severity": r.severity,
        }
        for r in rows
    ]
    detected = [r for r in rows if r.is_anomaly]
    last_scan = max((r.detected_at for r in rows), default=datetime.now(utc))
    return {
        "anomalies": anomalies,
        "summary": {
            "total_sensors": len({r.sensor_type for r in rows}),
            "anomalies_detected": len(detected),
            "critical_count": sum(1 for r in detected if r.severity == "critical"),
            "warning_count": sum(1 for r in detected if r.severity == "warning"),
            "last_scan_at": last_scan.isoformat(),
        },
    }
