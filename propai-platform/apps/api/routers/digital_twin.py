"""Digital twin router for G90 and v53 status operations.

가상준공 3D 디지털트윈 씬(MVP, 공개): POST /scene + GET /aerial-image(항공 프록시).
산정/합성 로직은 app/services/digital_twin/scene_service.py에 있고 본 라우터는 얇게 위임한다.
표고=SRTM 30m·주변건물=footprint 추정·매스=AI 절차생성(실측/인허가도면 아님) — badges에 명시.
"""

from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from packages.schemas.models import (
    AssetIntelligenceRequest,
    AssetIntelligenceResponse,
    DigitalTwinStatusRequest,
    DigitalTwinStatusResponse,
)
from pydantic import BaseModel
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
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from apps.api.database.models.digital_twin_anomaly import DigitalTwinAnomaly

    utc = UTC
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


# ── 가상준공 3D 디지털트윈 씬(MVP, 공개) ──

class DigitalTwinSceneRequest(BaseModel):
    """씬 요청 — address/pnu 중 최소 1개 필수. design_version_id 있으면 건물 glb 포함."""

    address: str | None = None
    pnu: str | None = None
    design_version_id: str | None = None


@router.post("/scene", summary="가상준공 3D 씬 — 필지·지형메시·항공·주변·건물 ENU 정합")
async def build_digital_twin_scene(req: DigitalTwinSceneRequest) -> dict:
    """주소/PNU → ENU 로컬평면 단일 원점으로 정합된 3D 씬 페이로드를 반환한다.

    parcel(필지 ring)·terrain(SRTM 30m DEM 삼각메시)·aerial(항공 프록시 URL)·
    neighbors(주변 footprint 압출 추정)·building(있으면 glb)·badges(정직성)를 합성한다.
    """
    if not (req.address and req.address.strip()) and not (req.pnu and req.pnu.strip()):
        raise HTTPException(status_code=422, detail="address 또는 pnu 중 하나는 필수입니다.")

    from app.services.digital_twin.scene_service import build_scene

    return await build_scene(
        address=(req.address or "").strip() or None,
        pnu=(req.pnu or "").strip() or None,
        design_version_id=(req.design_version_id or "").strip() or None,
    )


class DigitalTwinInterpretContext(BaseModel):
    """가상준공 AI 해설 컨텍스트(선택) — 제공된 항목만 그라운딩에 반영."""

    roi: dict | float | None = None
    esg: dict | float | None = None
    permit: dict | str | None = None
    zone_type: str | None = None
    design_summary: dict | str | None = None


class DigitalTwinInterpretRequest(BaseModel):
    """가상준공 AI 해설 요청 — address/pnu/scene 중 최소 1개 필요."""

    address: str | None = None
    pnu: str | None = None
    scene: dict | None = None
    context: DigitalTwinInterpretContext | None = None


def _summarize_scene(scene: dict, context: dict | None) -> tuple[dict, list[str]]:
    """build_scene 페이로드 → 인터프리터 그라운딩 요약 + used_fields(정직성 표기)."""
    used: list[str] = []
    summary: dict = {}

    addr = scene.get("address")
    if addr:
        summary["address"] = addr
        used.append("address")
    if scene.get("pnu"):
        summary["pnu"] = scene["pnu"]
        used.append("pnu")

    terrain = scene.get("terrain") or {}
    if terrain:
        summary["terrain"] = {
            "slope_deg": terrain.get("slope_deg") or terrain.get("avg_slope_deg"),
            "relief_m": terrain.get("relief_m"),
            "terrain_class": terrain.get("terrain_class") or terrain.get("class"),
            "elev0": terrain.get("elev0"),
            "resolution_m": terrain.get("resolution_m"),
        }
        used.append("terrain(slope/relief/class)")

    neighbors = scene.get("neighbors") or []
    if isinstance(neighbors, list):
        summary["neighbor_count"] = len(neighbors)
        heights = [n.get("height_m") for n in neighbors if isinstance(n, dict) and n.get("height_m")]
        if heights:
            summary["neighbor_avg_height_m"] = round(sum(heights) / len(heights), 1)
        used.append("neighbors")

    building = scene.get("building")
    summary["has_building_mass"] = bool(
        building and (building.get("glb_url") if isinstance(building, dict) else building)
    )
    used.append("building_mass")

    # 필지면적·용도지역은 씬에 직접 없으면 컨텍스트에서 보강.
    if context:
        if context.get("zone_type"):
            summary["zone_type"] = context["zone_type"]
            used.append("zone_type")
        ctx_keep = {k: v for k, v in context.items() if v is not None}
        if ctx_keep:
            summary["context"] = ctx_keep
            used.append("context(" + ",".join(sorted(ctx_keep.keys())) + ")")

    return summary, used


@router.post("/interpret", summary="가상준공 AI 해설 — 씬·컨텍스트 그라운딩 5섹션 해석")
async def interpret_digital_twin(req: DigitalTwinInterpretRequest) -> dict:
    """씬(또는 주소/PNU로 빌드) + 컨텍스트를 LLM이 해석해 5섹션 한국어 서술을 반환한다.

    그라운딩: 제공된 씬·컨텍스트 수치만 근거(추측 금지). 캐시는 기존 interpretation_cache 재사용.
    """
    import asyncio

    has_locator = (req.address and req.address.strip()) or (req.pnu and req.pnu.strip())
    if not has_locator and not req.scene:
        raise HTTPException(
            status_code=422, detail="address/pnu/scene 중 최소 하나는 필요합니다."
        )

    context = req.context.model_dump(exclude_none=True) if req.context else {}

    # 씬 미제공 시 build_scene로 핵심 요약 구성.
    scene = req.scene
    if not scene:
        from app.services.digital_twin.scene_service import build_scene

        try:
            scene = await asyncio.wait_for(
                build_scene(
                    address=(req.address or "").strip() or None,
                    pnu=(req.pnu or "").strip() or None,
                ),
                timeout=90.0,
            )
        except Exception:  # noqa: BLE001
            scene = None
        if not scene or not scene.get("ok"):
            return {
                "ok": False,
                "sections": {},
                "cached": False,
                "grounding": {"used_fields": []},
                "message": "씬 구성에 실패해 해석할 수 없습니다(주소/PNU 또는 좌표 확인).",
                "note": "AI 해석·참고용 — 데이터 미확보 시 해석을 생성하지 않습니다.",
            }

    summary, used_fields = _summarize_scene(scene, context)

    from app.services.ai.interpretation_cache import cache_key, get_cached, put_cached

    data_for_interp = dict(summary)
    if context:
        data_for_interp["context"] = context
    ckey = cache_key("digital_twin", data_for_interp)
    cached = await get_cached(ckey)
    if cached:
        return {
            "ok": True,
            "sections": cached,
            "cached": True,
            "grounding": {"used_fields": used_fields},
            "note": "AI 해석·참고용 — 가상준공 매스(AI 절차생성)·표고(SRTM 30m)는 실측·인허가도면이 아닙니다.",
        }

    from app.services.ai.digital_twin_interpreter import DigitalTwinInterpreter

    try:
        sections = await asyncio.wait_for(
            DigitalTwinInterpreter().generate_interpretation(data_for_interp),
            timeout=30.0,
        )
    except Exception:  # noqa: BLE001
        sections = {}

    ok = isinstance(sections, dict) and bool(sections)
    if ok:
        await put_cached(ckey, "digital_twin", sections)

    return {
        "ok": ok,
        "sections": sections if isinstance(sections, dict) else {},
        "cached": False,
        "grounding": {"used_fields": used_fields},
        "note": "AI 해석·참고용 — 가상준공 매스(AI 절차생성)·표고(SRTM 30m)는 실측·인허가도면이 아닙니다.",
        **({} if ok else {"message": "AI 해석 생성에 실패했습니다(LLM 키/타임아웃)."}),
    }


@router.get("/aerial-image", summary="항공 정사영상 프록시(키 비노출, 지면 텍스처)")
async def digital_twin_aerial_image(
    lat: float = Query(..., description="중심 위도(WGS84)"),
    lon: float = Query(..., description="중심 경도(WGS84)"),
    zoom: int = Query(18, ge=7, le=18, description="VWorld getmap 줌(7~18)"),
    size: int = Query(512, ge=256, le=1024, description="이미지 한 변 px(지형 bbox 정합)"),
) -> Response:
    """VWorld 항공 정사영상(PHOTO) PNG를 서버가 대리 취득해 스트리밍한다(키 비노출)."""
    from app.services.external_api.vworld_service import VWorldService

    acq = await VWorldService().get_aerial_image(lat, lon, zoom=zoom, size=size, basemap="PHOTO")
    if not acq or not acq.get("bytes"):
        raise HTTPException(status_code=502, detail="항공 정사영상을 취득하지 못했습니다.")
    return Response(
        content=acq["bytes"],
        media_type=acq.get("content_type", "image/png"),
        headers={
            "Cache-Control": "public, max-age=86400",
            # TextureLoader crossOrigin=anonymous 대응 — 이미지 응답 CORS 허용(키 비노출).
            "Access-Control-Allow-Origin": "*",
            "Cross-Origin-Resource-Policy": "cross-origin",
        },
    )
