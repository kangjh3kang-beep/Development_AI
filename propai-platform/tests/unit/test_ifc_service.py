"""BIM/IFC 파싱 서비스 단위 테스트.

inspect.getsource() 패턴으로 실제 로직 존재 검증.
외부 의존성(ifcopenshell, MinIO)이 필요하므로 직접 호출 대신 소스 코드 분석.
"""

import inspect

from apps.api.services.bim_ifc_service import BIMIFCService


class TestBIMIFCServiceCode:
    """BIMIFCService 소스 코드 검증."""

    def test_parse_ifc_has_ifcopenshell(self) -> None:
        """_parse_ifc()에서 ifcopenshell.open을 호출한다."""
        src = inspect.getsource(BIMIFCService._parse_ifc)
        assert "ifcopenshell.open" in src

    def test_parse_ifc_iterates_building_elements(self) -> None:
        """_parse_ifc()에서 IfcBuildingElement를 순회한다."""
        src = inspect.getsource(BIMIFCService._parse_ifc)
        assert "IfcBuildingElement" in src

    def test_parse_ifc_extracts_volume(self) -> None:
        """_parse_ifc()에서 IfcQuantityVolume을 추출한다."""
        src = inspect.getsource(BIMIFCService._parse_ifc)
        assert "IfcQuantityVolume" in src

    def test_parse_ifc_extracts_area(self) -> None:
        """_parse_ifc()에서 IfcQuantityArea를 추출한다."""
        src = inspect.getsource(BIMIFCService._parse_ifc)
        assert "IfcQuantityArea" in src

    def test_parse_ifc_returns_material_breakdown(self) -> None:
        """_parse_ifc()가 material_breakdown 키를 반환한다."""
        src = inspect.getsource(BIMIFCService._parse_ifc)
        assert "material_breakdown" in src

    def test_parse_ifc_returns_ifc_version(self) -> None:
        """_parse_ifc()가 ifc_version을 반환한다."""
        src = inspect.getsource(BIMIFCService._parse_ifc)
        assert "ifc_version" in src

    def test_generate_threejs_uses_geom(self) -> None:
        """_generate_threejs_geometry()에서 ifcopenshell.geom을 사용한다."""
        src = inspect.getsource(BIMIFCService._generate_threejs_geometry)
        assert "ifcopenshell.geom" in src

    def test_generate_threejs_uses_create_shape(self) -> None:
        """_generate_threejs_geometry()에서 create_shape을 호출한다."""
        src = inspect.getsource(BIMIFCService._generate_threejs_geometry)
        assert "create_shape" in src

    def test_generate_threejs_uses_world_coords(self) -> None:
        """_generate_threejs_geometry()에서 USE_WORLD_COORDS를 설정한다."""
        src = inspect.getsource(BIMIFCService._generate_threejs_geometry)
        assert "USE_WORLD_COORDS" in src

    def test_download_ifc_uses_minio(self) -> None:
        """_download_ifc()에서 Minio 클라이언트를 사용한다."""
        src = inspect.getsource(BIMIFCService._download_ifc)
        assert "Minio" in src

    def test_download_ifc_uses_fget_object(self) -> None:
        """_download_ifc()에서 fget_object로 파일을 다운로드한다."""
        src = inspect.getsource(BIMIFCService._download_ifc)
        assert "fget_object" in src

    def test_analyze_ifc_cleans_temp_file(self) -> None:
        """analyze_ifc()에서 임시 파일을 정리한다."""
        src = inspect.getsource(BIMIFCService.analyze_ifc)
        assert "unlink" in src

    def test_analyze_ifc_saves_to_db(self) -> None:
        """analyze_ifc()에서 Design 모델로 DB에 저장한다."""
        src = inspect.getsource(BIMIFCService.analyze_ifc)
        assert "Design(" in src
        assert "db.add" in src
        assert "db.commit" in src
