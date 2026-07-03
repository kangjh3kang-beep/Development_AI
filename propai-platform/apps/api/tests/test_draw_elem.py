"""DrawElem 데이터클래스 + LAYERS + UNIT_DIMS 테스트."""

from app.services.drawing.draw_elem import LAYERS, UNIT_DIMS, DrawElem


class TestDrawElem:

    def test_create_line(self):
        elem = DrawElem(id="e1", type="LINE", layer="A-WALL",
                        pts=[{"x": 0, "y": 0}, {"x": 10, "y": 0}])
        assert elem.type == "LINE"
        assert len(elem.pts) == 2
        assert elem.layer == "A-WALL"

    def test_create_text(self):
        elem = DrawElem(id="t1", type="TEXT", layer="A-TEXT",
                        text="거실", h=3.0, rot=0.0)
        assert elem.text == "거실"
        assert elem.h == 3.0

    def test_create_circle(self):
        elem = DrawElem(id="c1", type="CIRCLE", layer="A-COLS",
                        cx=5.0, cy=5.0, r=0.3)
        assert elem.cx == 5.0
        assert elem.r == 0.3

    def test_default_values(self):
        elem = DrawElem(id="d1", type="RECT", layer="A-FLOR")
        assert elem.color is None
        assert elem.lw is None
        assert elem.pts == []
        assert elem.props == {}
        assert elem.rot == 0.0


class TestLayers:

    def test_layer_count(self):
        assert len(LAYERS) == 22

    def test_wall_layer(self):
        assert LAYERS["A-WALL"]["c"] == "#000000"
        assert LAYERS["A-WALL"]["w"] == 0.50

    def test_all_have_required_keys(self):
        for name, cfg in LAYERS.items():
            assert "c" in cfg, f"{name} missing color"
            assert "w" in cfg, f"{name} missing weight"
            assert "d" in cfg, f"{name} missing description"


class TestUnitDims:

    def test_unit_count(self):
        assert len(UNIT_DIMS) == 7

    def test_84a(self):
        u = UNIT_DIMS["84A"]
        assert u["w"] == 8.4
        assert u["d"] == 12.5
        assert u["area"] == 84.0

    def test_all_have_required_keys(self):
        for name, dim in UNIT_DIMS.items():
            assert "w" in dim, f"{name} missing width"
            assert "d" in dim, f"{name} missing depth"
            assert "area" in dim, f"{name} missing area"
