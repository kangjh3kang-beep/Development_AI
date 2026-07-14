"""WP-C P5 좌표계약(CoordinateContract) 최소형 — 결정적 합성 기하 테스트.

검증 계약(라이브 API 금지 — 전부 순수 pyproj/shapely 합성 기하):
- ㉘ 공용 변환헬퍼 확장: build_crs_transformer(임의 SRID·양방향)·build_utmk_to_wgs84_transformer 무회귀.
- 왕복(GIS→DXF→GIS) 오차: 4326↔5186/5174/5179 근사영(near-zero)·거친 정밀도 시 공차 초과.
- 좌표 계약: 기준점 부족→UNAVAILABLE·저RMSE→VERIFIED·고RMSE→FIELD_VERIFICATION_REQUIRED.
- 지적경계 대조: 동일→통과·면적차 초과·중첩률(IoU) 미달 경계 케이스.
- 종합 리포트: 전부 통과→VERIFIED·하나라도 초과→FIELD_VERIFICATION_REQUIRED(사유 기록).
"""
from __future__ import annotations

import pytest

# 좌표 변환·기하 라이브러리 없으면 이 스위트는 건너뛴다(CI 환경 정직).
pytest.importorskip("pyproj")
pytest.importorskip("shapely")

from app.services.market.population_density_service import (  # noqa: E402
    build_crs_transformer,
    build_utmk_to_wgs84_transformer,
)
from app.services.survey.coordinate_contract import (  # noqa: E402
    ControlPoint,
    ToleranceTable,
    VerificationStatus,
)
from app.services.survey.coordinate_service import (  # noqa: E402
    build_coordinate_contract,
    reconcile_boundary,
    reconcile_report,
    roundtrip_error,
)

# 서울 인근 WGS84 점 3개(경도,위도) — 기준점·왕복 입력용.
_WGS_POINTS = [
    (126.9779, 37.5663),
    (126.9850, 37.5700),
    (126.9700, 37.5600),
]

# 5186(지적 중부원점) 평면 좌표계 100m 정사각형(면적 10,000㎡).
_SQUARE = [(200000.0, 500000.0), (200100.0, 500000.0),
           (200100.0, 500100.0), (200000.0, 500100.0)]


def _perfect_control_points(source_srid: int, target_srid: int,
                            offset_m: float = 0.0) -> list[ControlPoint]:
    """실제 변환기로 target 을 산출해 잔차 0 인 기준점을 만든다(+offset_m 로 잔차 주입)."""
    tf = build_crs_transformer(source_srid, target_srid)
    cps: list[ControlPoint] = []
    for i, (lon, lat) in enumerate(_WGS_POINTS):
        tx, ty = tf.transform(lon, lat)
        cps.append(ControlPoint(name=f"CP{i+1}", source=(lon, lat),
                                target=(tx + offset_m, ty)))
    return cps


# ── 1. ㉘ 공용 헬퍼 확장·무회귀 ─────────────────────────────────────

def test_build_crs_transformer_generalized_int_and_str():
    """임의 SRID 조합(정수·문자열) 모두 변환기를 만든다."""
    assert build_crs_transformer(4326, 5186) is not None
    assert build_crs_transformer("EPSG:4326", "EPSG:5186") is not None
    assert build_crs_transformer(5186, 4326) is not None  # 역방향


def test_build_crs_transformer_bogus_srid_returns_none():
    """미상 SRID 는 예외 대신 None(정직 폴백 — 가짜좌표 금지)."""
    assert build_crs_transformer(99999999, 4326) is None


def test_utmk_helper_no_regression():
    """기존 build_utmk_to_wgs84_transformer 무회귀 — 5179 점을 한국 경위도 범위로 변환."""
    tf = build_utmk_to_wgs84_transformer()
    assert tf is not None
    lon, lat = tf.transform(958000, 1944000)  # UTM-K 서울 부근
    assert 124.0 < lon < 132.0 and 33.0 < lat < 39.0


# ── 2. 왕복(GIS→DXF→GIS) 오차 ─────────────────────────────────────

@pytest.mark.parametrize("target_srid", [5186, 5179])
def test_roundtrip_near_zero_grs80_family(target_srid: int):
    """4326→지적계(GRS80/Korea2000)→4326 왕복은 무손실 시 엄격 공차 이내(near-zero)."""
    res = roundtrip_error(_WGS_POINTS, 4326, target_srid, dxf_precision_mm=0.0)
    assert res.rmse_mm is not None
    assert res.within_tolerance is True
    assert res.rmse_mm < 1.0


def test_roundtrip_5174_bessel_bounded_and_flagged():
    """★지적계 정밀변환 실증: 5174(Bessel 1841 구지적계) 왕복 잔차는 GRS80 계열과 달리
    0 에 수렴하지 않는다(데이텀 변환 비대칭). 엄격 기본공차(1mm)에선 정직하게 현장확인
    플래그(within_tolerance False)가 뜨고, Bessel 적정공차(20mm)에선 통과한다.
    잔차는 유계(<20mm)여야 한다(쓰레기값 아님)."""
    res_strict = roundtrip_error(_WGS_POINTS, 4326, 5174, dxf_precision_mm=0.0)
    assert res_strict.rmse_mm is not None
    assert 0.0 < res_strict.rmse_mm < 20.0        # 유계(수 mm 수준)
    assert res_strict.within_tolerance is False    # 엄격 기본공차 초과 → 현장확인 플래그

    tol_bessel = ToleranceTable(roundtrip_rmse_mm=20.0, roundtrip_max_mm=20.0)
    res_loose = roundtrip_error(_WGS_POINTS, 4326, 5174, tol_bessel, dxf_precision_mm=0.0)
    assert res_loose.within_tolerance is True      # Bessel 적정공차에선 통과


def test_roundtrip_exceeds_with_coarse_precision():
    """DXF 저장 격자가 거칠면(1m) 왕복 오차가 공차를 초과 → within_tolerance False."""
    res = roundtrip_error(_WGS_POINTS, 4326, 5186, dxf_precision_mm=1000.0)
    assert res.within_tolerance is False
    assert res.max_error_mm is not None and res.max_error_mm > 5.0


def test_roundtrip_empty_points_unavailable():
    """입력 좌표 없으면 산출 불가(정직) — rmse None·미통과."""
    res = roundtrip_error([], 4326, 5186)
    assert res.rmse_mm is None and res.within_tolerance is False


# ── 3. 좌표 계약(기준점 RMSE) ─────────────────────────────────────

def test_contract_insufficient_control_points():
    """기준점 3점 미만 → UNAVAILABLE·rmse None·사유 기록."""
    cps = _perfect_control_points(4326, 5186)[:2]
    contract = build_coordinate_contract(cps, 4326, 5186)
    assert contract.status == VerificationStatus.UNAVAILABLE
    assert contract.rmse_mm is None
    assert any("기준점" in n for n in contract.notes)


def test_contract_verified_low_rmse():
    """잔차 0 기준점 3점 → VERIFIED·RMSE 미소·transform_trace 존재."""
    cps = _perfect_control_points(4326, 5186)
    contract = build_coordinate_contract(cps, 4326, 5186)
    assert contract.status == VerificationStatus.VERIFIED
    assert contract.rmse_mm is not None and contract.rmse_mm < 1.0
    assert len(contract.transform_trace) >= 1


def test_contract_field_verification_on_high_rmse():
    """target 을 0.1m(100mm) 어긋내면 RMSE 공차(50mm) 초과 → FIELD_VERIFICATION_REQUIRED."""
    cps = _perfect_control_points(4326, 5186, offset_m=0.1)
    contract = build_coordinate_contract(cps, 4326, 5186)
    assert contract.status == VerificationStatus.FIELD_VERIFICATION_REQUIRED
    assert contract.rmse_mm is not None and contract.rmse_mm > 50.0


def test_contract_custom_tolerance_flips_to_verified():
    """공차표를 넉넉히(200mm) 덮어쓰면 같은 100mm 잔차가 VERIFIED 로."""
    cps = _perfect_control_points(4326, 5186, offset_m=0.1)
    tol = ToleranceTable(control_point_rmse_mm=200.0)
    contract = build_coordinate_contract(cps, 4326, 5186, tol)
    assert contract.status == VerificationStatus.VERIFIED


# ── 4. 지적경계 대조(면적차·중첩률) ─────────────────────────────────

def test_boundary_identical_pass():
    """동일 경계 → 면적차 0·중첩률 1.0 → within_tolerance True."""
    out = reconcile_boundary(_SQUARE, 5186, _SQUARE, 5186)
    assert out.area_diff_pct == pytest.approx(0.0, abs=1e-6)
    assert out.overlap_ratio == pytest.approx(1.0, abs=1e-6)
    assert out.within_tolerance is True


def test_boundary_area_diff_exceeds():
    """DXF 경계를 110m 정사각형으로 키우면 면적차(21%)>공차 → 미통과."""
    bigger = [(200000.0, 500000.0), (200110.0, 500000.0),
              (200110.0, 500110.0), (200000.0, 500110.0)]
    out = reconcile_boundary(_SQUARE, 5186, bigger, 5186)
    assert out.area_diff_pct is not None and out.area_diff_pct > 3.0
    assert out.within_tolerance is False


def test_boundary_overlap_below_min():
    """DXF 경계를 5m 평행이동하면 면적은 같아도 중첩률(IoU≈0.90)<0.98 → 미통과."""
    shifted = [(200005.0, 500000.0), (200105.0, 500000.0),
               (200105.0, 500100.0), (200005.0, 500100.0)]
    out = reconcile_boundary(_SQUARE, 5186, shifted, 5186)
    assert out.overlap_ratio is not None and out.overlap_ratio < 0.98
    assert out.within_tolerance is False


# ── 5. 종합 리포트 ────────────────────────────────────────────────

def test_reconcile_report_verified():
    """기준점 정확·왕복 무손실·경계 동일 → 종합 VERIFIED·사유 없음."""
    cps = _perfect_control_points(4326, 5186)
    report = reconcile_report(
        control_points=cps,
        reference_ring=_SQUARE, reference_srid=5186,
        dxf_ring=_SQUARE, dxf_srid=5186,
        source_srid=4326, target_srid=5186,
        dxf_precision_mm=0.0,
    )
    assert report.status == VerificationStatus.VERIFIED
    assert report.field_verification_reasons == []


def test_reconcile_report_field_verification_on_boundary_and_precision():
    """경계 어긋남 + 거친 정밀도 → FIELD_VERIFICATION_REQUIRED·사유 다중 기록."""
    cps = _perfect_control_points(4326, 5186)
    shifted = [(200005.0, 500000.0), (200105.0, 500000.0),
               (200105.0, 500100.0), (200005.0, 500100.0)]
    report = reconcile_report(
        control_points=cps,
        reference_ring=_SQUARE, reference_srid=5186,
        dxf_ring=shifted, dxf_srid=5186,
        source_srid=4326, target_srid=5186,
        dxf_precision_mm=1000.0,
    )
    assert report.status == VerificationStatus.FIELD_VERIFICATION_REQUIRED
    assert len(report.field_verification_reasons) >= 2


def test_dxf_boundary_ring_extraction_roundtrip():
    """ezdxf 로 닫힌 정사각형 DXF 를 만들어 원좌표 경계 링을 되뽑는다(px 정규화 아님)."""
    ezdxf = pytest.importorskip("ezdxf")
    from app.services.survey.coordinate_service import extract_dxf_boundary_ring

    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline([(p[0], p[1]) for p in _SQUARE], close=True)
    import io
    buf = io.StringIO()
    doc.write(buf)
    dxf_bytes = buf.getvalue().encode("utf-8")

    ring = extract_dxf_boundary_ring(dxf_bytes)
    assert ring is not None and len(ring) >= 4
    # 원좌표(지적계 미터) 보존 — 첫 점이 5186 좌표 범위.
    assert abs(ring[0][0] - 200000.0) < 1.0 and abs(ring[0][1] - 500000.0) < 1.0
