"""MEDIUM 감사: standard_quantity_estimator height_factor >=30 데드 elif 수선 검증.

배경: `if floor>=15 ... elif floor>=30`은 >=30 가지가 영구 미도달(>=15가 먼저 참)이라
고층(30층+) 전용 완만 보정커브(1.12 base, 0.005/층)가 죽고 15+ 커브(0.008/층)가 적용돼
30층 초과에서 구조비가 과대 산정된다. height_factor는 private 지역변수라 01-콘크리트
물량 비율(지상층수에만 의존)로 간접 검증한다(완전 결정론).
"""
import pytest

from app.services.cost.standard_quantity_estimator import StandardQuantityEstimator


def _concrete_qty(floors: int) -> float:
    items = StandardQuantityEstimator().estimate(
        building_type="공동주택", total_gfa_sqm=10000,
        floor_count_above=floors, floor_count_below=1, structure_type="RC",
    )
    for it in items:
        if it["work_code"] == "01-콘크리트":
            return it["quantity"]
    raise AssertionError("01-콘크리트 항목 없음")


def _height_factor(floors: int) -> float:
    # 콘크리트 물량 = effective_area(지상층수 무관)·std·struct_factor·height_factor.
    # 10층(height_factor=1.0) 대비 비율이 곧 height_factor.
    return _concrete_qty(floors) / _concrete_qty(10)


def test_anchor_10_floors_factor_one():
    assert _height_factor(10) == pytest.approx(1.0, abs=1e-3)


def test_below_15_no_correction():
    assert _height_factor(14) == pytest.approx(1.0, abs=1e-3)


def test_15_to_30_gentle_slope():
    # 20층 = 1.0 + 5*0.008 = 1.04
    assert _height_factor(20) == pytest.approx(1.04, abs=1e-3)


def test_boundary_30_continuous():
    # 경계 30층: 두 커브 모두 1.12 (연속성 — 수선 전후 동일)
    assert _height_factor(30) == pytest.approx(1.12, abs=1e-3)


def test_just_above_30_uses_steep_curve():
    # 31층 = 1.12 + 1*0.005 = 1.125 (버그 코드는 1.0+16*0.008=1.128)
    assert _height_factor(31) == pytest.approx(1.125, abs=1e-3)


def test_highrise_50_uses_highrise_curve():
    # ★핵심: 50층 = 1.12 + 20*0.005 = 1.22 (데드 elif 살아남). 버그 코드는 1.28.
    assert _height_factor(50) == pytest.approx(1.22, abs=1e-3)
