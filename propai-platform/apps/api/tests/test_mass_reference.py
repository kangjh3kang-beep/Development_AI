"""mass_backbone P2 — get_mass_reference(매스 레퍼런스 조회) 단위테스트(lookup stub·무 DB).

사업유형명→매스종류 매핑(재개발·주상복합 등)·결측 제외·region/표본 없음 None 검증.
"""
import asyncio

from app.services.mass_backbone import mass_reference


def _call(region, label, rows, monkeypatch):
    """get_mass_reference 호출 → (반환, lookup이 받은 인자) 반환. lookup_templates는 stub."""
    captured: dict = {}

    async def _stub_lookup(db, *, region, building_type, zone_code=None):
        captured["region"] = region
        captured["building_type"] = building_type
        return rows

    monkeypatch.setattr(mass_reference, "lookup_templates", _stub_lookup)
    result = asyncio.run(
        mass_reference.get_mass_reference(object(), region=region, building_type_label=label)
    )
    return result, captured


def test_get_mass_reference_normalizes_label_and_returns_typical(monkeypatch):
    rows = [{"region": "분당구", "building_type": "오피스텔", "sample_count": 30,
             "median_bcr_pct": 60.0, "median_far_pct": 600.0, "median_floors": 15.0,
             "median_total_area_sqm": 9000.0}]
    out, seen = _call("분당구", "오피스텔(업무복합)", rows, monkeypatch)
    assert seen["building_type"] == "오피스텔"   # 라벨 정규화
    assert out["region"] == "분당구" and out["sample_count"] == 30
    assert out["median_bcr_pct"] == 60.0 and out["median_far_pct"] == 600.0
    assert out["source"].startswith("mass_backbone")


def test_get_mass_reference_skips_missing_bcr_far(monkeypatch):
    # 건폐/용적 결측(None)이면 채택 안 함 → None(가짜 전형 금지)
    rows = [{"region": "동탄구", "building_type": "창고시설", "sample_count": 11,
             "median_bcr_pct": None, "median_far_pct": None, "median_floors": 1.0,
             "median_total_area_sqm": 255.7}]
    out, _ = _call("동탄구", "창고", rows, monkeypatch)
    assert out is None


def test_get_mass_reference_no_region_or_empty(monkeypatch):
    # region 없으면 조회 없이 None
    assert asyncio.run(
        mass_reference.get_mass_reference(object(), region=None, building_type_label="공동주택")
    ) is None
    # 표본 없으면 None
    out, _ = _call("위례", "공동주택", [], monkeypatch)
    assert out is None


def test_get_mass_reference_maps_development_types(monkeypatch):
    # ★사업유형명(재개발·재건축·일반분양·주상복합 등)이 '기타'로 떨어지지 않고 공동주택 매스로 매핑(H1).
    rows = [{"region": "분당구", "building_type": "공동주택", "sample_count": 84,
             "median_bcr_pct": 16.8, "median_far_pct": 89.2, "median_floors": 5.0,
             "median_total_area_sqm": 2879.8}]
    for label in ["재개발", "재건축", "일반분양", "주상복합", "도시형생활주택", "지역주택조합", "공공임대"]:
        out, seen = _call("분당구", label, rows, monkeypatch)
        assert seen["building_type"] == "공동주택", f"{label} → 공동주택 매핑 실패"
        assert out is not None and out["building_type"] == "공동주택"
    # 지식산업센터·오피스텔·타운하우스도 올바른 매스종류로
    _, seen = _call("분당구", "지식산업센터", rows, monkeypatch)
    assert seen["building_type"] == "지식산업센터"
    _, seen = _call("분당구", "타운하우스", rows, monkeypatch)
    assert seen["building_type"] == "단독주택"
