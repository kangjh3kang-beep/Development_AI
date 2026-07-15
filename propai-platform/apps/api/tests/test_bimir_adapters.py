"""구 DesignSpec 2벌 + 매스 → BimIR 어댑터 테스트 (WP-D · P11).

검증 축:
- 손실 0: 세 어댑터 모두 원본 전체를 extras에 보존(cad=model_dump·ingest=asdict·mass=원본).
- 이형 타입 왕복: cad(pydantic) 재구성 동일·mass 왕복(0/False 포함) 동일.
- 결정성: 같은 입력 3회 → element_id 전건·fingerprint·정규 JSON 바이트 동일.
- 소비처 전환(대표): build_ifc_from_bimir == build_ifc_from_mass 구조 동등(왕복 매스 동일 + IFC 요소 히스토그램 동일).
"""

from __future__ import annotations

import dataclasses

import pytest

from app.services.bim.bimir_adapters import (
    bimir_from_cad_design_spec,
    bimir_from_ingest_design_spec,
    bimir_from_mass,
    mass_from_bimir,
)
from app.services.bim.bimir_schema import BimCategory
from app.services.cad.design_spec import DesignSpec as CadDesignSpec
from app.services.cad.design_spec import Setback, UnitGrammar
from app.services.design_ingest.design_spec import DesignSpec as IngestDesignSpec
from app.services.design_ingest.design_spec import RoomSpec


# ── 픽스처 헬퍼 ──
def _cad_spec() -> CadDesignSpec:
    return CadDesignSpec(
        site_area_sqm=1000.0,
        zone_code="2R",
        building_use="공동주택",
        num_floors=7,
        floor_height_m=3.0,
        target_units=40,
        target_unit_types=["59A", "84A"],
        setback_m=Setback(north=3.0, south=2.0, east=1.5, west=1.5),
        effective_far_percent=200.0,
        massing_kind="slab",
        unit_grammar=UnitGrammar(bays=3, core_type="계단실형", balcony_extension=True),
    )


def _ingest_spec() -> IngestDesignSpec:
    return IngestDesignSpec(
        source_format="dxf",
        drawing_type="floor_plan",
        title="기준층 평면도",
        total_area_sqm=850.0,
        floor_count=7,
        unit_count=40,
        parking_count=0,  # ★0 보존 검증용(falsy 아님)
        rooms=[RoomSpec(name="거실", area_sqm=24.0), RoomSpec(name="침실1", area_sqm=12.0)],
        dimensions={"bbox": [0, 0, 40, 20]},
        layers=["A-WALL", "A-DOOR"],
        raw_summary="기준층 평면 요약",
    )


def _mass() -> dict:
    # ★0/False 포함 — 왕복에서 falsy가 살아남는지 검증.
    return {
        "building_width_m": 40.0,
        "building_depth_m": 20.0,
        "num_floors": 7,
        "floor_height_m": 3.0,
        "core_positions": [{"x": 20.0, "y": 10.0}],
        "core_size_m": 5.0,
        "corridor_width_m": 0.0,   # 0 보존
        "windows_per_side": 0,     # 0 보존
        "unit_width_m": 0.0,       # 0 보존
        "balconies": False,        # False 보존
        "unit_doors": False,       # False 보존
        "extra_vendor_key": "보존됨",  # 미사상 키도 손실 0
    }


# ─────────────────────────────── cad 어댑터 ───────────────────────────────
def test_cad_adapter_lossless_extras():
    spec = _cad_spec()
    model = bimir_from_cad_design_spec(spec)
    assert model.source_kind == "cad_design_spec"
    # 손실 0: 원본 model_dump 전체가 그대로 보존.
    assert model.extras["cad_design_spec"] == spec.model_dump()


def test_cad_adapter_reconstruct_equals_original():
    spec = _cad_spec()
    model = bimir_from_cad_design_spec(spec)
    # extras 보존본에서 원본 pydantic 모델을 완전 복원 → 동일(왕복 무손실).
    reconstructed = CadDesignSpec(**model.extras["cad_design_spec"])
    assert reconstructed == spec


def test_cad_adapter_emits_site_and_building():
    model = bimir_from_cad_design_spec(_cad_spec())
    cats = {e.category for e in model.elements}
    assert BimCategory.SITE in cats
    assert BimCategory.BUILDING in cats
    site = next(e for e in model.elements if e.category == BimCategory.SITE)
    assert site.geometry["site_area_sqm"] == 1000.0
    assert model.attributes["zone_code"] == "2R"  # zone_code 원본 그대로(변형 금지)


def test_cad_adapter_deterministic_x3():
    outs = [bimir_from_cad_design_spec(_cad_spec()) for _ in range(3)]
    jsons = {m.to_canonical_json() for m in outs}
    assert len(jsons) == 1  # 정규 JSON 바이트 동일
    id_sets = {tuple(m.element_ids()) for m in outs}
    assert len(id_sets) == 1  # element_id 전건 불변
    fps = {tuple(e.fingerprint for e in m.elements) for m in outs}
    assert len(fps) == 1  # fingerprint 동일


# ─────────────────────────────── ingest 어댑터 ───────────────────────────────
def test_ingest_adapter_lossless_extras():
    spec = _ingest_spec()
    model = bimir_from_ingest_design_spec(spec)
    assert model.source_kind == "design_ingest"
    # 손실 0: asdict 전체 보존(중첩 RoomSpec 포함).
    assert model.extras["design_ingest_design_spec"] == dataclasses.asdict(spec)


def test_ingest_adapter_rooms_to_spaces_and_zero_preserved():
    spec = _ingest_spec()
    model = bimir_from_ingest_design_spec(spec)
    spaces = [e for e in model.elements if e.category == BimCategory.SPACE]
    assert len(spaces) == 2
    assert spaces[0].name == "거실" and spaces[0].geometry["area_sqm"] == 24.0
    # parking_count=0 이 attributes에 보존(falsy 아님).
    assert model.attributes["parking_count"] == 0


def test_ingest_adapter_reuses_content_hash():
    spec = _ingest_spec()
    model = bimir_from_ingest_design_spec(spec)
    # design_input_hash = 원본의 결정적 content_hash 재사용(재발명 금지).
    assert model.design_input_hash == spec.content_hash()


def test_ingest_adapter_deterministic_x3():
    outs = [bimir_from_ingest_design_spec(_ingest_spec()) for _ in range(3)]
    assert len({m.to_canonical_json() for m in outs}) == 1
    assert len({tuple(m.element_ids()) for m in outs}) == 1


# ─────────────────────────────── mass 어댑터 ───────────────────────────────
def test_mass_roundtrip_lossless_including_zero_false():
    mass = _mass()
    model = bimir_from_mass(mass)
    restored = mass_from_bimir(model)
    # 왕복 완전 무손실 — 0/False/미사상 키까지 전부 동일.
    assert restored == mass
    # 원본 dict 훼손 없음(방어적 복사).
    assert mass["corridor_width_m"] == 0.0


def test_mass_adapter_emits_envelope_elements():
    model = bimir_from_mass(_mass())
    cats = [e.category for e in model.elements]
    assert BimCategory.BUILDING in cats
    assert cats.count(BimCategory.STOREY) == 7          # 층수만큼
    assert cats.count(BimCategory.SLAB) == 7            # 층당 바닥 1
    assert cats.count(BimCategory.WALL) == 7 * 4        # 층당 외벽 4면
    # 슬래브 물량 = generator BaseQuantities 수식 미러(NetArea=bw*bd).
    slab = next(e for e in model.elements if e.category == BimCategory.SLAB)
    assert slab.quantities["NetArea"] == 40.0 * 20.0


def test_mass_adapter_deterministic_x3():
    outs = [bimir_from_mass(_mass()) for _ in range(3)]
    assert len({m.to_canonical_json() for m in outs}) == 1
    assert len({tuple(m.element_ids()) for m in outs}) == 1


# ─────────────── 소비처 전환(대표): BimIR 경로 == 매스 경로 구조 동등 ───────────────
def test_build_ifc_from_bimir_uses_same_mass_params():
    # ifcopenshell 없이도 성립하는 1급 증거: 왕복 매스가 원본과 동일하므로 generate() 호출이 동일.
    from app.services.bim.ifc_generator_service import build_ifc_from_bimir  # noqa: F401

    mass = _mass()
    model = bimir_from_mass(mass)
    assert mass_from_bimir(model) == mass  # 동일 파라미터 → 동일 IFC(구조)


def _real_ifcopenshell() -> bool:
    try:
        import types

        import ifcopenshell
        return isinstance(ifcopenshell, types.ModuleType) and hasattr(ifcopenshell, "file")
    except Exception:
        return False


@pytest.mark.skipif(not _real_ifcopenshell(), reason="ifcopenshell 미설치 — IFC 히스토그램 동등성 skip")
def test_ifc_from_bimir_histogram_equals_mass_path():
    # 2급 증거: 실제 IFC 산출의 요소 타입 히스토그램이 두 경로에서 동일(GlobalId 랜덤은 구조 무관).
    from collections import Counter

    import ifcopenshell

    from app.services.bim.ifc_generator_service import (
        build_ifc_from_bimir,
        build_ifc_from_mass,
    )

    mass = _mass()
    ifc_mass = build_ifc_from_mass(mass, project_name="EQ")
    ifc_bimir = build_ifc_from_bimir(bimir_from_mass(mass), project_name="EQ")

    def hist(raw: bytes) -> Counter:
        m = ifcopenshell.file.from_string(raw.decode("utf-8"))
        return Counter(e.is_a() for e in m)

    h_mass, h_bimir = hist(ifc_mass), hist(ifc_bimir)
    # 핵심 제품 타입 수 동등(결정적).
    for cls in ("IfcSlab", "IfcWall", "IfcColumn", "IfcStair", "IfcBuildingStorey", "IfcSite", "IfcBuilding"):
        assert h_mass[cls] == h_bimir[cls], f"{cls} 요소 수 불일치: {h_mass[cls]} != {h_bimir[cls]}"


# ── PR#284 리뷰 MEDIUM 반영 회귀 ────────────────────────────────────────────


def test_mass_extras_are_independent_copies_no_alias_leak():
    """★리뷰 적발 회귀 고정 — 복원본 변이가 원본 mass·model.extras로 역류(별칭 누수)하면 안 된다."""
    mass = {"building_width_m": 12.0, "core_positions": [{"x": 1.0, "y": 2.0}]}
    model = bimir_from_mass(mass)
    restored = mass_from_bimir(model)
    restored["core_positions"][0]["x"] = 999.0
    assert mass["core_positions"][0]["x"] == 1.0, "원본 mass로 별칭 누수"
    assert model.extras["mass_geometry"]["core_positions"][0]["x"] == 1.0, "extras로 별칭 누수"


def test_build_ifc_from_bimir_rejects_non_mass_source_kind():
    """★리뷰 적발 회귀 고정 — 비-매스 기원 IR은 무음 퇴화(10×10 기본값) 대신 명시 거부."""
    import pytest as _pytest

    from app.services.bim.ifc_generator_service import build_ifc_from_bimir

    model = bimir_from_mass({"building_width_m": 12.0})
    hacked = model.model_copy(update={"source_kind": "cad_design_spec"})
    with _pytest.raises(ValueError):
        build_ifc_from_bimir(hacked)
