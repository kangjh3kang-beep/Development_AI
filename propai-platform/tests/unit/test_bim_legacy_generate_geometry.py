"""회귀 테스트 — legacy /api/v1/bim/generate-ifc 의 '빈 IFC' 결함 봉합.

결함(수정 전): BIMIFCService.generate_ifc_from_design 이 IFC 엔티티만 만들고
지오메트리(IfcExtrudedAreaSolid)·물량(IfcElementQuantity)을 전혀 부착하지 않아,
- /api/v1/bim/threejs 렌더 시 빈 지오메트리(create_shape 실패),
- /api/v1/bim/analyze 재분석 시 물량 0 이 되는 사용자 도달 결함.

수정(전역 전파방지): 자체 엔티티 조립을 제거하고 정본 생성기 build_ifc_from_mass
(IfcExtrudedAreaSolid 실압출 + BaseQuantities 부착)로 위임한다.

검증 2단계:
1) TestLegacyGenerateNoLongerHollow — legacy 어댑터(_design_params_to_mass)로 만든 매스를
   정본 생성기에 넣어 산출된 IFC 를 ifcopenshell 로 재오픈해 지오메트리·물량 존재를 확인.
2) TestGenerateIfcFromDesignEntrypoint — PR#315 M2 반영: 어댑터/생성기를 따로 부르는 것이
   아니라 실제 진입점 BIMIFCService.generate_ifc_from_design() 자체를 호출해(DB/MinIO만
   목 처리) 응답 계약(BIMQuantityResponse)이 실데이터를 담고 있는지 end-to-end 로 확인.

ifcopenshell 미설치(또는 sys.modules 목 주입) 환경이면 모듈 전체 skip.
propai-platform/tests/ 하위(루트 계약 스위트 — .github/workflows/ci.yml "Run root
contract suite" 단계, working-directory=propai-platform)에 위치(PR#315 M2 반영).
apps/api/tests/ 도 별도 "Run unit tests (apps/api)" 단계로 CI에 수집된다 — 두 스위트
모두 커버되도록 배선을 나눈다.
"""

from __future__ import annotations

import os
import sys
import types
import uuid

import pytest

# apps/api(app.* 임포트) + propai-platform 루트(apps.api.* 임포트) 를 sys.path 에 추가
# (apps/api/tests/conftest.py 와 동일 목적 — 이 파일은 apps/api 밖의 tests/unit/ 에 위치).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "apps", "api"))
sys.path.insert(0, os.path.join(_HERE, "..", ".."))


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
        """연면적÷층수 → 정사각 한 변(building_width=depth), 층고 3.0 고정, RC 벽두께 0.2."""
        import math

        from apps.api.services.bim_ifc_service import BIMIFCService

        mass = BIMIFCService._design_params_to_mass(1000.0, 10, "RC")
        expected_side = math.sqrt(1000.0 / 10)  # 층당 100㎡ → 한 변 10m
        assert mass["building_width_m"] == pytest.approx(expected_side)
        assert mass["building_depth_m"] == pytest.approx(expected_side)
        assert mass["num_floors"] == 10
        assert mass["floor_height_m"] == pytest.approx(3.0)
        # PR#315 M3: 구조형식별 벽두께 분기(RC=0.2)가 매스에 실제로 담긴다.
        assert mass["wall_thickness_m"] == pytest.approx(0.2)

    def test_adapter_non_rc_uses_thinner_wall(self):
        """PR#315 M3 — 비RC 구조는 벽두께 0.15(legacy 분기값)로 사상된다(근사 표기 대신 실반영)."""
        from apps.api.services.bim_ifc_service import BIMIFCService

        mass = BIMIFCService._design_params_to_mass(1000.0, 10, "SRC")
        assert mass["wall_thickness_m"] == pytest.approx(0.15)

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


def _mock_db_with_refresh():
    """Design.add/commit/refresh 만 캡처하는 가짜 비동기 세션(실 DB 비의존)."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock, MagicMock

    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.add_all = MagicMock()
    mock_db.commit = AsyncMock()

    async def _set_attrs(obj):
        if not getattr(obj, "id", None):
            obj.id = uuid.uuid4()
        if not getattr(obj, "created_at", None):
            obj.created_at = datetime.now(tz=UTC)

    mock_db.refresh = AsyncMock(side_effect=_set_attrs)
    return mock_db


class TestGenerateIfcFromDesignEntrypoint:
    """PR#315 M2 — 어댑터/생성기를 개별 호출하는 대신 실제 수정된 엔드포인트 진입점
    (BIMIFCService.generate_ifc_from_design)을 그대로 태워, 응답 계약이 실데이터를
    반환하는지 end-to-end 로 검증한다. DB/MinIO 만 목 처리(무목업 — IFC 생성·재적산은 실행)."""

    @pytest.mark.asyncio
    async def test_generate_ifc_from_design_returns_real_geometry_and_quantities(self):
        from unittest.mock import MagicMock, patch

        from apps.api.services.bim_ifc_service import BIMIFCService

        db = _mock_db_with_refresh()
        svc = BIMIFCService(db=db)
        svc.settings = MagicMock()
        svc.settings.minio_url = "http://localhost:9000"
        svc.settings.minio_access_key = "test"
        svc.settings.minio_secret_key = "test"

        mock_minio = MagicMock()
        mock_minio.bucket_exists.return_value = True
        mock_minio.put_object = MagicMock()

        with patch.dict(
            "sys.modules",
            {"minio": MagicMock(Minio=MagicMock(return_value=mock_minio))},
        ):
            result = await svc.generate_ifc_from_design(
                project_id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                total_area_sqm=LEGACY_TOTAL_AREA,
                floors=LEGACY_FLOORS,
                structure_type="RC",
            )

        # BIMQuantityResponse 계약 — 프론트(ProjectBimWorkspaceClient)가 그대로 소비하는 필드.
        assert result.ifc_version == "IFC4"
        assert result.element_count > 0, "빈 IFC 결함 재발 — element_count 0"
        assert result.total_volume_m3 > 0, "빈 IFC 결함 재발 — total_volume_m3 0"
        assert result.total_area_sqm > 0, "빈 IFC 결함 재발 — total_area_sqm 0"
        assert len(result.material_breakdown) > 0
        # bim_quantities 영속도 실제로 트리거됐다(add_all 호출) — 체인 연결 확인.
        assert db.add_all.call_count == 1
