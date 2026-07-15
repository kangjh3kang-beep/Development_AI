"""BimIR 소비처 전환 테스트 (WP-D 세션2 · P11) — glb·QTO·파생요소 확장.

검증 축(세션2 게이트):
- glb 전환: build_gltf_from_bimir == 매스 경로 구조 동등(mesh 그룹·정점수·인덱스수 + POSITION 버퍼
  실측값까지 바이트 동일) + source_kind 가드.
- QTO 전환: geometry_takeoff_from_bimir == geometry_takeoff 수치 동일(항목별 물량·금액 바이트 동일) + 가드.
- 파생요소 확장: 코어(COLUMN)·계단(STAIR)·창(WINDOW)·세대칸막이(PARTITION)·문(DOOR) 결정적 열거·물량 미러.
- 발산 감지(코디네이터 MEDIUM 리뷰): 미러 산출 물량을 하드코딩 기대값이 아니라 generator가 실제로
  만든 IFC의 BaseQuantities와 교차검증(test_derived_elements_no_divergence_from_real_generator_ifc).
- 왕복 확장: 파생요소를 늘려도 mass 왕복 무손실·element_id 결정성(3회 재생성 동일).
"""

from __future__ import annotations

import pytest

from app.services.bim.bimir_adapters import (
    bimir_from_cad_design_spec,
    bimir_from_mass,
    mass_from_bimir,
)
from app.services.bim.bimir_schema import BimCategory
from app.services.cad.design_spec import DesignSpec as CadDesignSpec
from app.services.cost.geometry_qto import (
    geometry_takeoff,
    geometry_takeoff_from_bimir,
)


# ── 픽스처 ──
def _mass() -> dict:
    # 세션1 픽스처와 동형(코어만 활성, 창/세대 비활성).
    return {
        "building_width_m": 40.0,
        "building_depth_m": 20.0,
        "num_floors": 7,
        "floor_height_m": 3.0,
        "core_positions": [{"x": 20.0, "y": 10.0}],
        "core_size_m": 5.0,
        "corridor_width_m": 0.0,
        "windows_per_side": 0,
        "unit_width_m": 0.0,
        "balconies": False,
        "unit_doors": False,
    }


def _rich_mass() -> dict:
    # ★모든 파생요소군을 켠다 — 코어·창·세대칸막이·문까지 열거되도록.
    return {
        "building_width_m": 40.0,
        "building_depth_m": 20.0,
        "num_floors": 3,
        "floor_height_m": 3.0,
        "core_positions": [{"x": 20.0, "y": 10.0}],
        "core_size_m": 5.0,
        "corridor_width_m": 2.0,   # >0 → 복도 존재(문 산출 조건)
        "windows_per_side": 2,     # 층당 F/B 2개씩
        "unit_width_m": 8.0,       # inner_w/8 균등 분할
        "unit_doors": True,        # 현관문 산출
        "extra_vendor_key": "보존됨",
    }


def _cad_model():
    return bimir_from_cad_design_spec(
        CadDesignSpec(site_area_sqm=1000.0, zone_code="2R", building_use="공동주택", num_floors=5)
    )


def _real_ifcopenshell() -> bool:
    try:
        import ifcopenshell

        return hasattr(ifcopenshell, "file")
    except Exception:
        return False


def _has_pygltflib() -> bool:
    try:
        import pygltflib  # noqa: F401

        return True
    except Exception:
        return False


_ifc_gate = pytest.mark.skipif(not _real_ifcopenshell(), reason="ifcopenshell 미설치 — IFC 산출 skip")
_glb_gate = pytest.mark.skipif(
    not (_real_ifcopenshell() and _has_pygltflib()), reason="ifcopenshell/pygltflib 미설치 — glb skip"
)


# ═══════════════════════════ QTO 전환 ═══════════════════════════
def test_qto_source_kind_guard_rejects_non_mass():
    # 비-매스 기원 IR은 무음 퇴화(10×10×5) 대신 명시 거부.
    with pytest.raises(ValueError):
        geometry_takeoff_from_bimir(_cad_model())


def test_qto_numerical_identity_basic():
    mass = _mass()
    direct = geometry_takeoff(
        width_m=mass["building_width_m"], depth_m=mass["building_depth_m"],
        floors_above=mass["num_floors"], floors_below=0,
        floor_height_m=mass["floor_height_m"], structure_type="RC",
    )
    via_bimir = geometry_takeoff_from_bimir(bimir_from_mass(mass))
    assert via_bimir == direct  # 전체 dict 바이트 동일(항목·요약 모두)


def test_qto_numerical_identity_with_floors_below_and_structure():
    mass = _mass()
    direct = geometry_takeoff(
        width_m=mass["building_width_m"], depth_m=mass["building_depth_m"],
        floors_above=mass["num_floors"], floors_below=2,
        floor_height_m=mass["floor_height_m"], structure_type="SRC",
    )
    via_bimir = geometry_takeoff_from_bimir(
        bimir_from_mass(mass), floors_below=2, structure_type="SRC"
    )
    assert via_bimir == direct


def test_qto_item_by_item_area_and_quantity_identity():
    mass = _rich_mass()
    direct = geometry_takeoff(
        width_m=mass["building_width_m"], depth_m=mass["building_depth_m"],
        floors_above=mass["num_floors"], floors_below=1,
        floor_height_m=mass["floor_height_m"], structure_type="RC",
    )
    via_bimir = geometry_takeoff_from_bimir(bimir_from_mass(mass), floors_below=1)
    # 항목별(레미콘·철근·거푸집) 수량·금액이 정확히 일치.
    assert len(via_bimir["items"]) == len(direct["items"])
    for a, b in zip(via_bimir["items"], direct["items"], strict=True):
        assert a["name"] == b["name"]
        assert a["quantity"] == b["quantity"]
        assert a["cost_won"] == b["cost_won"]
    # 집계 물량도 동일.
    for key in ("concrete_m3", "rebar_ton", "formwork_m2", "structural_direct_won"):
        assert via_bimir[key] == direct[key]


def test_qto_defaults_match_geometry_takeoff_defaults():
    # 기본 인자(floors_below=0·RC)가 geometry_takeoff 기본과 동일.
    mass = _mass()
    via_default = geometry_takeoff_from_bimir(bimir_from_mass(mass))
    via_explicit = geometry_takeoff_from_bimir(bimir_from_mass(mass), floors_below=0, structure_type="RC")
    assert via_default == via_explicit


# ═══════════════════════════ glb 전환 ═══════════════════════════
def test_glb_source_kind_guard_rejects_non_mass():
    # ifcopenshell 없이도 성립 — 가드가 IFC 산출 전에 먼저 거부.
    from app.services.bim.ifc_to_gltf_service import build_gltf_from_bimir

    with pytest.raises(ValueError):
        build_gltf_from_bimir(_cad_model())


def _glb_signature(glb_bytes: bytes) -> dict:
    """glb → {그룹명: (정점수, 인덱스수)} 구조 서명(GlobalId 무관·기하 구조만)."""
    import pygltflib

    g = pygltflib.GLTF2.load_from_bytes(glb_bytes)
    sig: dict[str, tuple[int, int]] = {}
    for prim in g.meshes[0].primitives:
        name = g.materials[prim.material].name
        pos = g.accessors[prim.attributes.POSITION]
        idx = g.accessors[prim.indices]
        sig[name] = (pos.count, idx.count)
    return sig


def _glb_positions(glb_bytes: bytes) -> dict[str, list[float]]:
    """glb → {그룹명: POSITION 버퍼 실측값} — 좌표 데이터 자체의 동등성 비교용(리뷰 LOW 강화).

    ★서명(개수)만 같아도 좌표가 다를 수 있으므로, bufferView에서 원시 float32 바이트를 직접
    슬라이스해 실제 정점 좌표까지 비교한다(구조 동등성의 '개수' 증거를 '값' 증거로 보강).
    """
    import numpy as np
    import pygltflib

    g = pygltflib.GLTF2.load_from_bytes(glb_bytes)
    blob = g.binary_blob()
    out: dict[str, list[float]] = {}
    for prim in g.meshes[0].primitives:
        name = g.materials[prim.material].name
        acc = g.accessors[prim.attributes.POSITION]
        bv = g.bufferViews[acc.bufferView]
        raw = blob[bv.byteOffset : bv.byteOffset + bv.byteLength]
        out[name] = np.frombuffer(raw, dtype=np.float32).tolist()
    return out


@_glb_gate
def test_glb_structural_equivalence_mass_vs_bimir():
    from app.services.bim.ifc_generator_service import build_ifc_from_mass
    from app.services.bim.ifc_to_gltf_service import build_gltf_from_bimir, ifc_bytes_to_glb

    mass = _mass()
    glb_mass = ifc_bytes_to_glb(build_ifc_from_mass(mass, project_name="EQ"))
    glb_bimir = build_gltf_from_bimir(bimir_from_mass(mass), project_name="EQ")
    # 그룹(mesh 색상군)·정점수·인덱스수가 두 경로에서 동일(구조 동등성).
    assert _glb_signature(glb_mass) == _glb_signature(glb_bimir)
    # ★강화(리뷰 LOW): 개수뿐 아니라 POSITION 버퍼 실측값까지 그룹별로 바이트 동일.
    assert _glb_positions(glb_mass) == _glb_positions(glb_bimir)


@_glb_gate
def test_glb_structural_equivalence_rich_mass():
    # 코어·창·세대·문까지 켠 매스로 더 많은 mesh 그룹을 통과시켜 동등성 확인.
    from app.services.bim.ifc_generator_service import build_ifc_from_mass
    from app.services.bim.ifc_to_gltf_service import build_gltf_from_bimir, ifc_bytes_to_glb

    mass = _rich_mass()
    glb_mass = ifc_bytes_to_glb(build_ifc_from_mass(mass, project_name="EQ"))
    glb_bimir = build_gltf_from_bimir(bimir_from_mass(mass), project_name="EQ")
    sig_mass = _glb_signature(glb_mass)
    sig_bimir = _glb_signature(glb_bimir)
    assert sig_mass == sig_bimir
    # 코어·계단·창·칸막이·문 그룹이 실제로 mesh에 존재(파생요소가 렌더된다).
    assert {"wall", "slab", "core", "stair", "window", "partition", "door"} <= set(sig_mass)
    # ★강화(리뷰 LOW): 좌표 버퍼까지 그룹별 바이트 동일(개수 동등을 값 동등으로 보강).
    assert _glb_positions(glb_mass) == _glb_positions(glb_bimir)


# ═══════════════════════════ 파생요소 확장 ═══════════════════════════
def test_mass_cores_emit_columns_and_stairs():
    model = bimir_from_mass(_mass())
    cats = [e.category for e in model.elements]
    # 코어 1개 × 7층: 코어벽 4면(COLUMN) + 계단참 2(STAIR).
    assert cats.count(BimCategory.COLUMN) == 4 * 1 * 7
    assert cats.count(BimCategory.STAIR) == 2 * 1 * 7
    # 기존 envelope 수는 불변(SLAB=층수·WALL=4×층수).
    assert cats.count(BimCategory.SLAB) == 7
    assert cats.count(BimCategory.WALL) == 7 * 4


def test_mass_windows_emit_window_elements():
    model = bimir_from_mass(_rich_mass())
    windows = [e for e in model.elements if e.category == BimCategory.WINDOW]
    # windows_per_side=2, F/B 2면, 1층 제외(i>0) → 3층 중 2개층.
    assert len(windows) == 2 * 2 * (3 - 1)
    # 1층(storey[0])에는 창이 없다(상가/필로티).
    assert all(not e.element_path.startswith("storey[0]/") for e in windows)


def test_mass_units_emit_partitions_and_doors():
    model = bimir_from_mass(_rich_mass())
    parts = [e for e in model.elements if e.category == BimCategory.PARTITION]
    doors = [e for e in model.elements if e.category == BimCategory.DOOR]
    # inner_w=39.6, unit_width=8 → 4세대/zone. 칸막이=3/zone, 문=4/zone. 2 zone × 2층(i>0).
    assert len(parts) == 3 * 2 * 2
    assert len(doors) == 4 * 2 * 2
    # 1층 제외 확인.
    assert all(not e.element_path.startswith("storey[0]/") for e in parts + doors)


def test_mass_slab_count_stays_floor_slabs_with_corridor():
    # ★복도(corridor_width_m>0)가 있어도 SLAB 범주는 '층 바닥'만 — 복도/발코니 슬래브는 파생 안 함.
    model = bimir_from_mass(_rich_mass())
    slabs = [e for e in model.elements if e.category == BimCategory.SLAB]
    assert len(slabs) == 3  # 층수만큼(복도 슬래브 미포함)


def test_derived_element_quantities_mirror_generator():
    model = bimir_from_mass(_rich_mass())

    def first(cat: BimCategory):
        return next(e for e in model.elements if e.category == cat)

    # COLUMN(코어벽 하단): ww=cs=5, wd=cwt=0.2, fh=3 → CrossSectionArea=1.0·NetVolume=3.0.
    col = first(BimCategory.COLUMN)
    assert col.quantities["CrossSectionArea"] == pytest.approx(5.0 * 0.2)
    assert col.quantities["NetVolume"] == pytest.approx(5.0 * 0.2 * 3.0)
    assert col.quantities["Length"] == pytest.approx(3.0)
    # STAIR: inset=0.25, half_w=2.25, st_w=2.2, st_d=4.5 → GrossArea=st_w*st_d.
    stair = first(BimCategory.STAIR)
    st_w, st_d = 2.25 - 0.05, 5.0 - 2 * 0.25
    assert stair.quantities["GrossArea"] == pytest.approx(st_w * st_d)
    assert stair.quantities["NetVolume"] == pytest.approx(st_w * st_d * 0.15)
    # WINDOW: 1.5×1.2 → Area=1.8.
    win = first(BimCategory.WINDOW)
    assert win.quantities["Area"] == pytest.approx(1.5 * 1.2)
    # PARTITION: zd=8.8, part_h=fh-slab=2.8 → NetSideArea=zd*part_h.
    part = first(BimCategory.PARTITION)
    assert part.quantities["NetSideArea"] == pytest.approx(8.8 * 2.8)
    assert part.quantities["NetVolume"] == pytest.approx(0.15 * 8.8 * 2.8)
    # DOOR: 0.9×2.1 → Area=1.89.
    door = first(BimCategory.DOOR)
    assert door.quantities["Area"] == pytest.approx(0.9 * 2.1)


def test_derived_element_paths_are_deterministic_and_indexed():
    paths = {e.element_path for e in bimir_from_mass(_rich_mass()).elements}
    # 결정적 인덱스 경로 — 층/코어/면·순번 규율.
    assert "storey[1]/core[0]/wall[0]" in paths
    assert "storey[1]/core[0]/stair[0]" in paths
    assert "storey[1]/window/F[0]" in paths
    assert "storey[1]/partition/F[1]" in paths
    assert "storey[1]/door/F[0]" in paths


def _ifc_quantity_value(q) -> float:
    """IfcQuantity* 1건 → 값(Length/Area/Volume). production 파서(design_ingest/parsers.py
    _ifc_quantity_area)와 동일한 is_a() 판별 패턴을 따른다(추측 API 사용 금지)."""
    if q.is_a("IfcQuantityLength"):
        return float(q.LengthValue or 0.0)
    if q.is_a("IfcQuantityArea"):
        return float(q.AreaValue or 0.0)
    if q.is_a("IfcQuantityVolume"):
        return float(q.VolumeValue or 0.0)
    return 0.0


def _ifc_sum_quantity(ifc_file, ifc_class: str, qty_name: str, *, name_suffix: str | None = None) -> float:
    """generator가 실제로 만든 IFC에서 ifc_class 전건의 qty_name 물량 합계를 파싱한다.

    name_suffix가 있으면 Name이 그 접미사로 끝나는 엔티티만 집계한다(예: IfcSlab 중 층 바닥
    "...F-Slab"만 골라 복도/발코니 슬래브를 제외 — 미러가 층 바닥만 파생하므로 동종 비교가
    되도록 맞춘다).

    ★include_subtypes=False 필수: IfcWallStandardCase(PARTITION이 쓰는 클래스)는 IFC 스키마상
    IfcWall의 하위형이라 by_type("IfcWall") 기본값(include_subtypes=True)은 파티션까지 함께
    끌어와 합계를 오염시킨다(실측: WALL Length 465.6 vs 미러 360.0 — 이 필터 없이는 '가짜
    발산'을 낸다). 정확히 그 클래스만 세도록 명시적으로 하위형을 배제한다.
    """
    total = 0.0
    for ent in ifc_file.by_type(ifc_class, include_subtypes=False):
        if name_suffix is not None and not str(ent.Name or "").endswith(name_suffix):
            continue
        for rel in getattr(ent, "IsDefinedBy", None) or []:
            if not rel.is_a("IfcRelDefinesByProperties"):
                continue
            pd = rel.RelatingPropertyDefinition
            if not pd.is_a("IfcElementQuantity"):
                continue
            for q in pd.Quantities:
                if q.Name == qty_name:
                    total += _ifc_quantity_value(q)
    return total


def _mirror_sum_quantity(model, category: BimCategory, qty_name: str) -> float:
    return sum(e.quantities.get(qty_name, 0.0) for e in model.elements if e.category == category)


@_ifc_gate
def test_derived_elements_no_divergence_from_real_generator_ifc():
    """★발산 감지(코디네이터 MEDIUM 리뷰 반영) — 이전 테스트들은 미러 산출을 '하드코딩 기대값'과만
    비교했고, generator가 실제로 만든 IFC와는 대조하지 않았다(리뷰 지적: 두 경로가 함께 발산해도
    잡히지 않는 사각지대). 이 테스트는 build_ifc_from_mass가 실제로 산출한 IFC를 파싱해 그
    BaseQuantities 합계와 미러(bimir_from_mass)의 물량 합계를 범주별로 교차검증한다.

    ★SSOT 추출 대신 발산 감지를 택한 근거(커밋에도 기록): 코어·계단·창·칸막이·문의 좌표·존재조건
    수식은 generator.generate() 루프 본문에 IFC 엔티티 생성 호출과 인터리브되어 있어, 세션2
    스코프에서 안전하게 순수 함수로 분리 추출하려면 이미 리뷰·머지된 핵심 생성기(세션1 승인)의
    구조를 재편해야 한다 — 26+2 기존 테스트 대비 회귀 리스크가 이번 세션 범위를 초과한다. 대신
    이 테스트가 "두 경로가 실제로 같은 물량을 낸다"를 직접 증명하는 안전망 역할을 한다. 단
    unit_widths 하나는 진짜 SSOT로 전환했다(_mirror_unit_widths → IfcGeneratorService._unit_widths
    직접 재사용 — bimir_adapters.py 참고).
    """
    import ifcopenshell

    from app.services.bim.ifc_generator_service import build_ifc_from_mass

    mass = _rich_mass()
    ifc = ifcopenshell.file.from_string(build_ifc_from_mass(mass, project_name="DIV").decode("utf-8"))
    model = bimir_from_mass(mass)

    # (범주, IFC 클래스, Name 접미사 필터, 비교할 물량명들) — 미러가 실제로 저장하는 물량명만
    # 비교한다(WALL/PARTITION의 Width처럼 미러가 담지 않는 부수 스칼라는 docstring에 정직 표기).
    checks = [
        (BimCategory.COLUMN, "IfcColumn", None, ("Length", "CrossSectionArea", "NetVolume")),
        (BimCategory.STAIR, "IfcStair", None, ("Length", "GrossArea", "NetVolume")),
        (BimCategory.WINDOW, "IfcWindow", None, ("Width", "Height", "Area")),
        (BimCategory.DOOR, "IfcDoor", None, ("Width", "Height", "Area")),
        (BimCategory.PARTITION, "IfcWallStandardCase", None,
         ("Length", "Height", "NetSideArea", "NetVolume")),
        (BimCategory.WALL, "IfcWall", None, ("Length", "NetSideArea", "NetVolume")),
        # IfcSlab은 generator가 층바닥+복도(+발코니)를 함께 만든다 — 미러는 층바닥만 파생하므로
        # Name 접미사 "-Slab"로 층바닥만 걸러 동종 비교(복도 "-Corridor"는 제외).
        (BimCategory.SLAB, "IfcSlab", "-Slab", ("NetArea", "NetVolume", "Perimeter")),
    ]
    for category, ifc_class, suffix, qty_names in checks:
        for qty_name in qty_names:
            real = _ifc_sum_quantity(ifc, ifc_class, qty_name, name_suffix=suffix)
            mirror = _mirror_sum_quantity(model, category, qty_name)
            assert real == pytest.approx(mirror), (
                f"{category.value}.{qty_name} 발산: generator(실제 IFC)={real} mirror(BimIR)={mirror}"
            )


# ═══════════════════════════ 클램프 정합(리뷰 LOW) ═══════════════════════════
def test_mass_derived_elements_clamp_degenerate_dimensions():
    """★리뷰 LOW 회귀 고정 — 클램프 정합 전에는 미러가 0/음수/극단값을 그대로 써 generator의
    max(...,바닥값) 클램프와 발산했다(실측 DIVERGE 확인됨). 이제 파생요소 계산에 동일 클램프를
    적용한다. BUILDING geometry(왕복 진실원천)는 클램프와 무관 — 원본 그대로 보존(손실 0 유지).
    """
    mass = {"building_width_m": 0.1, "building_depth_m": -5.0, "num_floors": 0, "floor_height_m": 0.5}
    model = bimir_from_mass(mass)
    slab = next(e for e in model.elements if e.category == BimCategory.SLAB)
    assert slab.geometry["width_m"] == 1.0  # generator bw=max(0.1,1.0)
    assert slab.geometry["depth_m"] == 1.0  # generator bd=max(-5.0,1.0)
    storeys = [e for e in model.elements if e.category == BimCategory.STOREY]
    assert len(storeys) == 1  # generator n=max(0,1)
    wall = next(e for e in model.elements if e.category == BimCategory.WALL)
    assert wall.geometry["height_m"] == 2.0  # generator fh=max(0.5,2.0)
    # 왕복 진실원천은 클램프 이전 원본 그대로.
    restored = mass_from_bimir(model)
    assert restored["building_width_m"] == 0.1
    assert restored["building_depth_m"] == -5.0
    assert restored["num_floors"] == 0
    assert restored["floor_height_m"] == 0.5


@_ifc_gate
def test_mass_adapter_clamp_matches_real_generator_ifc_for_degenerate_input():
    # 실제 생성기가 만든 IFC와 대조해 클램프 파라미터 정합을 직접 증명(하드코딩 기대값 아님).
    import ifcopenshell

    from app.services.bim.ifc_generator_service import build_ifc_from_mass

    mass = {"building_width_m": 0.1, "building_depth_m": -5.0, "num_floors": 0, "floor_height_m": 0.5}
    ifc = ifcopenshell.file.from_string(
        build_ifc_from_mass(mass, project_name="CLAMP").decode("utf-8")
    )
    real_storeys = ifc.by_type("IfcBuildingStorey", include_subtypes=False)
    model = bimir_from_mass(mass)
    mirror_storeys = [e for e in model.elements if e.category == BimCategory.STOREY]
    assert len(real_storeys) == len(mirror_storeys) == 1


# ═══════════════════════════ 왕복 확장 검증 ═══════════════════════════
def test_rich_mass_roundtrip_lossless():
    mass = _rich_mass()
    model = bimir_from_mass(mass)
    restored = mass_from_bimir(model)
    # 파생요소를 늘려도 왕복 진실원천은 BUILDING geometry 한 곳 — 원본과 완전 동일(미사상 키 포함).
    assert restored == mass
    assert mass["corridor_width_m"] == 2.0  # 원본 훼손 없음


def test_rich_mass_deterministic_x3():
    outs = [bimir_from_mass(_rich_mass()) for _ in range(3)]
    # 정규 JSON 바이트 동일·element_id 전건 불변(3회 재생성).
    assert len({m.to_canonical_json() for m in outs}) == 1
    assert len({tuple(m.element_ids()) for m in outs}) == 1
    assert len({tuple(e.fingerprint for e in m.elements) for m in outs}) == 1


@_ifc_gate
def test_rich_mass_ifc_histogram_equivalence():
    # 파생요소 확장 후에도 BimIR IFC 경로 == 매스 경로 요소 히스토그램 동일(회귀 0).
    from collections import Counter

    import ifcopenshell

    from app.services.bim.ifc_generator_service import build_ifc_from_bimir, build_ifc_from_mass

    mass = _rich_mass()
    ifc_mass = build_ifc_from_mass(mass, project_name="EQ")
    ifc_bimir = build_ifc_from_bimir(bimir_from_mass(mass), project_name="EQ")

    def hist(raw: bytes) -> Counter:
        m = ifcopenshell.file.from_string(raw.decode("utf-8"))
        return Counter(e.is_a() for e in m)

    h_mass, h_bimir = hist(ifc_mass), hist(ifc_bimir)
    for cls in ("IfcSlab", "IfcWall", "IfcWallStandardCase", "IfcColumn", "IfcStair",
                "IfcWindow", "IfcDoor", "IfcBuildingStorey", "IfcSite", "IfcBuilding"):
        assert h_mass[cls] == h_bimir[cls], f"{cls} 불일치: {h_mass[cls]} != {h_bimir[cls]}"


# ═══════════════════════════ boq_bim_merge 계약 불변 확인 ═══════════════════════════
def test_boq_bim_merge_contract_unaffected():
    # boq_bim_merge는 geometry_takeoff를 소비하지 않는다(bim_rows 별도 계약) — QTO 전환 무관.
    import inspect

    from app.services.cost import boq_bim_merge

    assert "geometry_takeoff" not in inspect.getsource(boq_bim_merge)
    # merge_bim 자체는 여전히 정상 동작(비파괴·additive 계약 유지).
    draft = {
        "disciplines": {"골조": {"items": [{"name": "레미콘 타설", "unit": "m3", "qty": 100.0}]}},
        "summary": {},
    }
    out = boq_bim_merge.merge_bim(draft, [{"work_code": "A01", "unit": "m3", "quantity": 120.0}])
    assert "bim_merge" in out["summary"]
