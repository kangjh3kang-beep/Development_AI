"""좌표 정합 서비스 — GIS(지도)와 DXF(측량·설계 도면) 좌표를 대조·검증한다.

핵심 흐름(쉬운 말):
1. 기준점 3점 이상으로 '좌표 계약'을 만들어 변환이 얼마나 정확한지(RMSE) 잰다.
2. GIS→DXF→GIS 로 한 바퀴 돌려(왕복) 원래 자리로 잘 돌아오는지 오차를 잰다.
3. 기준(지적) 경계와 DXF 경계의 면적차·중첩률(IoU)을 잰다.
4. 셋 중 하나라도 공차를 넘거나 못 재면 '현장 확인 필요(FIELD_VERIFICATION_REQUIRED)' 로
   정직하게 강등한다(억지 통과 금지).

재사용(재구현 금지):
- 좌표 변환: market/population_density_service.build_crs_transformer (공용 pyproj 헬퍼 확장분).
- DXF 읽기: cad/dxf_import_service 의 도면 리더(경계 폴리라인 추출).
- 경계 기하: shapely(면적·교집합·합집합) — site_layout_service 와 동일한 패턴.

측정 단위 규약: 파이프라인은 m(미터) 그대로 쓰고, 공차 판정만 mm 로 환산한다(A6 참조 규범).
투영(지적)계는 좌표가 곧 미터라 유클리드 거리로, 지리(경위도)계는 측지거리(Geod)로 오차를 잰다.
"""
from __future__ import annotations

import math
from typing import Any

import structlog

from app.services.market.population_density_service import build_crs_transformer
from app.services.survey.coordinate_contract import (
    BoundaryReconcile,
    ControlPoint,
    CoordinateContract,
    ReconcileReport,
    RoundtripResult,
    ToleranceTable,
    TransformTraceEntry,
    VerificationStatus,
)

logger = structlog.get_logger(__name__)

Point = tuple[float, float]
Ring = list[Point]


# ────────────────────────── 좌표계·거리 유틸 ──────────────────────────

def _is_geographic(srid: int) -> bool:
    """해당 SRID 가 경위도(지리)계인지 판별. 실패 시 4326 만 지리로 간주(보수적)."""
    try:
        from pyproj import CRS
        return bool(CRS.from_epsg(srid).is_geographic)
    except Exception:  # noqa: BLE001
        return srid == 4326


def _metric_distance(a: Point, b: Point, srid: int) -> float:
    """두 점 사이 실제 지상거리(m). 지리계는 측지거리(Geod), 투영계는 유클리드."""
    if _is_geographic(srid):
        try:
            from pyproj import Geod
            try:
                from pyproj import CRS
                geod = CRS.from_epsg(srid).get_geod() or Geod(ellps="WGS84")
            except Exception:  # noqa: BLE001
                geod = Geod(ellps="WGS84")
            _, _, dist_m = geod.inv(a[0], a[1], b[0], b[1])
            return abs(float(dist_m))
        except Exception:  # noqa: BLE001
            # pyproj Geod 미가용 — 경위도 차이를 대략 m 로(적도 근사) 환산(정직: 근사 표기).
            return math.hypot(b[0] - a[0], b[1] - a[1]) * 111_320.0
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _transform_ring(ring: Ring, source_srid: int, target_srid: int) -> Ring | None:
    """폴리곤 외곽 좌표들을 source→target 으로 변환. 같은 SRID 는 그대로(항등)."""
    if source_srid == target_srid:
        return [(float(x), float(y)) for x, y in ring]
    tf = build_crs_transformer(source_srid, target_srid)
    if tf is None:
        return None
    out: Ring = []
    for x, y in ring:
        nx, ny = tf.transform(x, y)
        out.append((float(nx), float(ny)))
    return out


def _rms(values: list[float]) -> float:
    """제곱평균제곱근(RMSE) — 오차들의 대표값."""
    if not values:
        return 0.0
    return math.sqrt(sum(v * v for v in values) / len(values))


# ────────────────────────── 1) 좌표 계약(기준점 RMSE) ──────────────────────────

def build_coordinate_contract(
    control_points: list[ControlPoint],
    source_srid: int,
    target_srid: int,
    tolerances: ToleranceTable | None = None,
) -> CoordinateContract:
    """기준점으로 좌표 계약을 만든다 — 변환 정확도(RMSE)와 상태를 판정.

    기준점 3점 미만이거나 pyproj 변환기가 없으면 status=UNAVAILABLE(rmse_mm=None, 사유 기록).
    RMSE 가 공차(control_point_rmse_mm) 이내면 VERIFIED, 넘으면 FIELD_VERIFICATION_REQUIRED.
    ※ target 은 지적(투영)계(미터)를 전제로 mm 환산한다 — WP-C 용례(DXF 지적좌표).
    """
    tol = tolerances or ToleranceTable()
    trace = [
        TransformTraceEntry(
            step="기준점 정합(source→target 변환 후 실측 target 과 잔차 비교)",
            source_srid=source_srid,
            target_srid=target_srid,
        )
    ]
    contract = CoordinateContract(
        source_srid=source_srid,
        target_srid=target_srid,
        control_points=list(control_points),
        transform_trace=trace,
    )

    if len(control_points) < 3:
        contract.status = VerificationStatus.UNAVAILABLE
        contract.notes.append(
            f"기준점 3점 미만({len(control_points)}점) — 정합 판정 불가(정직)."
        )
        return contract

    tf = build_crs_transformer(source_srid, target_srid)
    if tf is None:
        contract.status = VerificationStatus.UNAVAILABLE
        contract.notes.append("pyproj 변환기 미가용 — 정합 판정 불가(정직).")
        return contract

    residuals: list[float] = []
    for cp in control_points:
        px, py = tf.transform(cp.source[0], cp.source[1])
        residuals.append(_metric_distance((px, py), cp.target, target_srid))

    rmse_m = _rms(residuals)
    contract.rmse_mm = round(rmse_m * 1000.0, 4)
    if contract.rmse_mm <= tol.control_point_rmse_mm:
        contract.status = VerificationStatus.VERIFIED
    else:
        contract.status = VerificationStatus.FIELD_VERIFICATION_REQUIRED
        contract.notes.append(
            f"기준점 RMSE {contract.rmse_mm}mm > 공차 {tol.control_point_rmse_mm}mm — 현장 확인 필요."
        )
    return contract


# ────────────────────────── 2) 왕복(GIS→DXF→GIS) 오차 ──────────────────────────

def roundtrip_error(
    points: list[Point],
    source_srid: int,
    target_srid: int,
    tolerances: ToleranceTable | None = None,
    dxf_precision_mm: float = 0.0,
) -> RoundtripResult:
    """GIS→DXF→GIS 왕복 오차를 잰다 — 좌표계·정밀도가 맞으면 사실상 0 에 수렴.

    dxf_precision_mm>0 이면 중간(DXF) 좌표를 그 격자로 반올림해 실측 도면의 좌표 절단 오차를 모사한다.
    rmse_mm·max_error_mm 가 공차 이내면 within_tolerance=True.
    """
    tol = tolerances or ToleranceTable()
    result = RoundtripResult(point_count=len(points), dxf_precision_mm=dxf_precision_mm)

    if not points:
        result.notes.append("입력 좌표 없음 — 왕복 오차 산출 불가.")
        return result

    fwd = build_crs_transformer(source_srid, target_srid)
    inv = build_crs_transformer(target_srid, source_srid)
    if fwd is None or inv is None:
        result.notes.append("pyproj 변환기 미가용 — 왕복 오차 산출 불가(정직).")
        return result

    grid_m = max(dxf_precision_mm, 0.0) / 1000.0  # mm → m 격자
    errors_m: list[float] = []
    for x, y in points:
        tx, ty = fwd.transform(x, y)
        if grid_m > 0:
            tx = round(tx / grid_m) * grid_m
            ty = round(ty / grid_m) * grid_m
        bx, by = inv.transform(tx, ty)
        errors_m.append(_metric_distance((x, y), (bx, by), source_srid))

    result.rmse_mm = round(_rms(errors_m) * 1000.0, 4)
    result.max_error_mm = round(max(errors_m) * 1000.0, 4)
    result.within_tolerance = (
        result.rmse_mm <= tol.roundtrip_rmse_mm
        and result.max_error_mm <= tol.roundtrip_max_mm
    )
    if not result.within_tolerance:
        result.notes.append(
            f"왕복 RMSE {result.rmse_mm}mm / 최대 {result.max_error_mm}mm — 공차 초과."
        )
    return result


# ────────────────────────── 3) 지적경계 대조(면적차·중첩률) ──────────────────────────

def _polygon(ring: Ring) -> Any | None:
    """좌표 링 → shapely Polygon(buffer(0) 로 자가교차 보정). shapely 미가용/무효 시 None."""
    try:
        from shapely.geometry import Polygon
        poly = Polygon(ring).buffer(0)
        if poly.is_empty or poly.area <= 0:
            return None
        return poly
    except Exception:  # noqa: BLE001
        return None


def reconcile_boundary(
    reference_ring: Ring,
    reference_srid: int,
    dxf_ring: Ring,
    dxf_srid: int,
    tolerances: ToleranceTable | None = None,
    compute_srid: int | None = None,
) -> BoundaryReconcile:
    """기준(지적) 경계 vs DXF 경계 — 면적차(%)·중첩률(IoU)을 잰다.

    두 경계를 같은 평면(compute_srid, 기본=dxf_srid — 이미 미터) 으로 옮겨 shapely 로 면적·교집합을 구한다.
    면적차가 공차 이내이고 중첩률이 하한 이상이면 within_tolerance=True.
    """
    tol = tolerances or ToleranceTable()
    csrid = compute_srid if compute_srid is not None else dxf_srid
    out = BoundaryReconcile(computed_in_srid=csrid)

    ref_c = _transform_ring(reference_ring, reference_srid, csrid)
    dxf_c = _transform_ring(dxf_ring, dxf_srid, csrid)
    if ref_c is None or dxf_c is None:
        out.notes.append("좌표 변환기 미가용 — 경계 대조 불가(정직).")
        return out

    ref_poly = _polygon(ref_c)
    dxf_poly = _polygon(dxf_c)
    if ref_poly is None or dxf_poly is None:
        out.notes.append("유효 폴리곤 없음(shapely 미가용/무효 기하) — 경계 대조 불가(정직).")
        return out

    ref_area = float(ref_poly.area)
    dxf_area = float(dxf_poly.area)
    out.reference_area_sqm = round(ref_area, 3)
    out.dxf_area_sqm = round(dxf_area, 3)
    out.area_diff_pct = round(abs(ref_area - dxf_area) / ref_area * 100.0, 4) if ref_area else None

    inter = float(ref_poly.intersection(dxf_poly).area)
    union = float(ref_poly.union(dxf_poly).area)
    out.overlap_ratio = round(inter / union, 6) if union > 0 else 0.0

    out.within_tolerance = bool(
        out.area_diff_pct is not None
        and out.area_diff_pct <= tol.area_diff_pct
        and out.overlap_ratio >= tol.overlap_ratio_min
    )
    if not out.within_tolerance:
        out.notes.append(
            f"면적차 {out.area_diff_pct}% (공차 {tol.area_diff_pct}%) / "
            f"중첩률 {out.overlap_ratio} (하한 {tol.overlap_ratio_min}) — 공차 초과."
        )
    return out


# ────────────────────────── 4) 종합 리포트(DXF 업로드 → 지적경계 대조) ──────────────────────────

def reconcile_report(
    *,
    control_points: list[ControlPoint],
    reference_ring: Ring,
    reference_srid: int,
    dxf_ring: Ring,
    dxf_srid: int,
    source_srid: int | None = None,
    target_srid: int | None = None,
    tolerances: ToleranceTable | None = None,
    dxf_precision_mm: float = 0.0,
) -> ReconcileReport:
    """세 검증(기준점 계약·왕복 오차·경계 대조)을 묶은 종합 리포트.

    하나라도 공차를 넘으면 status=FIELD_VERIFICATION_REQUIRED, 셋 다 못 재면 UNAVAILABLE,
    모두 통과해야 VERIFIED. 왜 현장 확인이 필요한지는 field_verification_reasons 에 남긴다.
    source/target_srid 를 안 주면 계약·왕복 검증은 reference_srid→dxf_srid 로 본다.
    """
    tol = tolerances or ToleranceTable()
    src = source_srid if source_srid is not None else reference_srid
    tgt = target_srid if target_srid is not None else dxf_srid

    contract = build_coordinate_contract(control_points, src, tgt, tol)
    roundtrip = roundtrip_error(
        [cp.source for cp in control_points] or list(reference_ring),
        src, tgt, tol, dxf_precision_mm=dxf_precision_mm,
    )
    boundary = reconcile_boundary(reference_ring, reference_srid, dxf_ring, dxf_srid, tol)

    reasons: list[str] = []
    computed = False

    if contract.status == VerificationStatus.UNAVAILABLE:
        reasons.append("기준점 계약 판정 불가")
    else:
        computed = True
        if contract.status == VerificationStatus.FIELD_VERIFICATION_REQUIRED:
            reasons.append("기준점 RMSE 공차 초과")

    if roundtrip.rmse_mm is None:
        reasons.append("왕복 오차 산출 불가")
    else:
        computed = True
        if not roundtrip.within_tolerance:
            reasons.append("왕복 오차 공차 초과")

    if boundary.reference_area_sqm is None:
        reasons.append("지적경계 대조 불가")
    else:
        computed = True
        if not boundary.within_tolerance:
            reasons.append("면적차/중첩률 공차 초과")

    if not reasons:
        status = VerificationStatus.VERIFIED
    elif computed:
        status = VerificationStatus.FIELD_VERIFICATION_REQUIRED
    else:
        status = VerificationStatus.UNAVAILABLE

    return ReconcileReport(
        status=status,
        tolerances=tol,
        contract=contract,
        roundtrip=roundtrip,
        boundary=boundary,
        field_verification_reasons=reasons,
    )


# ────────────────────────── DXF 업로드 어댑터(경계 링 추출) ──────────────────────────

def extract_dxf_boundary_ring(dxf_bytes: bytes, max_entities: int = 5000) -> Ring | None:
    """업로드된 DXF 에서 지적 좌표(도면 단위) 그대로의 메인 외곽 경계 링을 뽑는다.

    CAD 도면 리더(dxf_import_service)를 재사용해 닫힌 폴리라인 중 최대 면적을 경계로 본다.
    px 정규화(캔버스 좌표)가 아닌 '원좌표'를 반환한다 — 지적계 대조에 필요하기 때문.
    ezdxf 미설치·경계 미검출 시 None(정직 폴백 — 가짜좌표 금지).
    """
    if not dxf_bytes:
        return None
    try:
        from app.services.cad.dxf_import_service import (
            _extract_raw_entities,
            _read_document,
        )
    except Exception:  # noqa: BLE001
        return None
    try:
        doc = _read_document(dxf_bytes)
        raw, _ignored, _truncated = _extract_raw_entities(doc.modelspace(), max_entities)
    except Exception:  # noqa: BLE001 — ezdxf 미설치/파싱 결함은 정직 None
        return None

    best_ring: Ring | None = None
    best_area = 0.0
    for e in raw:
        if e.get("kind") != "polyline" or not e.get("closed"):
            continue
        pts = [(float(x), float(y)) for x, y in e.get("points", [])]
        if len(pts) < 3:
            continue
        # 신발끈 면적(절댓값)으로 최대 외곽 선택.
        n = len(pts)
        area2 = sum(
            pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
            for i in range(n)
        )
        area = abs(area2) / 2.0
        if area > best_area:
            best_area = area
            best_ring = pts
    return best_ring
