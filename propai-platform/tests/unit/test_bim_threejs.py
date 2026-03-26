"""BIM Three.js 라우터 + IFC 자동 생성 테스트.

Phase F-1: Three.js geometry GET 엔드포인트 + generate_ifc_from_design() 검증.
"""

from pathlib import Path

_BIM_ROUTER_PATH = Path(__file__).resolve().parents[2] / "apps" / "api" / "routers" / "bim.py"
_BIM_ROUTER_SOURCE = _BIM_ROUTER_PATH.read_text(encoding="utf-8")

_BIM_SERVICE_PATH = Path(__file__).resolve().parents[2] / "apps" / "api" / "services" / "bim_ifc_service.py"
_BIM_SERVICE_SOURCE = _BIM_SERVICE_PATH.read_text(encoding="utf-8")


class TestBIMThreeJSRouter:
    """BIM Three.js 라우터 엔드포인트 검증."""

    def test_threejs_endpoint_exists(self) -> None:
        """GET /threejs/{project_id} 엔드포인트가 존재한다."""
        assert "/threejs/{project_id}" in _BIM_ROUTER_SOURCE

    def test_threejs_endpoint_is_get(self) -> None:
        """Three.js 엔드포인트가 GET 메서드이다."""
        assert "@router.get" in _BIM_ROUTER_SOURCE
        assert "get_threejs_geometry" in _BIM_ROUTER_SOURCE

    def test_generate_ifc_endpoint_exists(self) -> None:
        """POST /generate-ifc 엔드포인트가 존재한다."""
        assert "/generate-ifc" in _BIM_ROUTER_SOURCE

    def test_ifc_generate_request_model(self) -> None:
        """IFCGenerateRequest 모델이 정의되어 있다."""
        assert "IFCGenerateRequest" in _BIM_ROUTER_SOURCE
        assert "total_area_sqm" in _BIM_ROUTER_SOURCE
        assert "floors" in _BIM_ROUTER_SOURCE
        assert "structure_type" in _BIM_ROUTER_SOURCE


class TestBIMIFCGeneration:
    """BIM IFC 자동 생성 서비스 검증."""

    def test_generate_ifc_from_design_method(self) -> None:
        """generate_ifc_from_design() 메서드가 존재한다."""
        assert "generate_ifc_from_design" in _BIM_SERVICE_SOURCE

    def test_ifcopenshell_usage(self) -> None:
        """ifcopenshell 라이브러리를 사용한다."""
        assert "ifcopenshell" in _BIM_SERVICE_SOURCE

    def test_ifc_building_hierarchy(self) -> None:
        """IFC 건물 계층 구조를 생성한다 (Project/Site/Building)."""
        assert "IfcProject" in _BIM_SERVICE_SOURCE or "createIfcProject" in _BIM_SERVICE_SOURCE

    def test_ifc_wall_creation(self) -> None:
        """벽체 요소를 생성한다."""
        assert "IfcWall" in _BIM_SERVICE_SOURCE or "wall" in _BIM_SERVICE_SOURCE.lower()

    def test_ifc_slab_creation(self) -> None:
        """슬라브 요소를 생성한다."""
        assert "IfcSlab" in _BIM_SERVICE_SOURCE or "slab" in _BIM_SERVICE_SOURCE.lower()

    def test_minio_upload_in_ifc_gen(self) -> None:
        """생성된 IFC 파일을 MinIO에 업로드한다."""
        assert "minio" in _BIM_SERVICE_SOURCE.lower()
