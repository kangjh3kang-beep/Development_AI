"""가상준공 3D 디지털트윈 — 씬 페이로드 본체.

좌표정합(ENU 로컬평면) 합성 레이어. 라이브 재료 4종을 단일 원점(lat0,lon0=필지중심)
ENU 미터로 정합해 프론트(@react-three/fiber)가 그대로 앉힐 수 있는 형태로 반환한다.

  - parcel : VWorld 필지 폴리곤(EPSG4326) → ENU ring
  - terrain: SRTM 30m DEM 격자 → ENU 삼각 메시(terrain_service.build_terrain_mesh 재사용)
  - aerial : VWorld 항공 정사영상(PHOTO) 프록시 URL + center/zoom/cover_m
  - neighbors: 주변 필지 footprint → ENU 폴리곤 + 추정 압출고(estimated:true)
  - building: design_v61 glb(있으면) URL + place_at_enu

정직성(비협상): 표고=SRTM 30m·실측 아님, 주변건물=footprint 추정, 매스=AI 절차생성·
인허가도면 아님, 항공=촬영시점 상이 가능. badges에 출처·해상도·confidence·note 명시.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Optional
from urllib.parse import urlencode

import structlog

logger = structlog.get_logger()

# 씬 규모(±half_m 정사각). 지형 메시·항공 커버·주변 bbox 공통 기준.
SCENE_HALF_M = 150.0
TERRAIN_GRID_N = 21          # 21x21 = 441점
AERIAL_ZOOM = 18            # VWorld getmap 항공 줌(고해상)
NEIGHBOR_DEFAULT_HEIGHT_M = 9.0
NEIGHBOR_FLOOR_HEIGHT_M = 3.3
SCENE_TIMEOUT_S = 88.0      # 90초 가드 직전
TERRAIN_TIMEOUT_S = 60.0
AERIAL_TIMEOUT_S = 20.0
NEIGHBOR_TIMEOUT_S = 20.0

SOURCES = [
    "좌표·필지·주변필지·항공: VWorld(국토교통부 공간정보 오픈플랫폼)",
    "표고(지형메시): OpenTopoData SRTM 30m — api.opentopodata.org",
    "건물 매스: PropAI AutoDesign 절차생성 glTF(있을 때) — AI 추정·인허가도면 아님",
]


def _ring_lonlat(geometry: dict | None) -> list[tuple[float, float]]:
    """GeoJSON geometry → 외곽 ring [(lon,lat), ...]. 실패시 빈 리스트."""
    if not geometry:
        return []
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return []
    try:
        if gtype == "Polygon":
            return [(float(x), float(y)) for x, y in coords[0]]
        if gtype == "MultiPolygon":
            return [(float(x), float(y)) for x, y in coords[0][0]]
    except (ValueError, TypeError, IndexError):
        return []
    return []


def _enu_xz(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    """WGS84 → ENU 로컬평면 (x=동, z=남). 원점=(lon0,lat0).

    terrain_service의 111320*cos 수식과 동일. z=-(북) 이므로 남쪽이 +z(Three.js 우수좌표).
    """
    x = (lon - lon0) * 111_320.0 * math.cos(math.radians(lat0))
    z = -(lat - lat0) * 111_320.0
    return x, z


def _ring_to_enu(
    ring: list[tuple[float, float]], lon0: float, lat0: float
) -> list[list[float]]:
    """ring [(lon,lat)] → ENU [[x,z], ...] (소수 3자리)."""
    out: list[list[float]] = []
    for lon, lat in ring:
        x, z = _enu_xz(lon, lat, lon0, lat0)
        out.append([round(x, 3), round(z, 3)])
    return out


def _aerial_proxy_url(lat: float, lon: float, zoom: int) -> str:
    """디지털트윈 항공 프록시 GET URL(라우터의 /aerial-image 스트리밍 엔드포인트).

    프론트는 이 URL을 텍스처로 직접 로드한다(키 비노출 — 서버가 VWorld 대리 호출).
    """
    qs = urlencode({"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": str(int(zoom))})
    return f"/api/v1/digital-twin/aerial-image?{qs}"


def _aerial_cover_m(lat: float, zoom: int, size: int = 512) -> float:
    """VWorld getmap(center+zoom) 커버 폭(m) 근사 — 지형 bbox 정합용.

    웹메르카토르 해상도: m/px ≈ 156543.03392 * cos(lat) / 2^zoom. cover = m/px * size.
    """
    m_per_px = 156_543.033_92 * math.cos(math.radians(lat)) / (2 ** int(zoom))
    return round(m_per_px * size, 1)


async def _build_parcel(geometry: dict | None, lon0: float, lat0: float) -> dict[str, Any]:
    ring = _ring_lonlat(geometry)
    ring_enu = _ring_to_enu(ring, lon0, lat0) if ring else []
    return {"ring_enu": ring_enu, "center_enu": [0.0, 0.0]}


async def _build_neighbors(
    lat0: float, lon0: float, self_pnu: str | None
) -> list[dict[str, Any]]:
    """주변 필지 footprint → ENU 압출 추정. 자기 필지·도로/하천 등 비건물 지목 제외."""
    from app.services.external_api.vworld_service import VWorldService

    half_deg_lat = SCENE_HALF_M / 111_320.0
    half_deg_lon = SCENE_HALF_M / (111_320.0 * math.cos(math.radians(lat0)))
    min_lon, max_lon = lon0 - half_deg_lon, lon0 + half_deg_lon
    min_lat, max_lat = lat0 - half_deg_lat, lat0 + half_deg_lat

    svc = VWorldService()
    try:
        parcels = await asyncio.wait_for(
            svc.get_parcels_in_bbox(min_lon, min_lat, max_lon, max_lat, max_count=80),
            timeout=NEIGHBOR_TIMEOUT_S,
        )
    except Exception as e:  # noqa: BLE001
        logger.info("주변 필지 조회 실패: %s", str(e)[:150])
        return []

    # 비건물 지목(도로·하천·구거·제방 등)은 압출 제외 → 빈 대지로 둠
    non_building = {"도로", "하천", "구거", "제방", "유지", "수도용지", "철도용지"}
    out: list[dict[str, Any]] = []
    for p in parcels:
        if self_pnu and p.get("pnu") == self_pnu:
            continue
        if (p.get("jimok") or "") in non_building:
            continue
        ring = _ring_lonlat(p.get("geometry"))
        if len(ring) < 3:
            continue
        fp = _ring_to_enu(ring, lon0, lat0)
        # 씬 외곽으로 완전히 벗어난 필지 스킵(중심점 기준)
        cx = sum(c[0] for c in fp) / len(fp)
        cz = sum(c[1] for c in fp) / len(fp)
        if abs(cx) > SCENE_HALF_M * 1.4 or abs(cz) > SCENE_HALF_M * 1.4:
            continue
        out.append({
            "pnu": p.get("pnu", ""),
            "jimok": p.get("jimok", ""),
            "footprint_enu": fp,
            "height_m": NEIGHBOR_DEFAULT_HEIGHT_M,
            "estimated": True,
        })
        if len(out) >= 60:
            break
    return out


async def _resolve_building_glb(
    design_version_id: str | None, project_id: str | None
) -> dict[str, Any]:
    """design_version_id(또는 project_id) 있으면 glb URL 구성. glb 라우트는 POST이므로
    URL만 노출하고 프론트가 매스 페이로드와 함께 POST 로드한다(없으면 building=null).
    """
    if not design_version_id and not project_id:
        return {"glb_url": None, "place_at_enu": None}
    pid = design_version_id or project_id
    return {
        "glb_url": f"/api/v1/design/{pid}/bim/model.glb",
        "method": "POST",
        "note": "POST(매스 페이로드 동봉)로 glb 로드. design_v61 /{id}/bim/model.glb.",
    }


async def build_scene(
    address: str | None,
    pnu: str | None,
    design_version_id: str | None = None,
) -> dict[str, Any]:
    """씬 페이로드 빌드. 좌표/필지 불가→ok:false. 표고 실패해도 나머지로 ok 가능."""
    from app.services.terrain.terrain_service import _resolve_location, build_terrain_mesh

    loc = await _resolve_location(address, pnu)
    if loc is None:
        return {
            "ok": False,
            "message": "주소/PNU로 좌표 또는 필지를 확인하지 못했습니다. 주소 또는 PNU를 확인하세요.",
            "sources": SOURCES,
        }

    lat0, lon0 = loc["lat"], loc["lon"]
    geometry = loc.get("geometry")
    resolved_pnu = loc.get("pnu")

    async def _terrain():
        try:
            return await asyncio.wait_for(
                build_terrain_mesh(lat0, lon0, half_m=SCENE_HALF_M, n=TERRAIN_GRID_N),
                timeout=TERRAIN_TIMEOUT_S,
            )
        except Exception as e:  # noqa: BLE001
            logger.info("지형메시 빌드 실패: %s", str(e)[:150])
            return None

    parcel, terrain, neighbors, building = await asyncio.wait_for(
        asyncio.gather(
            _build_parcel(geometry, lon0, lat0),
            _terrain(),
            _build_neighbors(lat0, lon0, resolved_pnu),
            _resolve_building_glb(design_version_id, None),
        ),
        timeout=SCENE_TIMEOUT_S,
    )

    elev0 = float(terrain["elev0"]) if terrain else 0.0

    aerial = {
        "image_proxy_url": _aerial_proxy_url(lat0, lon0, AERIAL_ZOOM),
        "center": [round(lon0, 6), round(lat0, 6)],
        "zoom": AERIAL_ZOOM,
        "cover_m": _aerial_cover_m(lat0, AERIAL_ZOOM),
        "basemap": "PHOTO",
        "note": "VWorld 항공 정사영상 — 촬영시점이 현재와 다를 수 있음(드레이프 텍스처).",
    }

    if building.get("glb_url"):
        building["place_at_enu"] = [0.0, elev0, 0.0]
    else:
        building = None  # type: ignore[assignment]

    # ── 정직성 배지 ──
    if terrain:
        terrain_conf = round(0.6 * float(terrain.get("valid_ratio", 1.0)), 2)
        terrain_note = (
            f"표고 SRTM {terrain.get('resolution_m', 30)}m 광역 격자 — 실측·정밀측량 아님. "
            f"기복 {terrain.get('relief_m', 0)}m(중심표고 {terrain.get('elev0', 0)}m)."
        )
        terrain_src = terrain.get("source")
        terrain_res = terrain.get("resolution_m", 30.0)
    else:
        terrain_conf = 0.0
        terrain_note = "표고(DEM) 취득 실패 — 지형은 평면으로 대체(OpenTopoData 일시 장애 가능)."
        terrain_src = "OpenTopoData SRTM 30m (미취득)"
        terrain_res = 30.0

    badges = {
        "terrain_source": terrain_src,
        "terrain_resolution_m": terrain_res,
        "confidence": terrain_conf,
        "neighbors_estimated": True,
        "note": (
            f"{terrain_note} 주변건물={len(neighbors)}동 footprint 압출 추정"
            f"(기본 {NEIGHBOR_DEFAULT_HEIGHT_M:.0f}m, 실측 아님). "
            f"건물 매스={'AI 절차생성(인허가도면 아님)' if building else '없음(지형·항공·필지만)'}. "
            f"실측=실선/채움, 추정=점선/반투명으로 시각 구분."
        ),
    }

    return {
        "ok": True,
        "address": loc.get("address") or address or "",
        "pnu": resolved_pnu,
        "lat0": round(lat0, 6),
        "lon0": round(lon0, 6),
        "parcel": parcel,
        "terrain": terrain,
        "aerial": aerial,
        "neighbors": neighbors,
        "building": building,
        "badges": badges,
        "sources": SOURCES,
    }
