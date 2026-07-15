"""WP-F 도면틀 표준(sheet_frame) 단위 테스트.

검증축: (1) 시트 레지스트리·필수시트 판정, (2) 표제란 조립(정직 폴백), (3) SVG 프레임
additive(원본 무회귀·XML 주입 안전), (4) DXF 프레임 additive(무회귀·ezdxf 미설치 시 원본유지),
(5) 시트 매니페스트(편철 순서·존재 여부·해시).
"""

from __future__ import annotations

import pytest

from app.services.cad.sheet_frame import (
    apply_title_block_dxf,
    apply_title_block_svg,
    build_sheet_manifest,
    build_title_block,
    check_required_sheets,
    required_sheet_codes,
    sheet_registry,
    sheet_spec,
)

_SAMPLE_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="400" height="300">'
    '<rect width="400" height="300" fill="white"/><text x="10" y="20">배치도</text></svg>'
)


# ── 1) 시트 레지스트리·필수시트 ──────────────────────────────────────────


def test_sheet_registry_nonempty_and_required_subset():
    """레지스트리에 12건이 등록돼 있고, 필수시트는 그 부분집합이다."""
    reg = sheet_registry()
    assert len(reg) == 12
    codes = {s.code for s in reg}
    for code in required_sheet_codes():
        assert code in codes


def test_required_sheet_codes_exact_set():
    """필수시트(심의 제출 최소 5종) — B-01/B-02-STD/B-03/B-04-F/B-04-S."""
    assert set(required_sheet_codes()) == {"B-01", "B-02-STD", "B-03", "B-04-F", "B-04-S"}


def test_sheet_spec_known_code_returns_registry_entry():
    spec = sheet_spec("B-01")
    assert spec is not None
    assert spec.number == "A-001"
    assert spec.required is True


def test_sheet_spec_unknown_code_returns_none():
    """미등록 코드는 정직하게 None(가짜 사양 생성 금지)."""
    assert sheet_spec("Z-999") is None


def test_check_required_sheets_all_present_ok():
    ok, missing = check_required_sheets(required_sheet_codes())
    assert ok is True
    assert missing == []


def test_check_required_sheets_missing_returns_ordered_list():
    """필수시트 중 일부만 있으면 누락 목록을 편철 순서로 반환(무음 부분산출 금지)."""
    ok, missing = check_required_sheets({"B-01"})
    assert ok is False
    missing_codes = [m["code"] for m in missing]
    assert missing_codes == ["B-02-STD", "B-03", "B-04-F", "B-04-S"]
    assert all({"code", "number", "name"} <= m.keys() for m in missing)


def test_check_required_sheets_empty_input_all_missing():
    ok, missing = check_required_sheets(None)
    assert ok is False
    assert len(missing) == 5


# ── 2) 타이틀블록 조립 ────────────────────────────────────────────────


def test_build_title_block_known_code_uses_registry_number_name():
    tb = build_title_block(
        "B-03", project_name="테스트", scale="1:100", issue_date="2026-07-15",
        content_hash="deadbeef",
    )
    assert tb.sheet_number == "A-201"
    assert tb.sheet_name == "단면도"
    assert tb.scale == "1:100"
    assert tb.issue_date == "2026-07-15"
    assert tb.content_hash == "deadbeef"


def test_build_title_block_unknown_code_falls_back_to_code_itself():
    """미등록 코드는 번호=코드 그대로, 이름은 빈 문자열(가짜 번호 생성 금지)."""
    tb = build_title_block("X-77", project_name="테스트")
    assert tb.sheet_number == "X-77"
    assert tb.sheet_name == ""


def test_build_title_block_missing_issue_date_is_honest_blank():
    """발행일 미상 시 공란('') — now() 로 채우지 않는다(무날조)."""
    tb = build_title_block("B-01", project_name="테스트")
    assert tb.issue_date == ""


# ── 3) SVG 프레임(additive) ──────────────────────────────────────────


def test_apply_title_block_svg_adds_band_and_preserves_original_content():
    tb = build_title_block("B-01", project_name="테스트프로젝트", scale="1:100",
                            issue_date="2026-07-15", content_hash="abc123")
    framed = apply_title_block_svg(_SAMPLE_SVG, tb)
    assert "배치도" in framed  # 원본 콘텐츠 무가림(그대로 존재)
    assert "propai-titleblock" in framed
    assert "테스트프로젝트" in framed
    assert "A-001" in framed  # 레지스트리 시트번호 표기


def test_apply_title_block_svg_expands_viewbox_height():
    """캔버스 높이가 표제란 밴드만큼 늘어난다(원본 도면 영역은 안 줄어듦)."""
    tb = build_title_block("B-01", project_name="P")
    framed = apply_title_block_svg(_SAMPLE_SVG, tb)
    import re

    m = re.search(r'viewBox="0\.00 0\.00 400\.00 (\d+(?:\.\d+)?)"', framed)
    assert m is not None
    new_h = float(m.group(1))
    assert new_h > 300.0


def test_apply_title_block_svg_noop_on_invalid_svg_no_regression():
    """치수를 읽을 수 없는 SVG(빈 문자열·svg 태그 없음)는 원본 그대로 반환(무회귀 안전판)."""
    tb = build_title_block("B-01", project_name="P")
    assert apply_title_block_svg("", tb) == ""
    assert apply_title_block_svg("<div>no svg here</div>", tb) == "<div>no svg here</div>"
    assert apply_title_block_svg("<svg>no close", tb) == "<svg>no close"


def test_apply_title_block_svg_escapes_xml_injection():
    """프로젝트명에 '<>&\"' 가 섞여도 SVG가 깨지지 않게 이스케이프한다(주입 안전)."""
    tb = build_title_block("B-01", project_name='<script>&"evil"</script>')
    framed = apply_title_block_svg(_SAMPLE_SVG, tb)
    assert "<script>" not in framed
    assert "&lt;script&gt;" in framed


# ── 4) DXF 프레임(additive) ──────────────────────────────────────────


def test_apply_title_block_dxf_invalid_bytes_returns_original_no_regression():
    """DXF 파싱 실패(ezdxf 미설치 포함) 시 원본 바이트 그대로(도면을 절대 깨지 않는다)."""
    garbage = b"NOT_A_REAL_DXF_FILE"
    assert apply_title_block_dxf(garbage, build_title_block("B-01", project_name="P")) == garbage


def test_apply_title_block_dxf_empty_bytes_passthrough():
    assert apply_title_block_dxf(b"", build_title_block("B-01", project_name="P")) == b""


def test_apply_title_block_dxf_roundtrip_contains_titleblock_text():
    """ezdxf 설치 환경에서 실제 DXF에 표제란 텍스트 엔티티가 추가되는지 왕복 검증."""
    ezdxf = pytest.importorskip("ezdxf", reason="ezdxf 미설치 — DXF 왕복 테스트 스킵")
    import io

    from app.services.cad.parametric_cad_service import ParametricCADService

    cad = ParametricCADService()
    original = cad.create_floor_plan_dxf(building_width_m=40.0, building_depth_m=20.0, floor_count=5)
    tb = build_title_block("B-01", project_name="테스트프로젝트", scale="1:100",
                            issue_date="2026-07-15", content_hash="abc123", revision="A")
    framed = apply_title_block_dxf(original, tb)
    assert framed != original  # 프레임이 실제로 추가됨(무변화면 버그)

    doc = ezdxf.read(io.StringIO(framed.decode("utf-8")))
    msp = doc.modelspace()
    texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
    joined = " ".join(texts)
    assert "테스트프로젝트" in joined
    assert "A-001" in joined  # 레지스트리 시트번호


# ── 5) 시트 매니페스트 ────────────────────────────────────────────────


def test_build_sheet_manifest_registry_order_and_presence():
    drawings = {"B-01": _SAMPLE_SVG, "B-03": ""}  # B-03은 빈 콘텐츠(미존재로 판정)
    manifest = build_sheet_manifest(drawings)
    by_code = {m["code"]: m for m in manifest}
    assert by_code["B-01"]["present"] is True
    assert by_code["B-01"]["sha256"] is not None
    assert by_code["B-03"]["present"] is False
    assert by_code["B-03"]["sha256"] is None
    # 편철 순서 = 레지스트리 순서(B-01이 B-03보다 먼저)
    codes_in_order = [m["code"] for m in manifest]
    assert codes_in_order.index("B-01") < codes_in_order.index("B-03")


def test_build_sheet_manifest_unregistered_code_appended_honestly():
    """레지스트리 밖 코드도 누락 없이 정직하게 덧붙는다(번호=코드·이름=빈값)."""
    drawings = {"Z-999": _SAMPLE_SVG}
    manifest = build_sheet_manifest(drawings)
    row = next(m for m in manifest if m["code"] == "Z-999")
    assert row["number"] == "Z-999"
    assert row["name"] == ""
    assert row["present"] is True
