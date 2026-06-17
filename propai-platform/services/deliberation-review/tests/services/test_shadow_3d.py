"""3D 일조/그림자 시뮬(shapely) — 태양위치·그림자 투영·일영 분석·남측 고층 차폐."""

from app.adapters.solar.sun_position import sun_altitude_azimuth
from app.services.sim.shadow_3d import building_shadow, sunlight_analysis


def test_sun_noon_south():
    # 정오(시간각 0) → 방위각 남(180), 고도 양수(서울 동지).
    alt, az = sun_altitude_azimuth(37.5, -23.44, 0.0)
    assert 25 < alt < 32  # 서울 동지 정오 ~29°
    assert abs(az - 180) < 1.0


def test_sun_morning_east_afternoon_west():
    _, az_am = sun_altitude_azimuth(37.5, -23.44, -45.0)  # 오전
    _, az_pm = sun_altitude_azimuth(37.5, -23.44, 45.0)   # 오후
    assert az_am < 180 < az_pm  # 오전 동쪽(<180), 오후 서쪽(>180)


def test_building_shadow_north():
    # 정오 남쪽 태양(az 180) → 그림자는 북(+y)으로. shadow 폴리곤이 footprint보다 북쪽 확장.
    from shapely.geometry import Polygon
    fp = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    shadow = building_shadow(fp, height_m=30.0, sun_alt_deg=30.0, sun_azim_deg=180.0)
    assert shadow.area > fp.area
    assert shadow.bounds[3] > fp.bounds[3]  # 북쪽(max y) 확장


def test_no_shadow_when_sun_down():
    from shapely.geometry import Polygon
    fp = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    assert building_shadow(fp, 30.0, sun_alt_deg=-5.0, sun_azim_deg=180.0) is None


def _square(cx, cy, half):
    return {"type": "Polygon", "coordinates": [[
        [cx - half, cy - half], [cx + half, cy - half],
        [cx + half, cy + half], [cx - half, cy + half], [cx - half, cy - half]]]}


def test_sunlight_open_site_full():
    # 주변 건물 없음 → 종일 일조(sunny 7시간).
    target = _square(127.0, 37.5, 0.0002)
    out = sunlight_analysis(target, [], 37.5)
    assert out["nearby_masses"] == 0
    assert out["sunny_hours_9to15"] == 7.0


def test_sunlight_south_highrise_blocks():
    # 대상지 남측(작은 위도)에 고층(40층≈120m) → 정오 전후 차폐로 일조시간 감소.
    target = _square(127.0, 37.5, 0.0003)
    south = _square(127.0, 37.4985, 0.0004)  # 남쪽(위도 작음)
    buildings = [{"geometry": south, "floors": 40, "height_m": 0}]
    out = sunlight_analysis(target, buildings, 37.5)
    assert out["nearby_masses"] == 1
    assert out["sunny_hours_9to15"] < 7.0  # 남측 고층이 일부 시각 차폐
    assert any(h["shaded_ratio"] > 0 for h in out["per_hour"])
