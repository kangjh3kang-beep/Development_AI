"""MEDIUM 감사: 일조 휴리스틱 정직 라벨(설명가능성).

_is_sun_blocked(2D 평면투영 ±18° 약식 가림)·정북일조 스트립적분(직사각형 대지 근사)이
정밀계산으로 오인되지 않게, 산출 dict에 구조화 메타키(method/limitations·approximation/
assumptions)를 가산한다. 수치·기존 키는 무변경(폴백/회귀 무영향).
"""
from app.services.environment.environment_service import _compute_solar
from app.services.site_score.solar_envelope_service import compute_buildable_envelope


def test_compute_solar_has_honest_method_meta():
    polar = [{"dist_m": 20.0, "azimuth_deg": 180.0, "height_m": 30.0}]
    out = _compute_solar(37.5, 127.0, "제2종일반주거지역", 20, polar, "winter")
    assert out["method"] == "2D-planar-projection"
    assert isinstance(out["limitations"], list) and len(out["limitations"]) >= 3
    # 기존 키·타입 불변(프론트 폴백 회귀 가드)
    for k in ("sun_positions", "sunlight_hours", "sunlight_hours_winter", "grade", "summary"):
        assert k in out


def test_envelope_applies_has_approximation_meta():
    out = compute_buildable_envelope(
        land_area_sqm=660.0, zone="제2종일반주거지역",
        land_width_m=22.0, land_depth_m=30.0,
        bcr_limit_pct=60.0, far_limit_pct=250.0,
    )
    assert out["applies_north_light"] is True
    assert out["approximation"] == "rectangular-lot-strip-integration"
    assert isinstance(out["assumptions"], list) and out["assumptions"]
    # 수치 키 불변(산식 무변경 증명)
    for k in ("effective_gfa_sqm", "daylight_loss_pct", "binding", "max_floors"):
        assert k in out


def test_envelope_non_applies_has_meta():
    out = compute_buildable_envelope(
        land_area_sqm=660.0, zone="일반상업지역",
        bcr_limit_pct=60.0, far_limit_pct=800.0,
    )
    assert out["applies_north_light"] is False
    assert "approximation" in out and "assumptions" in out
