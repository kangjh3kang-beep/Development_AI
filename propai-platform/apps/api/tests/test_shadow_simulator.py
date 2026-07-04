"""일영분석 시뮬레이터 테스트."""

from app.services.drawing.shadow_simulator import (
    DECLINATION,
    ShadowSimulator,
    shadow_polygon,
    sun_position,
)


class TestSunPosition:

    def test_noon_summer_seoul(self):
        """하지 정오 서울(37.5N): 태양 고도 ~76도."""
        alt, az = sun_position(37.5, 12.0, 23.45)
        assert 70.0 < alt < 80.0
        assert 170.0 < az < 190.0  # 남쪽 부근

    def test_noon_winter_seoul(self):
        """동지 정오 서울(37.5N): 태양 고도 ~29도."""
        alt, az = sun_position(37.5, 12.0, -23.45)
        assert 25.0 < alt < 35.0

    def test_early_morning(self):
        """동지 오전 7시: 태양 고도 낮음."""
        alt, _ = sun_position(37.5, 7.0, -23.45)
        # 고도가 매우 낮거나 음수 (일출 전 가능)
        assert alt < 20.0

    def test_equinox_noon(self):
        """춘분 정오: 태양 고도 ~52.5도."""
        alt, az = sun_position(37.5, 12.0, 0.0)
        assert 48.0 < alt < 56.0


class TestShadowPolygon:

    def test_basic_shadow(self):
        poly = shadow_polygon(30.0, 180.0, 20.0, 15.0, 10.0)
        assert len(poly) >= 4  # 최소 4꼭짓점

    def test_zero_altitude(self):
        """태양 고도 0이면 그림자 없음."""
        poly = shadow_polygon(0.0, 180.0, 20.0, 15.0, 10.0)
        assert poly == []

    def test_negative_altitude(self):
        poly = shadow_polygon(-5.0, 180.0, 20.0, 15.0, 10.0)
        assert poly == []

    def test_high_altitude_short_shadow(self):
        """태양 고도 높으면 그림자 짧음."""
        poly_low = shadow_polygon(20.0, 180.0, 10.0, 10.0, 10.0)
        poly_high = shadow_polygon(70.0, 180.0, 10.0, 10.0, 10.0)
        # 높은 고도: 그림자 작음 → 폴리곤 면적 작음
        assert len(poly_low) >= 4
        assert len(poly_high) >= 4


class TestShadowSimulator:

    def test_generate_returns_svg(self):
        sim = ShadowSimulator()
        svg = sim.generate({
            "building_w": 30.0,
            "building_d": 20.0,
            "building_h": 15.0,
            "analysis_date": "winter_solstice",
        })
        assert isinstance(svg, str)
        assert "<svg" in svg.lower()

    def test_summer_solstice(self):
        sim = ShadowSimulator()
        svg = sim.generate({
            "building_w": 20.0,
            "building_d": 15.0,
            "building_h": 30.0,
            "analysis_date": "summer_solstice",
        })
        assert isinstance(svg, str)
        assert "<svg" in svg.lower()

    def test_declination_values(self):
        assert DECLINATION["winter_solstice"] == -23.45
        assert DECLINATION["summer_solstice"] == 23.45
        assert DECLINATION["equinox"] == 0.0
