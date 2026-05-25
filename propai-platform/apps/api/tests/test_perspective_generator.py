"""투시도 생성기 테스트."""

from app.services.drawing.perspective_generator import PerspectiveGenerator, _iso


class TestIsoProjection:

    def test_origin(self):
        sx, sy = _iso(0, 0, 0, 350, 400, 1.0)
        assert sx == 350.0
        assert sy == 400.0

    def test_z_moves_up(self):
        _, sy0 = _iso(0, 0, 0, 350, 400, 1.0)
        _, sy1 = _iso(0, 0, 10, 350, 400, 1.0)
        assert sy1 < sy0  # z 증가 → SVG y 감소 (위로)

    def test_scale_factor(self):
        sx1, _ = _iso(10, 0, 0, 0, 0, 1.0)
        sx2, _ = _iso(10, 0, 0, 0, 0, 2.0)
        assert abs(sx2) > abs(sx1)  # 스케일 적용


class TestPerspectiveGenerator:

    def test_generate_returns_svg(self):
        gen = PerspectiveGenerator()
        svg = gen.generate({
            "building_w": 30.0,
            "building_d": 20.0,
            "floor_count": 5,
            "floor_height": 3.0,
            "project_name": "테스트빌딩",
        })
        assert isinstance(svg, str)
        assert "<svg" in svg.lower()
        assert "투시도" in svg

    def test_fallback_svg(self):
        svg = PerspectiveGenerator._fallback_svg({
            "project_name": "Fallback",
            "floor_count": 3,
            "floor_height": 3.0,
        })
        assert "<svg" in svg.lower()
        assert "Fallback" in svg

    def test_different_params(self):
        gen = PerspectiveGenerator()
        svg1 = gen.generate({"floor_count": 3})
        svg2 = gen.generate({"floor_count": 10})
        assert isinstance(svg1, str)
        assert isinstance(svg2, str)
