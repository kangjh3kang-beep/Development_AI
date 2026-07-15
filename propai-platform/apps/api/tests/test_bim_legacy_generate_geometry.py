"""회귀 테스트 — legacy /api/v1/bim/generate-ifc 의 '빈 IFC' 결함 봉합.

결함(수정 전): BIMIFCService.generate_ifc_from_design 이 IFC 엔티티만 만들고
지오메트리(IfcExtrudedAreaSolid)·물량(IfcElementQuantity)을 전혀 부착하지 않아,
- /api/v1/bim/threejs 렌더 시 빈 지오메트리(create_shape 실패),
- /api/v1/bim/analyze 재분석 시 물량 0 이 되는 사용자 도달 결함.

수정(전역 전파방지): 자체 엔티티 조립을 제거하고 정본 생성기 build_ifc_from_mass
(IfcExtrudedAreaSolid 실압출 + BaseQuantities 부착)로 위임한다.

본 테스트는 legacy 어댑터(_design_params_to_mass)로 만든 매스를 정본 생성기에 넣어
산출된 IFC 를 ifcopenshell 로 재오픈해:
  1) IfcExtrudedAreaSolid(지오메트리) 존재,
  2) IfcElementQuantity(물량) 존재,
  3) 자사 파서 _parse_ifc 재적산 물량 > 0
을 assert 한다 → /threejs·/analyze 가 실데이터를 반환함을 보장.

ifcopenshell 미설치(또는 sys.modules 목 주입) 환경이면 모듈 전체 skip.
"""

from __future__ import annotations

import types

import pytest


def _real_ifcopenshell() -> bool:
    """실설치된 ifcopenshell인지 확인 — sys.modules 목 주입(MagicMock)은 거부."""
    try:
        import ifcopenshell
    except Exception:
        return False
    return isinstance(ifcopenshell, types.ModuleType)


pytestmark = pytest.mark.skipif(
    not _real_ifcopenshell(),
    reason="ifcopenshell 미설치(또는 목 주입) — legacy generate-ifc 지오메트리 회귀 테스트 스킵",
)


# ── legacy generate_ifc_from_design 기본 파라미터(연면적 1000㎡·10층·RC) ──
LEGACY_TOTAL_AREA = 1000.0
LEGACY_FLOORS = 10


@pytest.fixture(scope="module")
def legacy_generated_ifc_path(tmp_path_factory) -> str:
    """legacy 어댑터(_design_params_to_mass) → 정본 build_ifc_from_mass 로 생성한 IFC 파일."""
    from app.services.bim.ifc_generator_service import build_ifc_from_mass
    from apps.api.services.bim_ifc_service import BIMIFCService

    mass = BIMIFCService._design_params_to_mass(
        total_area_sqm=LEGACY_TOTAL_AREA,
        floors=LEGACY_FLOORS,
        structure_type="RC",
    )
    data = build_ifc_from_mass(mass, project_name="legacy-generate-ifc")
    path = tmp_path_factory.mktemp("legacy_ifc") / "legacy.ifc"
    path.write_bytes(data)
    return str(path)


def _open(path: str):
    import ifcopenshell

    return ifcopenshell.open(path)


class TestLegacyGenerateNoLongerHollow:
    def test_adapter_maps_area_floors_to_square_footprint(self):
        """연면적÷층수 → 정사각 한 변(building_width=depth), 층고 3.0 고정."""
        import math

        from apps.api.services.bim_ifc_service import BIMIFCService

        mass = BIMIFCService._design_params_to_mass(1000.0, 10, "RC")
        expected_side = math.sqrt(1000.0 / 10)  # 층당 100㎡ → 한 변 10m
        assert mass["building_width_m"] == pytest.approx(expected_side)
        assert mass["building_depth_m"] == pytest.approx(expected_side)
        assert mass["num_floors"] == 10
        assert mass["floor_height_m"] == pytest.approx(3.0)

    def test_generated_ifc_has_extruded_geometry(self, legacy_generated_ifc_path):
        """지오메트리 존재 — /threejs 빈 지오메트리 결함 봉합(수정 전 IfcExtrudedAreaSolid 0)."""
        ifc = _open(legacy_generated_ifc_path)
        solids = ifc.by_type("IfcExtrudedAreaSolid")
        assert len(solids) > 0, "IfcExtrudedAreaSolid 부재 — 여전히 빈 IFC(threejs 렌더 불가)"
        # 각 슬래브/벽이 Body representation 을 실제 보유(그림자 엔티티 아님).
        for e in ifc.by_type("IfcBuildingElement"):
            assert e.Representation is not None, f"{e.Name}: representation 부재(빈 지오메트리)"

    def test_generated_ifc_has_element_quantities(self, legacy_generated_ifc_path):
        """물량 존재 — /analyze 물량 0 결함 봉합(수정 전 IfcElementQuantity 0)."""
        ifc = _open(legacy_generated_ifc_path)
        assert len(ifc.by_type("IfcElementQuantity")) > 0, (
            "IfcElementQuantity 부재 — analyze 재적산 시 물량 0"
        )

    def test_self_parse_yields_nonzero_quantities(self, legacy_generated_ifc_path):
        """자사 파서(_parse_ifc)가 자기 생성 IFC 를 적산 → 물량 > 0(analyze 응답 정합)."""
        from apps.api.services.bim_ifc_service import BIMIFCService

        # _parse_ifc 는 self 상태 비의존 — db/settings 없이 인스턴스만 구성.
        parser = BIMIFCService.__new__(BIMIFCService)
        result = parser._parse_ifc(legacy_generated_ifc_path)

        assert result["ifc_version"] == "IFC4"
        assert result["element_count"] > 0
        assert result["total_volume_m3"] > 0, "재적산 체적 0 — 물량 부착 실패"
        assert result["total_area_sqm"] > 0, "재적산 면적 0 — 물량 부착 실패"
        # bim_quantities 영속 입력(elements)도 전 요소 물량 > 0(공종매핑 가능).
        assert len(result["elements"]) > 0
        for el in result["elements"]:
            assert el["quantity"] > 0, f"{el['name']}: 물량 0 — 적산 누락"
