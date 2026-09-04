"""P0-4(RC8) 일조권(건축법 §61) 라벨 정정 회귀 테스트.

과거 버그: 비주거 전량(녹지·관리·농림·자연환경보전 포함)을 "상업/공업지역 면제"로
하드코딩 라벨링 — 자연녹지 등에서 사실과 다른 서술이 노출됐다(라이브 재현). §61은
전용·일반주거지역에만 적용되고 준주거지역도 적용대상이 아니다.
"""
from __future__ import annotations

from app.services.zoning.development_feasibility_validator import _check_daylighting


def test_natural_green_zone_not_labeled_commercial_industrial():
    """자연녹지 — '상업/공업지역' 오표기 대신 '전용·일반주거지역 한정' 정확 서술."""
    result = _check_daylighting("M11", "자연녹지지역", floor_count=1, building_area=100.0)
    assert result.status == "pass"
    assert "상업" not in result.detail
    assert "공업" not in result.detail
    assert "전용·일반주거지역 한정" in result.detail


def test_management_zone_not_labeled_commercial_industrial():
    """계획관리지역 — 마찬가지로 '상업/공업' 오표기 없이 비적용 사유 정확 서술."""
    result = _check_daylighting("M11", "계획관리지역", floor_count=1, building_area=100.0)
    assert "상업" not in result.detail
    assert "공업" not in result.detail


def test_commercial_zone_still_labeled_commercial_industrial():
    """일반상업지역 — 실제 상업지역은 '상업/공업지역' 사유로 정상 표기(무회귀)."""
    result = _check_daylighting("M07", "일반상업지역", floor_count=10, building_area=500.0)
    assert result.status == "pass"
    assert "상업/공업지역" in result.detail


def test_semi_residential_zone_not_daylighting_applicable():
    """준주거지역 — §61 적용대상 아님(전용·일반주거 한정)이므로 pass + 비적용 서술."""
    result = _check_daylighting("M13", "준주거지역", floor_count=10, building_area=500.0)
    assert result.status == "pass"
    assert "준주거지역" in result.detail


def test_general_residential_zone_unaffected_daylighting_review():
    """제2종일반주거지역(§61 적용대상) — 기존 사선검토 로직 그대로(무회귀)."""
    result = _check_daylighting("M01", "제2종일반주거지역", floor_count=10, building_area=500.0)
    assert result.status == "conditional"
    assert "이격" in result.detail
