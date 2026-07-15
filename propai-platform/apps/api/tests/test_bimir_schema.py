"""propai.bimir/1.0 스키마 계약 테스트 (WP-D · P11).

검증 축:
- category v1 = 정확히 14종 + IFC 클래스 1:1 사상(전건).
- element_id = 결정적 uuid5 파생(포맷·재현성·문서화된 파생식).
- fingerprint = int/float 잡음 무시·기하 변화 감지.
- ownership 예약 필드 직렬화(값은 None, 자리는 항상 존재).
- 0-falsy 금지(값 0을 버리지 않음)·정규 JSON 바이트 안정성.
- IR 생성 경로에 uuid4/시각/랜덤 부재(결정론 게이트의 소스 레벨 가드).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.services.bim.bimir_schema import (
    BIMIR_NAMESPACE,
    CATEGORY_IFC_CLASS,
    ELEMENT_ID_DERIVATION,
    IR_VERSION,
    BimCategory,
    BimElement,
    BimElementOwnership,
    compute_fingerprint,
    derive_element_id,
    ifc_class_for,
    make_element,
)


def test_category_v1_is_exactly_14():
    # 명세 A7: category v1 14종. 매핑 dict 키 집합 = enum 전건.
    assert len(BimCategory) == 14
    assert set(CATEGORY_IFC_CLASS.keys()) == set(BimCategory)


def test_every_category_maps_to_expected_ifc_class():
    expected = {
        BimCategory.SITE: "IfcSite",
        BimCategory.BUILDING: "IfcBuilding",
        BimCategory.STOREY: "IfcBuildingStorey",
        BimCategory.SPACE: "IfcSpace",
        BimCategory.SLAB: "IfcSlab",
        BimCategory.WALL: "IfcWall",
        BimCategory.PARTITION: "IfcWallStandardCase",
        BimCategory.COLUMN: "IfcColumn",
        BimCategory.BEAM: "IfcBeam",
        BimCategory.STAIR: "IfcStair",
        BimCategory.DOOR: "IfcDoor",
        BimCategory.WINDOW: "IfcWindow",
        BimCategory.ROOF: "IfcRoof",
        BimCategory.UNKNOWN: "IfcBuildingElementProxy",
    }
    for cat, ifc in expected.items():
        assert ifc_class_for(cat) == ifc
        assert CATEGORY_IFC_CLASS[cat] == ifc


def test_ir_version_constant():
    assert IR_VERSION == "propai.bimir/1.0"


def test_element_id_is_valid_uuid5():
    eid = derive_element_id("deadbeef", "storey[0]/wall/S", "cafef00d")
    parsed = uuid.UUID(eid)  # 포맷 유효(예외 없이 파싱)
    assert parsed.version == 5  # uuid5(SHA-1 기반) — 랜덤/시각 아님


def test_element_id_derivation_matches_documented_formula():
    # 스키마가 박제한 파생식(ELEMENT_ID_DERIVATION)과 실제 파생이 일치하는지(문서=코드).
    ih, path, fp = "hash123", "building", "fp456"
    manual = str(uuid.uuid5(BIMIR_NAMESPACE, f"{ih}|{path}|{fp}"))
    assert derive_element_id(ih, path, fp) == manual
    assert "uuid5(BIMIR_NAMESPACE" in ELEMENT_ID_DERIVATION
    assert "design_input_hash" in ELEMENT_ID_DERIVATION


def test_derive_element_id_is_deterministic():
    a = derive_element_id("h", "p", "f")
    b = derive_element_id("h", "p", "f")
    assert a == b
    # 입력이 다르면 id도 다르다.
    assert derive_element_id("h", "p", "f") != derive_element_id("h", "p2", "f")


def test_fingerprint_ignores_int_float_noise():
    # 20 == 20.0 → 같은 지문(normalize_fingerprint 경유).
    fp_int = compute_fingerprint(category=BimCategory.SLAB, geometry={"w": 20}, storey_index=1)
    fp_float = compute_fingerprint(category=BimCategory.SLAB, geometry={"w": 20.0}, storey_index=1)
    assert fp_int == fp_float


def test_fingerprint_changes_with_geometry_and_category():
    base = compute_fingerprint(category=BimCategory.SLAB, geometry={"w": 20.0}, storey_index=1)
    diff_geo = compute_fingerprint(category=BimCategory.SLAB, geometry={"w": 21.0}, storey_index=1)
    diff_cat = compute_fingerprint(category=BimCategory.WALL, geometry={"w": 20.0}, storey_index=1)
    assert base != diff_geo
    assert base != diff_cat


def test_ownership_reserved_fields_serialize():
    # 예약 필드는 값이 None이어도 직렬화에 '항상' 존재해야 한다(하류 스키마 인지).
    dumped = BimElementOwnership().model_dump()
    assert dumped == {
        "owner_track": None,
        "base_version": None,
        "origin_kind": None,
        "locked": None,
    }
    # 요소에 부착됐을 때도 마찬가지.
    el = make_element(
        design_input_hash="h", element_path="p", category=BimCategory.WALL,
    )
    assert el.model_dump()["ownership"] == dumped


def test_make_element_preserves_zero_and_false_values():
    # ★0-falsy 금지: 값 0/False/빈문자열을 버리지 않고 원본 그대로 보존한다.
    el = make_element(
        design_input_hash="h",
        element_path="storey[0]/slab",
        category=BimCategory.SLAB,
        storey_index=0,
        geometry={"thickness_m": 0.0, "flag": False, "label": ""},
        quantities={"NetArea": 0.0},
    )
    assert el.geometry == {"thickness_m": 0.0, "flag": False, "label": ""}
    assert el.quantities == {"NetArea": 0.0}
    assert el.storey_index == 0  # 층 인덱스 0 보존(falsy 아님)


def test_make_element_is_deterministic():
    kwargs = dict(
        design_input_hash="abc",
        element_path="storey[2]/wall/N",
        category=BimCategory.WALL,
        storey_index=2,
        geometry={"length_m": 20.0, "height_m": 3.0},
    )
    a = make_element(**kwargs)
    b = make_element(**kwargs)
    assert a.element_id == b.element_id
    assert a.fingerprint == b.fingerprint
    assert a.model_dump() == b.model_dump()


def test_no_random_or_time_in_ir_source():
    # 결정론 게이트의 소스 '코드' 레벨 가드 — IR 생성 경로에 비결정 식별자가 없어야 한다.
    # ★AST 기반: 주석·docstring 문자열(금지 토큰을 '설명'하는 문장)은 무시하고 실제 코드 식별자만 검사.
    import ast

    base = Path(__file__).resolve().parent.parent / "app" / "services" / "bim"
    forbidden = {"uuid4", "uuid1", "now", "random", "perf_counter", "datetime", "time"}
    for name in ("bimir_schema.py", "bimir_adapters.py"):
        tree = ast.parse((base / name).read_text(encoding="utf-8"))
        used: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
            elif isinstance(node, ast.Import):
                used.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                used.add(node.module.split(".")[0])
        hit = forbidden & used
        assert not hit, f"{name} 코드에 비결정 식별자 {hit} 발견 — 결정론 위반"


def test_bim_element_forbids_unknown_fields():
    # extra='forbid' — 계약 밖 필드 유입 차단(오염 방지).
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        BimElement(
            element_id="x", element_path="p", category=BimCategory.WALL,
            fingerprint="f", bogus_field=123,
        )
