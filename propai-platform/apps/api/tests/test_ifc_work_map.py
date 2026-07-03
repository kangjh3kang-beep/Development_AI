"""IFC→공종코드 매핑 테스트."""

from app.services.cost.ifc_work_map import IFC_WORK_MAP, map_ifc_to_work_codes


class TestIFCWorkMap:

    def test_map_count(self):
        assert len(IFC_WORK_MAP) == 16

    def test_wall_mapping(self):
        codes = map_ifc_to_work_codes("IfcWall")
        assert len(codes) == 4
        work_codes = [c[0] for c in codes]
        assert "A01" in work_codes

    def test_door_mapping(self):
        codes = map_ifc_to_work_codes("IfcDoor")
        work_codes = [c[0] for c in codes]
        assert "A05" in work_codes

    def test_window_mapping(self):
        codes = map_ifc_to_work_codes("IfcWindow")
        assert len(codes) >= 2

    def test_pipe_mapping(self):
        codes = map_ifc_to_work_codes("IfcPipeSegment")
        assert codes == [("B01", "배관공사")]

    def test_cable_mapping(self):
        codes = map_ifc_to_work_codes("IfcCableSegment")
        assert codes == [("C01", "전기배선공사")]

    def test_unknown_type_empty(self):
        codes = map_ifc_to_work_codes("IfcUnknown")
        assert codes == []

    def test_all_values_are_tuples(self):
        for _ifc_type, mappings in IFC_WORK_MAP.items():
            for item in mappings:
                assert isinstance(item, tuple)
                assert len(item) == 2
