"""design_ingest 단위테스트 — 파싱→DesignSpec 정규화(DB/네트워크 무관).

엑셀(openpyxl)·DXF(ezdxf)를 인메모리로 생성해 라운드트립 검증한다.
"""

import io

from app.services.design_ingest.design_spec import DesignSpec, detect_drawing_type
from app.services.design_ingest.parsers import (
    detect_format,
    parse_design_file,
    parse_dxf,
    parse_excel,
    parse_ifc,
)


def test_detect_format():
    assert detect_format("배치도.dxf") == "dxf"
    assert detect_format("스펙.xlsx") == "excel"
    assert detect_format("model.ifc") == "ifc"
    assert detect_format("plan.pdf") == "pdf"
    assert detect_format("photo.JPG") == "image"
    assert detect_format("readme.txt") == "unknown"


def test_detect_drawing_type():
    assert detect_drawing_type("의정부_배치도.dxf") == "site_plan"
    assert detect_drawing_type("3층_평면도.dxf") == "floor_plan"
    assert detect_drawing_type("A-A_단면도.dxf") == "section"
    assert detect_drawing_type("정면_입면도.dxf") == "elevation"
    assert detect_drawing_type("지하주차장.dxf") == "parking"
    assert detect_drawing_type("무관한이름.dxf") == "unknown"


def _make_xlsx() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["항목", "값"])
    ws.append(["연면적", "12,345.6"])
    ws.append(["지상 층수", "15"])
    ws.append(["세대수", "120"])
    ws.append(["주차대수", "150"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_excel_extracts_quant():
    spec = parse_excel(_make_xlsx(), "용인_사업개요.xlsx")
    assert spec.source_format == "excel"
    assert spec.total_area_sqm == 12345.6
    assert spec.floor_count == 15
    assert spec.unit_count == 120
    assert spec.parking_count == 150
    assert "12,345.6" in spec.raw_summary


def _make_dxf() -> bytes:
    import ezdxf

    doc = ezdxf.new()
    doc.layers.add("ROOM")
    doc.layers.add("PARKING")
    msp = doc.modelspace()
    msp.add_text("거실", dxfattribs={"insert": (0, 0)})
    msp.add_text("주차구역", dxfattribs={"insert": (100, 50)})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_parse_dxf_extracts_layers_labels():
    spec = parse_dxf(_make_dxf(), "지하1층_주차_평면도.dxf")
    assert spec.source_format == "dxf"
    assert "ROOM" in spec.layers and "PARKING" in spec.layers
    labels = {r.name for r in spec.rooms}
    assert "거실" in labels and "주차구역" in labels
    # 파일명에 평면도+주차 — 키워드 우선순위상 floor_plan/parking 중 하나로 분류
    assert spec.drawing_type in ("floor_plan", "parking")
    assert "bbox_w" in spec.dimensions


def test_content_hash_deterministic_and_pointid():
    a = parse_excel(_make_xlsx(), "x.xlsx")
    b = parse_excel(_make_xlsx(), "x.xlsx")
    assert a.content_hash() == b.content_hash()
    # 결정적 UUID(36자, 하이픈 4개)
    pid = a.point_id()
    assert len(pid) == 36 and pid.count("-") == 4
    # 내용이 다르면 해시도 달라야 함
    c = DesignSpec(source_format="excel", total_area_sqm=999.0)
    assert c.content_hash() != a.content_hash()


def test_point_id_tenant_namespaced():
    """★교차테넌트 멱등 충돌 차단: 동일 내용이라도 테넌트가 다르면 point_id가 달라야 함."""
    a = parse_excel(_make_xlsx(), "x.xlsx")
    b = parse_excel(_make_xlsx(), "x.xlsx")
    # 같은 테넌트 = 멱등(동일 point_id)
    assert a.point_id(tenant_id="T1") == b.point_id(tenant_id="T1")
    # 다른 테넌트 = 다른 point_id(소유표시 덮어쓰기 불가)
    assert a.point_id(tenant_id="T1") != a.point_id(tenant_id="T2")
    # 테넌트 미지정(하위호환) = hash-only
    assert a.point_id() == a.point_id(tenant_id=None)
    assert a.point_id() != a.point_id(tenant_id="T1")
    # 형식 유지(36자 UUID)
    assert len(a.point_id(tenant_id="T1")) == 36


def test_to_payload_includes_discipline():
    # payload에 분야(discipline) 포함 — 분야별 검색 필터용(택소노미 파생)
    s = DesignSpec(source_format="dxf", drawing_type="structural_plan")
    assert s.to_payload()["discipline"] == "구조"
    s2 = DesignSpec(source_format="dxf", drawing_type="floor_plan")
    assert s2.to_payload()["discipline"] == "건축"
    s3 = DesignSpec(source_format="unknown", drawing_type="unknown")
    assert s3.to_payload()["discipline"] is None  # 미상은 None(정직)


def test_detect_drawing_type_taxonomy():
    from app.services.design_ingest.design_spec import (
        DRAWING_TYPES,
        detect_drawing_type,
        drawing_types_by_discipline,
    )
    # 기존 5종 하위호환
    assert detect_drawing_type("배치도") == "site_plan"
    assert detect_drawing_type("1층평면도") == "floor_plan"
    assert detect_drawing_type("남측입면도") == "elevation"
    assert detect_drawing_type("종단면도") == "section"
    assert detect_drawing_type("주차계획도") == "parking"
    # 분야별 신규(복합 키워드 우선 — 'X평면도'가 floor_plan으로 오분류되지 않음)
    assert detect_drawing_type("구조평면도") == "structural_plan"
    assert detect_drawing_type("전기간선계통도") == "electrical_plan"
    assert detect_drawing_type("급배수위생계통도") == "plumbing_plan"
    assert detect_drawing_type("토목우배수도") == "civil_plan"
    assert detect_drawing_type("조경식재도") == "landscape_plan"
    assert detect_drawing_type("천장도") == "ceiling_plan"
    assert detect_drawing_type("창호일람표") == "window_door_schedule"
    assert detect_drawing_type("정북일조분석도") == "daylight_analysis"
    assert detect_drawing_type("a.txt") == "unknown"
    # 택소노미 규모·분야 그룹
    assert len(DRAWING_TYPES) >= 35 and "unknown" in DRAWING_TYPES
    by = drawing_types_by_discipline()
    assert {"구조", "전기", "기계설비", "급배수위생", "소방", "토목", "조경", "통신"} <= set(by)
    # 각 항목 계약(code/ko/set)
    assert all("code" in d and "ko" in d for items in by.values() for d in items)


def test_parse_design_file_routing_and_honesty():
    # PDF는 비전 경로 안내(경고) + 형식 보존. IFC 잘못된 바이트는 파싱실패 경고.
    ifc = parse_design_file(b"dummy", "model.ifc")
    assert ifc.source_format == "ifc" and ifc.meta.get("warnings")
    pdf = parse_design_file(b"dummy", "도면.pdf")
    assert pdf.source_format == "pdf" and pdf.meta.get("warnings")
    unknown = parse_design_file(b"x", "a.txt")
    assert unknown.source_format == "unknown"


def _make_ifc() -> bytes:
    """테스트용 최소 IFC4 — 층 3, 공간 2(거실30·주방20=바닥면적 50), 벽 표면적 999(미합산 확인)."""
    import ifcopenshell
    import ifcopenshell.guid

    ifc = ifcopenshell.file(schema="IFC4")
    oh = ifc.create_entity("IfcOwnerHistory")
    ifc.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="T", OwnerHistory=oh)
    for i in range(3):
        ifc.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(),
                          Name=f"{i + 1}F", OwnerHistory=oh)

    def _add_area(entity, name: str, val: float) -> None:
        q = ifc.create_entity("IfcQuantityArea", Name=name, AreaValue=val)
        eq = ifc.create_entity("IfcElementQuantity", GlobalId=ifcopenshell.guid.new(),
                               Name="Qto", Quantities=[q])
        ifc.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(),
                          RelatingPropertyDefinition=eq, RelatedObjects=[entity])

    for nm, area in (("거실", 30.0), ("주방", 20.0)):
        sp = ifc.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new(), Name=nm, OwnerHistory=oh)
        _add_area(sp, "GrossFloorArea", area)
    # 벽 표면적 — total_area_sqm(바닥면적)에 합산되면 안 됨(공간만 합산)
    wall = ifc.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="W1", OwnerHistory=oh)
    _add_area(wall, "NetSideArea", 999.0)
    return ifc.to_string().encode("utf-8")


def test_parse_ifc_extracts_storeys_spaces_area():
    spec = parse_ifc(_make_ifc(), "model.ifc")
    assert spec.source_format == "ifc" and spec.drawing_type == "bim"
    assert spec.floor_count == 3                     # IfcBuildingStorey ×3
    # ★바닥면적=공간 합(30+20), 벽 표면적 999는 미합산(의미 일관성)
    assert spec.total_area_sqm == 50.0
    assert spec.meta.get("ifc_area_basis") == "space_floor_area"
    areas = {r.name: r.area_sqm for r in spec.rooms}
    assert areas.get("거실") == 30.0 and areas.get("주방") == 20.0  # 공간별 면적
    assert "IfcWall" in spec.layers
    assert not spec.meta.get("warnings")             # 성공 시 경고 없음


def test_parse_ifc_bad_bytes_honest_stub():
    spec = parse_ifc(b"not an ifc file", "bad.ifc")
    assert spec.source_format == "ifc" and spec.meta.get("warnings")  # 정직 고지
    assert spec.total_area_sqm is None and spec.floor_count is None   # 가짜값 없음


def test_parse_design_file_routes_ifc_to_parser():
    spec = parse_design_file(_make_ifc(), "평면도.ifc")
    assert spec.source_format == "ifc" and spec.floor_count == 3


def test_to_embedding_text_only_present_values():
    spec = DesignSpec(source_format="dxf", drawing_type="floor_plan", total_area_sqm=84.0)
    txt = spec.to_embedding_text()
    assert "도면종류:floor_plan" in txt and "면적:84.0㎡" in txt
    # 미추출 값은 텍스트에 등장하지 않음(추정 금지)
    assert "세대수:" not in txt
