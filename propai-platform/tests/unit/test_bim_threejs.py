"""BIM Three.js 라우터 + IFC 자동 생성 테스트.

Phase F-1: Three.js geometry GET 엔드포인트 + generate_ifc_from_design() 검증.
"""

from pathlib import Path

_BIM_ROUTER_PATH = Path(__file__).resolve().parents[2] / "apps" / "api" / "routers" / "bim.py"
_BIM_ROUTER_SOURCE = _BIM_ROUTER_PATH.read_text(encoding="utf-8")

_BIM_SERVICE_PATH = Path(__file__).resolve().parents[2] / "apps" / "api" / "services" / "bim_ifc_service.py"
_BIM_SERVICE_SOURCE = _BIM_SERVICE_PATH.read_text(encoding="utf-8")

# PR#315(빈 IFC 결함 봉합): generate_ifc_from_design 은 더 이상 엔티티를 직접 조립하지 않고
# 정본 생성기로 위임한다 — 건물계층/벽/슬래브 생성 로직은 이 파일에 있다.
_IFC_GENERATOR_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps" / "api" / "app" / "services" / "bim" / "ifc_generator_service.py"
)
_IFC_GENERATOR_SOURCE = _IFC_GENERATOR_PATH.read_text(encoding="utf-8")


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
    """BIM IFC 자동 생성 서비스 검증.

    ★PR#315(빈 IFC 결함 봉합): generate_ifc_from_design 은 더 이상 자체 엔티티를 직접
    조립하지 않고 정본 생성기 app.services.bim.ifc_generator_service.build_ifc_from_mass
    로 위임한다(지오메트리·물량 실부착). 건물계층/벽/슬래브 생성 로직은 이제 그 파일에
    있으므로, 각 검증 대상을 위임 호출 존재(bim_ifc_service.py) + 실제 생성 로직 존재
    (ifc_generator_service.py) 양쪽으로 갱신 — legacy 인라인 조립 코드를 그대로 pin 하던
    구버전 문자열 검사는 정본위임 이후 항상 실패하므로(false regression) 교체한다.
    """

    def test_generate_ifc_from_design_method(self) -> None:
        """generate_ifc_from_design() 메서드가 존재한다."""
        assert "generate_ifc_from_design" in _BIM_SERVICE_SOURCE

    def test_generate_ifc_from_design_delegates_to_canonical_generator(self) -> None:
        """빈 IFC 결함 봉합 — 자체 엔티티 조립 대신 정본 생성기(build_ifc_from_mass)로 위임한다."""
        assert "build_ifc_from_mass" in _BIM_SERVICE_SOURCE
        assert "ifc_generator_service" in _BIM_SERVICE_SOURCE

    def test_ifcopenshell_usage(self) -> None:
        """ifcopenshell 라이브러리를 사용한다(정본 생성기 경유)."""
        assert "ifcopenshell" in _BIM_SERVICE_SOURCE or "ifcopenshell" in _IFC_GENERATOR_SOURCE

    def test_ifc_building_hierarchy(self) -> None:
        """IFC 건물 계층 구조를 생성한다 (Project/Site/Building) — 정본 생성기에 위치."""
        assert "IfcProject" in _IFC_GENERATOR_SOURCE
        assert "IfcBuilding" in _IFC_GENERATOR_SOURCE

    def test_ifc_wall_creation(self) -> None:
        """벽체 요소를 생성한다(정본 생성기 — 실 지오메트리 압출 포함, 빈 IFC 결함 봉합 확인)."""
        assert "IfcWall" in _IFC_GENERATOR_SOURCE
        assert "IfcExtrudedAreaSolid" in _IFC_GENERATOR_SOURCE

    def test_ifc_slab_creation(self) -> None:
        """슬라브 요소를 생성한다(정본 생성기)."""
        assert "IfcSlab" in _IFC_GENERATOR_SOURCE

    def test_minio_upload_in_ifc_gen(self) -> None:
        """생성된 IFC 파일을 MinIO에 업로드한다."""
        assert "minio" in _BIM_SERVICE_SOURCE.lower()
