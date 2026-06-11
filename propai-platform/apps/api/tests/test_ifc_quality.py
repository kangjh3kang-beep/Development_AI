"""R4′ IFC 품질 보강 회귀 테스트 — Pset/BaseQuantities 부착 + 자가 적산 루프.

검증 범위:
1) IfcGeneratorService.generate 산출 IFC를 ifcopenshell로 재파싱해
   모든 IfcBuildingElement에 IfcElementQuantity(BaseQuantities)가 부착됐는지,
   수치가 입력 치수와 정합하는지(벽 Length=입력 폭/깊이 등) 정답값 고정.
2) 벽(IfcWall/IfcWallStandardCase)의 Pset_WallCommon(LoadBearing·IsExternal).
3) 자가 적산 루프: 자사 파서 BIMIFCService._parse_ifc(수정 금지 — 계약만 충족)가
   자기 생성 IFC를 그대로 적산 — 집계 정답값(total_volume/total_area/element_count) 고정.
4) additive 회귀: Qto/Pset 부착이 제품 요소 수·SPF 헤더를 바꾸지 않음.

ifcopenshell 미설치(또는 sys.modules 목 주입 오염) 환경이면 모듈 전체 skip.
정답값 근거(최소 모델 20×10m·2층·층고3.0·벽0.2·슬래브0.2):
- 슬래브: NetArea=200, NetVolume=40 (×2층 → 400/80)
- 외벽 S/N: Length=20, NetSideArea=60, NetVolume=12 / W·E: 10/30/6
- 합계: element_count=10, total_volume=152, total_area=760
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
    reason="ifcopenshell 미설치(또는 목 주입) — IFC 생성·재파싱 왕복 테스트 스킵",
)


# ── 생성 파라미터(정답값의 입력 치수) ──

MINIMAL_KW = dict(
    building_width_m=20.0,
    building_depth_m=10.0,
    num_floors=2,
    floor_height_m=3.0,
    project_name="QTO-최소모델",
    wall_thickness_m=0.2,
    slab_thickness_m=0.2,
)

FULL_KW = dict(
    building_width_m=20.0,
    building_depth_m=10.0,
    num_floors=2,
    floor_height_m=3.0,
    project_name="QTO-전체모델",
    wall_thickness_m=0.2,
    slab_thickness_m=0.2,
    cores=[{"x": 10.0, "y": 5.0}],
    core_size_m=5.0,
    corridor_width_m=2.0,
    windows_per_side=2,
    unit_width_m=5.0,
    balconies=True,
    unit_doors=True,
)

# 전체 모델 요소 수(부착 전과 동일해야 함 — additive 회귀 고정):
# 1F: 슬래브1+외벽4+코어벽4+계단2+복도1 = 12
# 2F: 12 + 창4 + 칸막이4 + 발코니3 + 현관문6 = 29  →  합계 41
FULL_MODEL_ELEMENT_COUNT = 41


def _generate_to_file(tmp_path_factory, filename: str, kwargs: dict) -> str:
    from app.services.bim.ifc_generator_service import IfcGeneratorService

    data = IfcGeneratorService().generate(**kwargs)
    path = tmp_path_factory.mktemp("ifc_quality") / filename
    path.write_bytes(data)
    return str(path)


@pytest.fixture(scope="module")
def minimal_ifc_path(tmp_path_factory) -> str:
    """최소 모델(슬래브+외벽만) — 코어/복도/창/세대 없음."""
    return _generate_to_file(tmp_path_factory, "minimal.ifc", MINIMAL_KW)


@pytest.fixture(scope="module")
def full_ifc_path(tmp_path_factory) -> str:
    """전체 모델 — 코어·복도·창호·세대 칸막이·발코니·현관문 포함."""
    return _generate_to_file(tmp_path_factory, "full.ifc", FULL_KW)


# ── 재파싱 헬퍼 ──


def _open(path: str):
    import ifcopenshell

    return ifcopenshell.open(path)


def _quantity_sets(element) -> list:
    out = []
    for rel in element.IsDefinedBy:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pd = rel.RelatingPropertyDefinition
        if pd.is_a("IfcElementQuantity"):
            out.append(pd)
    return out


def _quantity_map(element) -> dict[str, float]:
    """요소의 IfcElementQuantity들에서 {물량명: 값} 추출."""
    out: dict[str, float] = {}
    for eq in _quantity_sets(element):
        for q in eq.Quantities:
            if q.is_a("IfcQuantityLength"):
                out[q.Name] = float(q.LengthValue)
            elif q.is_a("IfcQuantityArea"):
                out[q.Name] = float(q.AreaValue)
            elif q.is_a("IfcQuantityVolume"):
                out[q.Name] = float(q.VolumeValue)
    return out


def _pset_map(element, pset_name: str) -> dict[str, object] | None:
    """요소의 IfcPropertySet(pset_name)에서 {속성명: wrappedValue} 추출."""
    for rel in element.IsDefinedBy:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pd = rel.RelatingPropertyDefinition
        if pd.is_a("IfcPropertySet") and pd.Name == pset_name:
            return {p.Name: p.NominalValue.wrappedValue for p in pd.HasProperties}
    return None


def _by_name(ifc, ifc_class: str, name: str):
    for e in ifc.by_type(ifc_class):
        if e.Name == name:
            return e
    raise AssertionError(f"{ifc_class} '{name}' 요소가 IFC에 없음")


# ═══════════════════════════════════════════════
# 1. ElementQuantity 존재 + 입력 치수 정합(정답값 고정)
# ═══════════════════════════════════════════════


class TestElementQuantityAttachment:
    def test_every_building_element_has_base_quantities(self, minimal_ifc_path):
        ifc = _open(minimal_ifc_path)
        elements = ifc.by_type("IfcBuildingElement")
        assert len(elements) == 10  # 2층 × (슬래브1 + 외벽4)
        for e in elements:
            eqs = _quantity_sets(e)
            assert len(eqs) == 1, f"{e.Name}: IfcElementQuantity 1개여야 함"
            assert eqs[0].MethodOfMeasurement == "BaseQuantities"
            # 파서 결정성 계약: 면적·체적 물량은 요소당 각 1개(덮어쓰기 방지)
            areas = [q for q in eqs[0].Quantities if q.is_a("IfcQuantityArea")]
            vols = [q for q in eqs[0].Quantities if q.is_a("IfcQuantityVolume")]
            assert len(areas) == 1, f"{e.Name}: IfcQuantityArea 1개여야 함"
            assert len(vols) == 1, f"{e.Name}: IfcQuantityVolume 1개여야 함"

    def test_wall_quantities_match_input_dimensions(self, minimal_ifc_path):
        ifc = _open(minimal_ifc_path)
        # 남측(S) 외벽: 길이 = 입력 building_width_m(20.0)
        qm = _quantity_map(_by_name(ifc, "IfcWall", "1F-Wall-S"))
        assert qm["Length"] == pytest.approx(20.0)
        assert qm["Height"] == pytest.approx(3.0)
        assert qm["Width"] == pytest.approx(0.2)
        assert qm["NetSideArea"] == pytest.approx(60.0)   # 20 × 3
        assert qm["NetVolume"] == pytest.approx(12.0)     # 20 × 0.2 × 3
        # 동측(E) 외벽: 길이 = 입력 building_depth_m(10.0)
        qm_e = _quantity_map(_by_name(ifc, "IfcWall", "1F-Wall-E"))
        assert qm_e["Length"] == pytest.approx(10.0)
        assert qm_e["NetSideArea"] == pytest.approx(30.0)  # 10 × 3
        assert qm_e["NetVolume"] == pytest.approx(6.0)     # 0.2 × 10 × 3

    def test_slab_quantities_match_footprint(self, minimal_ifc_path):
        ifc = _open(minimal_ifc_path)
        qm = _quantity_map(_by_name(ifc, "IfcSlab", "2F-Slab"))
        assert qm["NetArea"] == pytest.approx(200.0)      # 20 × 10
        assert qm["NetVolume"] == pytest.approx(40.0)     # 200 × 0.2
        assert qm["Width"] == pytest.approx(0.2)          # 슬래브 두께
        assert qm["Perimeter"] == pytest.approx(60.0)     # 2 × (20+10)

    def test_pset_wall_common_on_exterior_wall(self, minimal_ifc_path):
        ifc = _open(minimal_ifc_path)
        pm = _pset_map(_by_name(ifc, "IfcWall", "1F-Wall-S"), "Pset_WallCommon")
        assert pm is not None, "외벽에 Pset_WallCommon 부재"
        assert pm["LoadBearing"] is True
        assert pm["IsExternal"] is True


# ═══════════════════════════════════════════════
# 2. 자가 적산 루프 — 자사 파서가 자기 생성 IFC를 적산(정답값 고정)
# ═══════════════════════════════════════════════


class TestSelfTakeoffRoundtrip:
    def _parser(self):
        from apps.api.services.bim_ifc_service import BIMIFCService

        # _parse_ifc는 self 상태 비의존 — db/settings 없이 인스턴스만 구성.
        return BIMIFCService.__new__(BIMIFCService)

    def test_parse_ifc_takes_off_own_minimal_model(self, minimal_ifc_path):
        result = self._parser()._parse_ifc(minimal_ifc_path)

        assert result["ifc_version"] == "IFC4"
        assert result["element_count"] == 10
        # 집계 정답값: 체적 = 슬래브 80 + 외벽 72, 면적 = 400 + 360
        assert result["total_volume_m3"] == pytest.approx(152.0)
        assert result["total_area_sqm"] == pytest.approx(760.0)

        breakdown = {m["type"]: m for m in result["material_breakdown"]}
        assert breakdown["IfcSlab"]["count"] == 2
        assert breakdown["IfcSlab"]["volume_m3"] == pytest.approx(80.0)
        assert breakdown["IfcSlab"]["area_sqm"] == pytest.approx(400.0)
        assert breakdown["IfcWall"]["count"] == 8
        assert breakdown["IfcWall"]["volume_m3"] == pytest.approx(72.0)
        assert breakdown["IfcWall"]["area_sqm"] == pytest.approx(360.0)

        # 요소 단위 레코드(bim_quantities INSERT 입력): 전 요소 물량>0, 체적 우선 m3.
        assert len(result["elements"]) == 10
        for el in result["elements"]:
            assert el["quantity"] > 0, f"{el['name']}: 물량 0 — 적산 실패"
            assert el["unit"] == "m3"
            assert el["global_id"], "GlobalId 누락"

    def test_parse_ifc_takes_off_full_model_no_zero_quantity(self, full_ifc_path):
        """전체 모델(창·문·발코니·코어·계단 포함)도 빠짐없이 적산된다."""
        result = self._parser()._parse_ifc(full_ifc_path)

        assert result["element_count"] == FULL_MODEL_ELEMENT_COUNT
        assert len(result["elements"]) == FULL_MODEL_ELEMENT_COUNT
        for el in result["elements"]:
            assert el["quantity"] > 0, (
                f"{el['element_type']} '{el['name']}': 물량 0 — 자가 적산 누락"
            )
        # 개구부(창·문)는 체적 미부착 → 면적(m2)으로 정직 적산.
        windows = [e for e in result["elements"] if e["element_type"] == "IfcWindow"]
        assert len(windows) == 4
        for w in windows:
            assert w["unit"] == "m2"
            assert w["quantity"] == pytest.approx(1.8)    # 1.5 × 1.2
        doors = [e for e in result["elements"] if e["element_type"] == "IfcDoor"]
        assert len(doors) == 6
        for d in doors:
            assert d["unit"] == "m2"
            assert d["quantity"] == pytest.approx(1.89)   # 0.9 × 2.1


# ═══════════════════════════════════════════════
# 3. 전체 모델 품질 — 칸막이 Pset·코어/계단 물량(정답값 고정)
# ═══════════════════════════════════════════════


class TestFullModelQuality:
    def test_partition_walls_quantities_and_internal_pset(self, full_ifc_path):
        ifc = _open(full_ifc_path)
        parts = ifc.by_type("IfcWallStandardCase")
        assert len(parts) == 4  # 2F 전면/배면 zone × 칸막이 2
        for part in parts:
            qm = _quantity_map(part)
            # zone 깊이 3.8 × 벽고(3.0-0.2)=2.8
            assert qm["Length"] == pytest.approx(3.8)
            assert qm["Height"] == pytest.approx(2.8)
            assert qm["Width"] == pytest.approx(0.15)
            assert qm["NetSideArea"] == pytest.approx(10.64)
            assert qm["NetVolume"] == pytest.approx(1.596)
            pm = _pset_map(part, "Pset_WallCommon")
            assert pm is not None, f"{part.Name}: Pset_WallCommon 부재"
            assert pm["LoadBearing"] is False
            assert pm["IsExternal"] is False

    def test_core_wall_and_stair_quantities(self, full_ifc_path):
        ifc = _open(full_ifc_path)
        # 코어벽(하단면): 단면 5.0×0.2=1.0㎡, 체적 ×층고3.0=3.0㎥
        qm = _quantity_map(_by_name(ifc, "IfcColumn", "2F-CoreWall-1-0"))
        assert qm["Length"] == pytest.approx(3.0)
        assert qm["CrossSectionArea"] == pytest.approx(1.0)
        assert qm["NetVolume"] == pytest.approx(3.0)
        # 계단참: (2.25-0.05) × (5-2×0.25) × 0.15
        qs = _quantity_map(_by_name(ifc, "IfcStair", "2F-Stair-1-0"))
        assert qs["GrossArea"] == pytest.approx(9.9)      # 2.2 × 4.5
        assert qs["NetVolume"] == pytest.approx(1.485)    # 9.9 × 0.15


# ═══════════════════════════════════════════════
# 4. additive 회귀 — 요소 수·SPF 직렬화 무파손
# ═══════════════════════════════════════════════


class TestAdditiveRegression:
    def test_element_count_unchanged_by_qto_pset(self, full_ifc_path):
        """Qto/Pset 부착은 속성 추가일 뿐 — 제품 요소 수는 부착 전과 동일."""
        ifc = _open(full_ifc_path)
        assert len(ifc.by_type("IfcBuildingElement")) == FULL_MODEL_ELEMENT_COUNT

    def test_spf_header_and_quantity_entities_serialized(self, minimal_ifc_path):
        """export-ifc 경로(bytes 직렬화) 무파손 + ElementQuantity 실직렬화."""
        from pathlib import Path

        raw = Path(minimal_ifc_path).read_bytes()
        assert raw[:32].startswith(b"ISO-10303-21")
        text = raw.decode("utf-8")
        assert "FILE_SCHEMA(('IFC4'))" in text
        assert "IFCELEMENTQUANTITY" in text
        assert "IFCQUANTITYAREA" in text
        assert "IFCQUANTITYVOLUME" in text
        assert "Pset_WallCommon" in text
