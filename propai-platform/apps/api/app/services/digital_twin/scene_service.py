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
from typing import Any
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
# 대상지 근접 상위 N동만 건축물대장 실높이 조회(병렬). 직렬 전수호출 금지(가드 준수).
NEIGHBOR_REGISTRY_TOP_N = 14
NEIGHBOR_REGISTRY_TIMEOUT_S = 8.0     # 개별 get_title_by_pnu 타임아웃
NEIGHBOR_REGISTRY_BATCH_TIMEOUT_S = 14.0  # 전체 병렬 배치 상한(SCENE 가드 여유 내)

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


def _aerial_proxy_url(lat: float, lon: float, zoom: int, size: int = 512) -> str:
    """디지털트윈 항공 프록시 GET URL(라우터의 /aerial-image 스트리밍 엔드포인트).

    프론트는 이 URL을 텍스처로 직접 로드한다(키 비노출 — 서버가 VWorld 대리 호출).
    PUBLIC_API_BASE 설정 시 절대 URL 반환(Cloudflare 프론트 오리진→api 오리진 정합·
    WARN-1). 미설정이면 상대 경로 유지(프론트가 resolveApiOrigin으로 방어적 절대화).
    """
    qs = urlencode({
        "lat": f"{lat:.6f}", "lon": f"{lon:.6f}",
        "zoom": str(int(zoom)), "size": str(int(size)),
    })
    path = f"/api/v1/digital-twin/aerial-image?{qs}"
    try:
        from app.core.config import settings

        base = (getattr(settings, "PUBLIC_API_BASE", "") or "").strip().rstrip("/")
    except Exception:  # noqa: BLE001 — 설정 미가용 시 상대 경로 폴백
        base = ""
    return f"{base}{path}" if base else path


def _aerial_cover_m(lat: float, zoom: int, size: int = 512) -> float:
    """VWorld getmap(center+zoom) 커버 폭(m) 근사 — 지형/씬 bbox 드레이프 정합용.

    ★정합 위험(WARN): VWorld getmap은 crs=EPSG:4326(지리좌표)로 응답하지만 zoom은
    웹메르카토르 타일 피라미드 레벨 스케일을 따른다. 여기 m/px는 중심위도 기준
    웹메르카토르 지상해상도(156543.03392 * cos(lat) / 2^zoom)다.
    EPSG:4326 정사각 이미지는 가로(경도)·세로(위도) "도(deg)" 폭이 동일하지만 그 도가
    매핑되는 미터는 위도에서 더 길다(경도는 cos(lat)배 축소). 따라서 cos(lat) 보정을
    적용한 이 값은 **가로(경도) 커버 폭**에 정합하며, 세로(위도) 커버 폭은 이보다
    1/cos(lat)배 크다. 프론트가 항공 텍스처를 정사각 평면에 드레이프할 때 가로/세로
    스케일을 동일하게 쓰면 위도방향이 약간 압축돼 보일 수 있다(고위도일수록 큼).
    한국(lat≈37)에서 cos≈0.80 → 세로가 약 25% 더 넓음. 정밀 드레이프가 필요하면
    프론트에서 cover_lat_m = cover_m / cos(lat)로 가로/세로 스케일을 분리할 것.
    과도수정 방지를 위해 본 함수는 기존 가로폭 근사를 유지한다.
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
            # 대상지 중심까지 거리(실높이 조회 우선순위 정렬용)
            "_dist": math.hypot(cx, cz),
        })
        if len(out) >= 60:
            break

    # 대상지 근접 상위 N동만 건축물대장 표제부로 실높이 보강(병렬·개별 timeout).
    # 직렬 전수호출 금지 — asyncio.gather로 한 번에 발사, 배치 상한도 가드 내로 둔다.
    await _enrich_neighbor_heights(out)

    # 정렬 보조 필드 제거(페이로드 청결)
    for n in out:
        n.pop("_dist", None)
    return out


async def _enrich_neighbor_heights(neighbors: list[dict[str, Any]]) -> None:
    """근접 상위 N동의 ground_floors를 건축물대장 표제부에서 병렬 조회해 실높이로 치환.

    - 거리순 상위 NEIGHBOR_REGISTRY_TOP_N개의 유효 PNU만 대상(전수호출 금지).
    - get_title_by_pnu를 asyncio.gather로 동시 발사, 각 호출 개별 timeout.
    - 성공: height_m = ground_floors × NEIGHBOR_FLOOR_HEIGHT_M, estimated=false.
    - 실패/무자료/국외IP차단: 기존 9m 추정 유지(estimated=true). in-place 갱신.
    """
    candidates = [
        n for n in neighbors if (n.get("pnu") or "") and len(str(n.get("pnu"))) >= 19
    ]
    candidates.sort(key=lambda n: n.get("_dist", 1e9))
    targets = candidates[:NEIGHBOR_REGISTRY_TOP_N]
    if not targets:
        return

    from app.services.external_api.building_registry_service import BuildingRegistryService

    svc = BuildingRegistryService()

    async def _one(pnu: str) -> dict[str, Any] | None:
        try:
            return await asyncio.wait_for(
                svc.get_title_by_pnu(pnu), timeout=NEIGHBOR_REGISTRY_TIMEOUT_S
            )
        except Exception:  # noqa: BLE001 — 개별 실패는 폴백, 로그만 집계 후
            return None

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_one(str(n["pnu"])) for n in targets]),
            timeout=NEIGHBOR_REGISTRY_BATCH_TIMEOUT_S,
        )
    except Exception as e:  # noqa: BLE001 — 배치 전체 타임아웃이면 전부 9m 폴백
        logger.info("주변 실높이 배치 조회 실패(폴백 9m): %s", str(e)[:120])
        return

    enriched = 0
    for n, title in zip(targets, results, strict=False):
        if not isinstance(title, dict):
            continue
        gf = int(title.get("ground_floors") or 0)
        if gf <= 0:
            continue
        n["height_m"] = round(gf * NEIGHBOR_FLOOR_HEIGHT_M, 1)
        n["ground_floors"] = gf
        n["estimated"] = False
        enriched += 1
    logger.info(
        "주변 실높이 보강: %d/%d동 실측치환(나머지 9m 추정)", enriched, len(targets)
    )


async def _resolve_building_glb(
    design_version_id: str | None, project_id: str | None
) -> dict[str, Any]:
    """design_version_id(또는 project_id) 있으면 GET 가능한 glb URL을 구성한다.

    design_v61의 GET /{id}/bim/model.glb 라우트로 정합 — 프론트 BuildingGlb의
    GLTFLoader.loadAsync(=GET)가 그대로 로드한다(과거 POST 전용→405 영구실패 해소).
    design_version_id가 있으면 그걸로(서버가 design_versions에서 매스 복원), 없으면
    project_id로 폴백 매스 절차생성. 둘 다 없으면 building=null.
    """
    if not design_version_id and not project_id:
        return {"glb_url": None, "place_at_enu": None}
    rid = design_version_id or project_id
    return {
        "glb_url": f"/api/v1/design/{rid}/bim/model.glb",
        "method": "GET",
        "note": "GET으로 glb 로드(GLTFLoader.loadAsync). design_v61 GET /{id}/bim/model.glb.",
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

    # ★정합: 항공영상을 지형 bbox(2×SCENE_HALF_M) 가로폭에 맞춰 픽셀 크기를 산출한다.
    #  (기존 고정 512px는 zoom18·lat37에서 ~242m만 커버 → 300m 메시에 늘어나 어긋남)
    _m_per_px = 156_543.033_92 * math.cos(math.radians(lat0)) / (2 ** AERIAL_ZOOM)
    _scene_w_m = 2.0 * SCENE_HALF_M
    _aerial_size = max(256, min(1024, round(_scene_w_m / max(0.01, _m_per_px))))
    _cover_lon_m = round(_aerial_size * _m_per_px, 1)  # ≈ scene_w_m(가로 정합)
    # EPSG:4326 정사각 이미지의 세로(위도) 커버 폭은 가로(경도) 폭 / cos(lat)
    _cover_lat_m = round(_cover_lon_m / max(0.05, math.cos(math.radians(lat0))), 1)
    aerial = {
        "image_proxy_url": _aerial_proxy_url(lat0, lon0, AERIAL_ZOOM, size=_aerial_size),
        "center": [round(lon0, 6), round(lat0, 6)],
        "zoom": AERIAL_ZOOM,
        "size_px": _aerial_size,
        "cover_m": _cover_lon_m,          # 가로(경도) 커버 폭(m) — 기존 호환
        "cover_lon_m": _cover_lon_m,      # 명시적 가로 폭
        "cover_lat_m": _cover_lat_m,      # 세로(위도) 커버 폭(m) — 정밀 드레이프용
        "crs": "EPSG:4326",
        "basemap": "PHOTO",
        "note": (
            "VWorld 항공 정사영상(EPSG:4326) — 촬영시점이 현재와 다를 수 있음(드레이프 텍스처). "
            "정밀 드레이프 시 가로=cover_lon_m·세로=cover_lat_m 분리 적용 권장."
        ),
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

    # 주변건물 실측/추정 집계(실높이=건축물대장 ground_floors×3.3, 나머지=9m 추정)
    n_real = sum(1 for n in neighbors if not n.get("estimated", True))
    n_total = len(neighbors)

    badges = {
        "terrain_source": terrain_src,
        "terrain_resolution_m": terrain_res,
        "confidence": terrain_conf,
        "neighbors_estimated": n_real < n_total,
        "neighbors_total": n_total,
        "neighbors_real_height": n_real,
        "note": (
            f"{terrain_note} 주변건물={n_total}동(실높이 {n_real}동=건축물대장 층수×{NEIGHBOR_FLOOR_HEIGHT_M:.1f}m, "
            f"나머지 {n_total - n_real}동=기본 {NEIGHBOR_DEFAULT_HEIGHT_M:.0f}m 추정). "
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
