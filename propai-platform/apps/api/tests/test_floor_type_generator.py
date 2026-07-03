"""FloorTypeGenerator 단위 테스트."""

import pytest

from app.services.cad.floor_type_generator import (
    BuildingFloorSet,
    FloorTypeGenerator,
)


@pytest.fixture()
def gen():
    return FloorTypeGenerator()


class TestGenerate:
    def test_returns_building_floor_set(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=7, basement_floors=1)
        assert isinstance(result, BuildingFloorSet)
        # 지하1 + 1F~7F = 8개
        assert len(result.floors) == 8

    def test_floor_labels(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, basement_floors=2)
        labels = [f.label for f in result.floors]
        assert "B2F" in labels
        assert "B1F" in labels
        assert "1F" in labels
        assert "5F" in labels

    def test_piloti_first_floor(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, first_floor_use="piloti")
        first = [f for f in result.floors if f.floor_number == 1][0]
        assert first.floor_type == "piloti"

    def test_commercial_first_floor(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, first_floor_use="commercial")
        first = [f for f in result.floors if f.floor_number == 1][0]
        assert first.floor_type == "commercial"

    def test_standard_first_floor(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, first_floor_use="standard")
        first = [f for f in result.floors if f.floor_number == 1][0]
        assert first.floor_type == "standard"


class TestPenthouse:
    def test_penthouse_floor(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=7, has_penthouse=True)
        last = result.floors[-1]
        assert last.floor_type == "penthouse"
        assert "PH" in last.label

    def test_no_penthouse(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=7, has_penthouse=False)
        last = result.floors[-1]
        assert last.floor_type == "standard"


class TestBasement:
    def test_basement_parking(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, basement_floors=2, parking_count=50)
        basements = [f for f in result.floors if f.floor_number < 0]
        assert len(basements) == 2
        assert all(f.floor_type == "basement_parking" for f in basements)

    def test_basement_has_mechanical_rooms(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, basement_floors=2)
        lowest = [f for f in result.floors if f.floor_number == -2][0]
        room_names = [r.name for r in lowest.rooms]
        assert "기계실" in room_names
        assert "전기실" in room_names


class TestStandardFloor:
    def test_unit_count(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, unit_width_m=8.0)
        standard = [f for f in result.floors if f.floor_type == "standard"]
        for f in standard:
            assert f.unit_count > 0

    def test_has_corridor_and_core(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5, core_count=2)
        standard = [f for f in result.floors if f.floor_type == "standard"][0]
        room_names = [r.name for r in standard.rooms]
        assert "복도" in room_names
        assert any("코어" in n for n in room_names)


class TestUtilities:
    def test_parking_requirement(self, gen: FloorTypeGenerator):
        count = gen.compute_parking_requirement(100, "공동주택")
        assert count == 100

    def test_parking_area(self, gen: FloorTypeGenerator):
        area = gen.compute_underground_parking_area(50, "자주식")
        assert area == 50 * 33.0

    def test_summary(self, gen: FloorTypeGenerator):
        result = gen.generate(30, 15, floor_count=5)
        summary = gen.to_summary(result)
        assert "total_floors" in summary
        assert "floors" in summary
        assert len(summary["floors"]) == len(result.floors)
