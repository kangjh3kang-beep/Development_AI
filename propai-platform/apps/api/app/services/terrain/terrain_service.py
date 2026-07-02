"""Flagship C-1 — 지형분석 본체 (경사도·토공량·지형단면).

표고(DEM) 소스 라이브 정찰 결과(2026-06-05):
- VWorld/NGII: 좌표·필지 폴리곤은 키로 동작하나, 점/그리드 표고를 JSON으로 주는
  공개 엔드포인트는 없음(NGII DEM은 WCS/파일 기반). → 표고는 미지원.
- OpenTopoData SRTM 30m(무키, https://api.opentopodata.org/v1/srtm30m): 라이브 동작 확인.
  배치 ≤100점/req, 1req/s 제한. 본 서비스는 단일 배치(≤225점)로 1회 질의한다.

정직 원칙: 표고 소스·해상도(~30m)를 응답에 명시. 필지가 DEM 1셀(≈30m×30m=900㎡)보다
작으면 SRTM 광역 표고는 필지 내 미세지형을 분해하지 못함 → confidence 낮춤 + note 경고.
"정밀 측량/검증된 토목설계 아님"을 항상 명시한다.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any, Optional

import httpx
import numpy as np
import structlog

logger = structlog.get_logger()

# ── DEM 소스 상수 ──
OPENTOPO_URL = "https://api.opentopodata.org/v1/srtm30m"
DEM_RESOLUTION_M = 30.0  # SRTM 30m 명목 해상도
DEM_CELL_AREA_SQM = DEM_RESOLUTION_M * DEM_RESOLUTION_M  # ≈900㎡
ELEVATION_SOURCE = "OpenTopoData SRTM 30m (공개 무료, NASA SRTM)"
SOURCES = [
    "좌표·필지: VWorld(국토교통부 공간정보 오픈플랫폼)",
    "표고(DEM): OpenTopoData SRTM 30m — api.opentopodata.org",
]

# ── 격자 크기 (홀수 권장: 중심 셀 보장) ──
GRID_N = 11  # 11x11 = 121점 (OpenTopoData 단일배치 100점 초과 가능 → 분할)
DEM_BATCH = 100  # OpenTopoData 1req 최대 점수
DEM_TIMEOUT_S = 25.0  # DEM 일괄질의 가드


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 WGS84 좌표 간 거리(m)."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _ring_coords(geometry: dict | None) -> list[tuple[float, float]]:
    """GeoJSON geometry → 외곽 ring 좌표 [(lon,lat), ...]. 실패시 빈 리스트."""
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


def _bbox_of(ring: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """ring → (min_lon, min_lat, max_lon, max_lat)."""
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    return min(lons), min(lats), max(lons), max(lats)


def _polygon_area_sqm(ring: list[tuple[float, float]]) -> float:
    """WGS84 ring 면적(㎡) — 평면 근사(작은 필지에 충분)."""
    if len(ring) < 3:
        return 0.0
    lat0 = sum(c[1] for c in ring) / len(ring)
    mx = 111_320.0 * math.cos(math.radians(lat0))
    my = 111_320.0
    pts = [(c[0] * mx, c[1] * my) for c in ring]
    area2 = 0.0
    for i in range(len(pts) - 1):
        area2 += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return abs(area2) / 2.0


# ── 폴리곤 내부 클립(★핵심 정확도 보정) ──
# 경사도·토공 격자는 필지 외접 사각형(bbox)에 깔린다. 비정형(삼각형·L자·사다리꼴) 필지는
# bbox 모서리에 "이웃 필지 지형"이 들어와 평균경사도·토공량을 오염시킨다. 아래 헬퍼로
# 격자점 중 "필지 폴리곤 내부 점"만 골라(마스킹) 집계 대상으로 삼는다.
# shapely 있으면 covers(경계 포함)로 정밀 판정, 없으면 ray-casting 순수함수로 폴백.
_MIN_INTERIOR_PTS = 4  # 폴리곤 내부 격자점이 이보다 적으면 클립 미적용(bbox 근사·신뢰도↓)


def _ray_cast_inside(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """순수 ray-casting 내부판정. ring=[(lon,lat),...](닫힘/열림 무관).

    점에서 수평 반직선을 쏴 폴리곤 변과의 교차 횟수가 홀수면 내부.
    shapely 미설치 환경을 위한 무의존 폴백(외부 라이브러리 없이 동작).
    """
    n = len(ring)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        # 변 (i,j)가 점의 위도(lat)를 가로지르는가 + 교차 x가 점의 우측인가
        if (yi > lat) != (yj > lat):
            denom = (yj - yi)
            if denom != 0.0:
                x_cross = xi + (lat - yi) / denom * (xj - xi)
                if lon < x_cross:
                    inside = not inside
        j = i
    return inside


def _polygon_interior_mask(
    lat_axis: np.ndarray, lon_axis: np.ndarray, ring: list[tuple[float, float]]
) -> np.ndarray | None:
    """격자점(row=lat, col=lon)이 필지 폴리곤 내부인지 bool 마스크. 경계점 포함.

    ring이 유효하지 않으면 None(호출측은 클립 미적용=현행 bbox 동작 유지).

    경계 규칙: shapely 경로는 covers(경계=내부)로 판정한다. ray-casting 폴백은
    변 위 점(경계) 판정이 규칙상 미세 상이할 수 있으나, 프로드 venv는 shapely 2.0.6
    단일경로이고 실좌표(float) 격자점이 폴리곤 변에 정확히 얹힐 확률은 0에 수렴하므로
    실사용 발산은 무시가능(폴백은 shapely 미설치 환경 안전망).
    """
    if not ring or len(ring) < 3:
        return None
    n_r, n_c = int(lat_axis.size), int(lon_axis.size)
    mask = np.zeros((n_r, n_c), dtype=bool)

    # 1) shapely 우선(정밀·경계 일관). 지연 import — 미설치 환경 가드(코드베이스 관행).
    poly = None
    try:
        from shapely.geometry import Point as _Pt, Polygon as _Poly

        poly = _Poly(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)  # self-touching/자가교차 복구
    except Exception:  # noqa: BLE001 — shapely 부재/불량 폴리곤 → ray-casting 폴백
        poly = None

    for r in range(n_r):
        la = float(lat_axis[r])
        for c in range(n_c):
            lo = float(lon_axis[c])
            if poly is not None:
                try:
                    mask[r, c] = bool(poly.covers(_Pt(lo, la)))  # covers=경계 포함
                except Exception:  # noqa: BLE001
                    mask[r, c] = _ray_cast_inside(lo, la, ring)
            else:
                mask[r, c] = _ray_cast_inside(lo, la, ring)
    return mask


async def _fetch_dem(points: list[tuple[float, float]]) -> Optional[list[float | None]]:
    """OpenTopoData SRTM30m 일괄질의. points=[(lat,lon),...] → [elev_m|None,...].

    100점/req 제한 → 분할. asyncio.wait_for 가드. 전부 실패시 None.
    """
    if not points:
        return None

    async def _one_batch(client: httpx.AsyncClient, batch: list[tuple[float, float]]):
        locs = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in batch)
        resp = await client.get(OPENTOPO_URL, params={"locations": locs})
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "OK":
            raise ValueError(f"OpenTopoData status={data.get('status')}")
        out: list[float | None] = []
        for r in data.get("results", []):
            e = r.get("elevation")
            out.append(float(e) if e is not None else None)
        return out

    try:
        async def _run():
            results: list[float | None] = []
            async with httpx.AsyncClient(timeout=20.0) as client:
                batches = [points[i:i + DEM_BATCH] for i in range(0, len(points), DEM_BATCH)]
                for idx, batch in enumerate(batches):
                    if idx > 0:
                        await asyncio.sleep(1.05)  # 1req/s 제한 준수
                    results.extend(await _one_batch(client, batch))
            return results

        return await asyncio.wait_for(_run(), timeout=DEM_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001
        logger.error("DEM 일괄질의 실패: %s", str(e)[:300])
        return None


def _slope_class(mean_pct: float) -> str:
    if mean_pct < 5:
        return "평지"
    if mean_pct < 15:
        return "완경사"
    if mean_pct < 30:
        return "경사"
    return "급경사"


def _aspect_to_compass(deg: float) -> str:
    dirs = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"]
    return dirs[int((deg + 22.5) % 360 // 45)]


def _compute_slope(
    grid: np.ndarray, dx_m: float, dy_m: float,
    interior_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """격자 표고(grid[row=lat, col=lon]) → 경사율(%)·aspect.

    중앙차분으로 dz/dx, dz/dy 산출. slope_pct = sqrt(gx²+gy²)*100.
    aspect: 내리막 방향(downhill) 방위각(deg, 북=0, 시계방향).

    interior_mask: 필지 폴리곤 내부 격자점 bool 마스크(있으면). 기울기(gradient)는
    이웃점이 필요하므로 전체 격자에서 계산하되, 평균/최대/향은 "폴리곤 내부 점"만
    집계해 이웃 필지 지형 혼입을 차단한다. 내부 점이 너무 적으면 bbox 전체로 폴백.
    """
    # np.gradient: axis0=row(북→남 진행), axis1=col(서→동 진행)
    gz_dy, gz_dx = np.gradient(grid, dy_m, dx_m)
    # grid row 0 = 최북단. lat 증가방향이 row 감소이므로 북향 기울기 부호 보정.
    slope_ratio = np.sqrt(gz_dx ** 2 + gz_dy ** 2)
    slope_pct = slope_ratio * 100.0
    finite = np.isfinite(slope_pct)

    # 폴리곤 내부 클립: bbox 격자점 중 필지 내부 점만 평균·최대·향에 반영.
    clip_applied = False
    interior_pts: int | None = None
    sel = finite
    if interior_mask is not None and interior_mask.shape == slope_pct.shape:
        inside = finite & interior_mask
        interior_pts = int(np.sum(inside))
        if interior_pts >= _MIN_INTERIOR_PTS:
            sel = inside
            clip_applied = True
        # 내부 점 부족(비정형 소필지 등) → bbox 전체로 폴백(신뢰도는 호출측에서 하향)

    valid = slope_pct[sel]
    if valid.size == 0:
        return {
            "mean_pct": 0.0, "max_pct": 0.0, "aspect_deg": None,
            "class": "평지", "detail": "표고 분해 불가",
            "clip_applied": False, "interior_pts": interior_pts,
            "grid_pts": int(np.sum(finite)),
        }
    mean_pct = float(np.mean(valid))
    max_pct = float(np.max(valid))
    # aspect(내리막): -gradient 방향. gz_dx=동향증분, gz_dy=row증분(북→남)
    # 동쪽성분 = -gz_dx, 북쪽성분 = +gz_dy (row 증가=남쪽이므로 북향=+gz_dy)
    # 선택 셀(sel)만 평균 — NaN 배제 + 폴리곤 내부 일관.
    east = -float(np.mean(gz_dx[sel]))
    north = float(np.mean(gz_dy[sel]))
    if abs(east) < 1e-9 and abs(north) < 1e-9:
        aspect_deg = None
    else:
        aspect_deg = (math.degrees(math.atan2(east, north)) + 360) % 360
    cls = _slope_class(mean_pct)
    clip_note = f" (필지 폴리곤 내부 {interior_pts}점 기준·이웃 지형 제외)" if clip_applied else ""
    if aspect_deg is not None:
        detail = (
            f"평균경사 {mean_pct:.1f}% / 최대 {max_pct:.1f}% — {cls}. "
            f"주 사면 향: {_aspect_to_compass(aspect_deg)}({aspect_deg:.0f}°).{clip_note}"
        )
    else:
        detail = f"평균경사 {mean_pct:.1f}% / 최대 {max_pct:.1f}% — {cls}. 사면 향 불명확(평탄).{clip_note}"
    return {
        "mean_pct": round(mean_pct, 2),
        "max_pct": round(max_pct, 2),
        "aspect_deg": round(aspect_deg, 1) if aspect_deg is not None else None,
        "class": cls,
        "detail": detail,
        "clip_applied": clip_applied,
        "interior_pts": interior_pts,
        "grid_pts": int(np.sum(finite)),
    }


def _compute_earthwork(
    grid: np.ndarray, cell_area_sqm: float, target_level_m: float | None,
    interior_mask: np.ndarray | None = None,
) -> dict[str, Any]:
    """base_level 기준 셀별 (elev-base)*셀면적 → 절토(+)/성토(-).

    interior_mask: 필지 폴리곤 내부 셀만 집계(경사도와 동일한 bbox 결함 차단 —
    비정형 필지는 이웃 지형의 절/성토가 물량에 섞인다). 내부 셀이 너무 적으면 bbox 폴백.
    """
    finite = np.isfinite(grid)
    sel = finite
    if interior_mask is not None and interior_mask.shape == grid.shape:
        inside = finite & interior_mask
        if int(np.sum(inside)) >= _MIN_INTERIOR_PTS:
            sel = inside  # 폴리곤 내부 셀만 base·절/성토 산정
    valid = grid[sel]
    if valid.size == 0:
        return {
            "base_level_m": 0.0, "cut_volume_m3": 0.0, "fill_volume_m3": 0.0,
            "net_m3": 0.0, "balance": "균형", "detail": "표고 데이터 없음",
        }
    base = float(target_level_m) if target_level_m is not None else float(np.mean(valid))
    diff = grid - base  # >0: 계획고보다 높음 → 깎아야 함(절토)
    diff = np.where(sel, diff, 0.0)  # 폴리곤 내부(=sel) 셀만 물량 합산, 그 외 0
    cut = float(np.sum(np.where(diff > 0, diff, 0.0)) * cell_area_sqm)   # 절토량
    fill = float(np.sum(np.where(diff < 0, -diff, 0.0)) * cell_area_sqm)  # 성토량
    net = cut - fill  # >0: 잔토(절토우세), <0: 부족토(성토우세)
    if abs(net) < max(cut, fill, 1.0) * 0.1:
        balance = "균형"
    elif net > 0:
        balance = "절토우세"
    else:
        balance = "성토우세"
    base_note = "사용자 계획고" if target_level_m is not None else "필지 평균표고"
    detail = (
        f"기준고(base) {base:.1f}m({base_note}) 기준 — "
        f"절토 {cut:,.0f}㎥ / 성토 {fill:,.0f}㎥ / 순(잔토-부족) {net:,.0f}㎥ → {balance}. "
        f"개략 추정(SRTM 30m 격자), 실제 토공 설계·다짐/팽창률 미반영."
    )
    return {
        "base_level_m": round(base, 2),
        "cut_volume_m3": round(cut, 1),
        "fill_volume_m3": round(fill, 1),
        "net_m3": round(net, 1),
        "balance": balance,
        "detail": detail,
    }


def _compute_cross_section(
    grid: np.ndarray,
    lat_axis: np.ndarray,
    lon_axis: np.ndarray,
    center_lat: float,
    center_lon: float,
    bearing_deg: float | None,
    slope_aspect_deg: float | None,
) -> dict[str, Any]:
    """중심 통과 직선 단면 프로필. bearing 미지정시 최대경사방향(=aspect 역방향).

    bearing_deg: 단면 진행 방위(북=0, 시계방향). 격자 bbox 내 직선을 샘플링.
    """
    if bearing_deg is None:
        # 최대경사선 방향 = 사면 향(내리막) 방향. 없으면 동서(90°).
        bearing_deg = slope_aspect_deg if slope_aspect_deg is not None else 90.0
    bearing_deg = float(bearing_deg) % 360.0

    min_lat, max_lat = float(lat_axis.min()), float(lat_axis.max())
    min_lon, max_lon = float(lon_axis.min()), float(lon_axis.max())
    # bbox 대각선 길이를 단면 최대 길이로 사용
    diag_m = _haversine_m(min_lat, min_lon, max_lat, max_lon)
    half = diag_m / 2.0
    n_samples = 31
    # 방위각 → 단위벡터(동, 북)
    east_u = math.sin(math.radians(bearing_deg))
    north_u = math.cos(math.radians(bearing_deg))
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(center_lat))

    pts: list[tuple[float, float]] = []  # (lat, lon, dist) 샘플
    sample_meta = []
    for i in range(n_samples):
        d = -half + (diag_m * i / (n_samples - 1))  # -half..+half
        dlat = (north_u * d) / m_per_deg_lat
        dlon = (east_u * d) / m_per_deg_lon
        lat = center_lat + dlat
        lon = center_lon + dlon
        # bbox 클램프
        if lat < min_lat or lat > max_lat or lon < min_lon or lon > max_lon:
            continue
        sample_meta.append((d + half, lat, lon))

    # 격자 보간으로 표고 산출 (가장 가까운 격자점)
    points_out = []
    elevs = []
    for dist_m, lat, lon in sample_meta:
        ri = int(np.argmin(np.abs(lat_axis - lat)))
        ci = int(np.argmin(np.abs(lon_axis - lon)))
        e = grid[ri, ci]
        if not np.isfinite(e):
            continue
        points_out.append({"dist_m": round(float(dist_m), 1), "elev_m": round(float(e), 1)})
        elevs.append(float(e))

    if not elevs:
        return {
            "bearing_deg": round(bearing_deg, 1), "length_m": round(diag_m, 1),
            "points": [], "min_elev_m": 0.0, "max_elev_m": 0.0, "relief_m": 0.0,
        }
    return {
        "bearing_deg": round(bearing_deg, 1),
        "length_m": round(points_out[-1]["dist_m"] - points_out[0]["dist_m"], 1) if len(points_out) > 1 else 0.0,
        "points": points_out,
        "min_elev_m": round(min(elevs), 1),
        "max_elev_m": round(max(elevs), 1),
        "relief_m": round(max(elevs) - min(elevs), 1),
    }


def _confidence(
    area_sqm: float | None, valid_pts: int, total_pts: int,
    slope_clip: dict | None = None,
) -> tuple[float, str]:
    """필지면적 대비 DEM 해상도 + 유효표고 비율 + 폴리곤 클립 여부로 신뢰도 산정.

    slope_clip: _compute_slope가 돌려준 {clip_applied, interior_pts} — 폴리곤 있으나
    내부 격자점이 적어 클립을 못 걸면(bbox 근사) 신뢰도를 낮추고 사유를 note한다.
    """
    notes = ["참고용(EXPERIMENTAL): SRTM 30m 광역 표고 기반 — 정밀 측량/검증된 토목설계가 아님."]
    base = 0.6
    if total_pts > 0:
        ratio = valid_pts / total_pts
        base *= ratio
        if ratio < 1.0:
            notes.append(f"표고 취득률 {ratio*100:.0f}% (일부 격자점 누락).")
    if area_sqm is not None and area_sqm > 0:
        cells = area_sqm / DEM_CELL_AREA_SQM
        if area_sqm < DEM_CELL_AREA_SQM:
            base *= 0.4
            notes.append(
                f"필지 {area_sqm:,.0f}㎡가 DEM 1셀(≈{DEM_CELL_AREA_SQM:,.0f}㎡)보다 작아 "
                f"필지 내 미세지형을 분해할 수 없음 → 광역 지형 근사."
            )
        elif cells < 4:
            base *= 0.7
            notes.append(f"필지가 DEM 셀 약 {cells:.1f}개 규모로 작아 경사·토공 분해도가 낮음.")
        else:
            base = min(0.85, base + 0.15)
    else:
        base *= 0.8
        notes.append("필지 폴리곤 미확보 — bbox 근사 격자로 분석(면적 null).")
    # 폴리곤 클립 반영: 내부 점만으로 산정하면 정확도↑, 내부 점 부족 폴백은 정확도↓.
    if isinstance(slope_clip, dict) and area_sqm is not None:
        interior = slope_clip.get("interior_pts")
        if slope_clip.get("clip_applied"):
            # 클립은 걸렸으나 내부 표본이 적으면(4~9점) 평균경사가 노이즈에 취약 → 완만 감점+경고.
            if isinstance(interior, int) and interior < 10:
                base *= 0.85
                notes.append(
                    f"평균경사도는 필지 폴리곤 내부 격자점 {interior}개만 집계(이웃 지형 제외) — "
                    f"표본이 적어 노이즈 가능."
                )
            else:
                notes.append(f"평균경사도는 필지 폴리곤 내부 격자점 {interior}개만 집계(이웃 지형 제외).")
        elif interior is not None:
            base *= 0.7
            notes.append(
                f"필지 폴리곤 내부 격자점이 {interior}개로 적어 bbox 근사로 평균경사 산정(정밀도 낮음)."
            )
    conf = max(0.05, min(0.9, base))
    return round(conf, 2), " ".join(notes)


async def _resolve_location(
    address: str | None, pnu: str | None
) -> Optional[dict[str, Any]]:
    """주소/PNU → {lat, lon, pnu, address, geometry|None}."""
    from app.services.external_api.vworld_service import VWorldService

    svc = VWorldService()
    lat = lon = None
    resolved_pnu = pnu
    resolved_addr = address or ""
    geometry = None

    # 1) PNU 우선: 필지 폴리곤 직접 취득
    if pnu:
        parcel = await svc.get_parcel_by_pnu(pnu)
        if parcel:
            geometry = parcel.get("geometry")
            ring = _ring_coords(geometry)
            if ring:
                lons = [c[0] for c in ring]
                lats = [c[1] for c in ring]
                lon = sum(lons) / len(lons)
                lat = sum(lats) / len(lats)
            props = parcel.get("properties", {})
            resolved_addr = props.get("addr", "") or resolved_addr

    # 2) 주소 지오코딩 (좌표/PNU 미확보 보완)
    if (lat is None or lon is None) and address:
        geo = await svc.geocode_address(address)
        if geo:
            lat, lon = geo["lat"], geo["lon"]
            resolved_pnu = resolved_pnu or geo.get("pnu")
            # PNU 확보되면 폴리곤 재시도
            if resolved_pnu and geometry is None:
                parcel = await svc.get_parcel_by_pnu(resolved_pnu)
                if parcel:
                    geometry = parcel.get("geometry")

    # 3) 좌표만 있고 폴리곤 없으면 점→필지 폴백
    if lat is not None and lon is not None and geometry is None:
        pf = await svc.get_parcel_by_point(lat, lon)
        if pf:
            geometry = pf.get("geometry")
            resolved_pnu = resolved_pnu or pf.get("pnu")
            resolved_addr = resolved_addr or pf.get("address", "")

    if lat is None or lon is None:
        return None
    return {
        "lat": float(lat), "lon": float(lon),
        "pnu": resolved_pnu, "address": resolved_addr, "geometry": geometry,
    }


async def build_terrain_mesh(
    lat: float,
    lon: float,
    half_m: float = 150.0,
    n: int = 21,
) -> Optional[dict[str, Any]]:
    """중심(lat,lon) 기준 ±half_m 정사각 영역의 DEM 격자 → ENU 삼각 메시.

    가상준공 3D 디지털트윈의 지면(terrain) 재료. 기존 SRTM 30m DEM 질의(_fetch_dem)와
    ENU 평면 수식(111320*cos)을 재사용한다. 반환은 Three.js BufferGeometry 친화 형태:
      verts: [[x,y,z], ...]  (x=동, y=표고, z=남(-북). ENU, 단위 m, 원점=중심)
      indices: [...]          (삼각형 3개 인덱스 평탄 배열, 2*(n-1)^2 삼각형)
      elev0: 중심 셀 표고(m), nx/nz: 격자 점 수(=n), bbox_m: 평면 범위

    n=21(권장) → 441점 > 100점/req → _fetch_dem 분할(1req/s) 사용.
    표고 전부 실패시 None. 정직성(해상도/소스/confidence)은 호출측 badges에 위임.
    """
    n = max(3, int(n))
    half_m = float(half_m)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))

    # ENU x(동), z(남=-북) 축 → 위경도 격자. y는 표고.
    xs = np.linspace(-half_m, half_m, n)          # 동(+동), m
    zs = np.linspace(-half_m, half_m, n)          # 남(+남), m
    # 표고 질의 좌표: x=동→lon+, z=남→lat-
    grid_pts: list[tuple[float, float]] = []
    for zv in zs:                                  # row: 북→남 진행(z 증가=남쪽)
        la = lat - (zv / m_per_deg_lat)
        for xv in xs:                              # col: 서→동 진행(x 증가=동쪽)
            lo = lon + (xv / m_per_deg_lon)
            grid_pts.append((float(la), float(lo)))

    elevs = await _fetch_dem(grid_pts)
    if elevs is None or all(e is None for e in elevs):
        return None

    grid = np.full((n, n), np.nan, dtype=float)
    for idx, e in enumerate(elevs):
        r, c = divmod(idx, n)
        if e is not None:
            grid[r, c] = e
    # 결측 보간: 유효 표고 평균으로 채움(메시 연속성 보장)
    finite = np.isfinite(grid)
    valid_pts = int(np.sum(finite))
    if valid_pts == 0:
        return None
    fill = float(np.mean(grid[finite]))
    grid = np.where(finite, grid, fill)

    elev0 = float(grid[n // 2, n // 2])

    # ENU 정점: (x, y=표고, z). numpy 벡터화 후 평탄 리스트.
    xx, zz = np.meshgrid(xs, zs)                   # shape (n,n): zz=row(남), xx=col(동)
    verts_arr = np.stack([xx, grid, zz], axis=-1).reshape(-1, 3)
    verts = [[round(float(p[0]), 3), round(float(p[1]), 3), round(float(p[2]), 3)] for p in verts_arr]

    # 삼각 인덱스(2 tri/cell). 정점 인덱스 = row*n + col.
    rows = np.arange(n - 1)
    cols = np.arange(n - 1)
    cc, rr = np.meshgrid(cols, rows)
    tl = (rr * n + cc).ravel()
    tr = tl + 1
    bl = tl + n
    br = bl + 1
    tri = np.empty((tl.size * 6,), dtype=np.int64)
    tri[0::6] = tl; tri[1::6] = bl; tri[2::6] = tr
    tri[3::6] = tr; tri[4::6] = bl; tri[5::6] = br
    indices = tri.tolist()

    relief = float(np.max(grid) - np.min(grid))
    return {
        "verts": verts,
        "indices": indices,
        "elev0": round(elev0, 2),
        "nx": n,
        "nz": n,
        "bbox_m": {
            "x_min": round(-half_m, 1), "x_max": round(half_m, 1),
            "z_min": round(-half_m, 1), "z_max": round(half_m, 1),
            "half_m": round(half_m, 1),
            "size_m": round(half_m * 2.0, 1),
        },
        "min_elev_m": round(float(np.min(grid)), 2),
        "max_elev_m": round(float(np.max(grid)), 2),
        "relief_m": round(relief, 2),
        "valid_ratio": round(valid_pts / (n * n), 3),
        "source": ELEVATION_SOURCE,
        "resolution_m": DEM_RESOLUTION_M,
    }


async def analyze_terrain(
    address: str | None,
    pnu: str | None,
    target_level_m: float | None,
    section_bearing_deg: float | None,
) -> dict[str, Any]:
    """지형분석 메인. 계약 응답 dict 반환. 좌표/DEM 전부 실패시 ok:false."""
    loc = await _resolve_location(address, pnu)
    if loc is None:
        return {
            "ok": False,
            "message": "주소/PNU로 좌표 또는 필지를 확인하지 못했습니다. 주소 또는 PNU를 확인하세요.",
            "elevation_source": ELEVATION_SOURCE,
            "sources": SOURCES,
        }

    lat, lon = loc["lat"], loc["lon"]
    geometry = loc.get("geometry")
    ring = _ring_coords(geometry)

    # bbox 결정: 폴리곤 있으면 그 bbox, 없으면 좌표 중심 ±약 50m
    if ring:
        min_lon, min_lat, max_lon, max_lat = _bbox_of(ring)
        area_sqm = round(_polygon_area_sqm(ring), 1)
        # 너무 작은 필지면 분석 격자를 최소 1셀(~30m) 이상으로 확장
        span_lat = (max_lat - min_lat) * 111_320.0
        span_lon = (max_lon - min_lon) * 111_320.0 * math.cos(math.radians(lat))
        if span_lat < DEM_RESOLUTION_M or span_lon < DEM_RESOLUTION_M:
            pad_lat = (DEM_RESOLUTION_M / 2) / 111_320.0
            pad_lon = (DEM_RESOLUTION_M / 2) / (111_320.0 * math.cos(math.radians(lat)))
            min_lat -= pad_lat; max_lat += pad_lat
            min_lon -= pad_lon; max_lon += pad_lon
    else:
        area_sqm = None
        half_deg_lat = 50.0 / 111_320.0
        half_deg_lon = 50.0 / (111_320.0 * math.cos(math.radians(lat)))
        min_lat, max_lat = lat - half_deg_lat, lat + half_deg_lat
        min_lon, max_lon = lon - half_deg_lon, lon + half_deg_lon

    # NxN 격자 좌표 생성
    lat_axis = np.linspace(min_lat, max_lat, GRID_N)
    lon_axis = np.linspace(min_lon, max_lon, GRID_N)
    grid_pts: list[tuple[float, float]] = []
    for la in lat_axis:
        for lo in lon_axis:
            grid_pts.append((float(la), float(lo)))

    elevs = await _fetch_dem(grid_pts)
    if elevs is None or all(e is None for e in elevs):
        return {
            "ok": False,
            "message": "표고(DEM) 데이터를 가져오지 못했습니다. (OpenTopoData 일시 장애 가능)",
            "address": loc["address"], "pnu": loc["pnu"],
            "coordinates": {"lat": lat, "lon": lon},
            "elevation_source": ELEVATION_SOURCE,
            "sources": SOURCES,
        }

    # 격자화 (row=lat 오름차순, col=lon 오름차순)
    grid = np.full((GRID_N, GRID_N), np.nan, dtype=float)
    for idx, e in enumerate(elevs):
        r, c = divmod(idx, GRID_N)
        if e is not None:
            grid[r, c] = e
    valid_pts = int(np.sum(np.isfinite(grid)))
    total_pts = GRID_N * GRID_N

    # 격자 셀 간 실거리(m) — 중앙 위도 기준
    dx_m = _haversine_m(lat, min_lon, lat, max_lon) / (GRID_N - 1)
    dy_m = _haversine_m(min_lat, lon, max_lat, lon) / (GRID_N - 1)

    # 폴리곤 내부 클립 마스크: 격자는 필지 bbox에 깔려 있으므로, 비정형 필지의 경사도·
    # 토공 평균에서 이웃 필지 지형이 섞이지 않도록 "필지 폴리곤 내부 격자점"만 마스킹한다.
    # ring 없으면(좌표 중심 bbox 폴백) None → 현행 bbox 동작 유지.
    interior_mask = _polygon_interior_mask(lat_axis, lon_axis, ring) if ring else None

    # 경사도 baseline: 격자 간격이 DEM 해상도보다 촘촘하면 sub-resolution 표고차(정수 m
    # 양자화)로 경사가 비현실적으로 과대해진다. 수평 baseline을 DEM 해상도 이상으로 클램프.
    slope_dx = max(dx_m, DEM_RESOLUTION_M)
    slope_dy = max(dy_m, DEM_RESOLUTION_M)
    slope = _compute_slope(grid, slope_dx, slope_dy, interior_mask=interior_mask)
    cell_area = (dx_m * dy_m) if (dx_m > 0 and dy_m > 0) else DEM_CELL_AREA_SQM
    earthwork = _compute_earthwork(grid, cell_area, target_level_m, interior_mask=interior_mask)
    cross_section = _compute_cross_section(
        grid, lat_axis, lon_axis, lat, lon, section_bearing_deg, slope.get("aspect_deg")
    )
    confidence, note = _confidence(area_sqm, valid_pts, total_pts, slope_clip=slope)

    return {
        "ok": True,
        "address": loc["address"],
        "pnu": loc["pnu"],
        "coordinates": {"lat": round(lat, 6), "lon": round(lon, 6)},
        "elevation_source": ELEVATION_SOURCE,
        "resolution_m": DEM_RESOLUTION_M,
        "sample_count": valid_pts,
        "area_sqm": area_sqm,
        "slope": slope,
        "earthwork": earthwork,
        "cross_section": cross_section,
        "confidence": confidence,
        "note": note,
        "sources": SOURCES,
    }
