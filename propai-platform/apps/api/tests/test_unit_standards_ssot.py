"""W1-3 세대·면적 표준 SSOT 계약 — comprehensive와 Top3 추천의 산식 단일출처 게이트.

이 테스트가 깨지면 두 엔진의 세대수가 다시 어긋나기 시작한 것(구 "40 vs 323" 버그
클래스 재발)이므로, 값 수정은 반드시 unit_standards에서만 해야 한다.
"""
from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
from app.services.feasibility.unit_standards import (
    AVG_EXCLUSIVE_AREA_SQM,
    EXCLUSIVE_AREA_RATIO,
    TYPICAL_FAR_PCT,
    get_avg_exclusive_area_sqm,
    get_exclusive_ratio,
    get_typical_far_pct,
)
from app.services.land_intelligence import comprehensive_analysis_service as C

ALL_TYPES = [f"M{i:02d}" for i in range(1, 16)]


def test_tables_cover_all_15_types():
    for t in ALL_TYPES:
        assert t in AVG_EXCLUSIVE_AREA_SQM, t
        assert t in EXCLUSIVE_AREA_RATIO, t
        assert t in TYPICAL_FAR_PCT, t


def test_comprehensive_uses_ssot_tables():
    # 재정의가 아니라 동일 객체 참조여야 함(드리프트 원천 차단).
    assert C.AVG_EXCLUSIVE_AREA is AVG_EXCLUSIVE_AREA_SQM
    assert C.EXCLUSIVE_AREA_RATIO is EXCLUSIVE_AREA_RATIO
    assert C.TYPICAL_FAR is TYPICAL_FAR_PCT


def test_feasibility_v2_delegates_to_ssot():
    svc = FeasibilityServiceV2()
    for t in ALL_TYPES:
        assert svc._get_type_avg_unit_area(t) == get_avg_exclusive_area_sqm(t), t
        assert svc._get_type_efficiency_ratio(t) == get_exclusive_ratio(t), t
        assert svc._get_type_typical_far(t) == get_typical_far_pct(t), t


def test_units_from_gfa_identical_between_engines():
    # 동일 GFA에서 세대수(GFA×전용률÷평균전용)가 두 엔진 경로에서 일치 — 과거 30% 어긋남 회귀 방지.
    gfa = 10_000.0
    svc = FeasibilityServiceV2()
    for t in ("M08", "M09", "M13"):
        units_comprehensive = int(gfa * C.EXCLUSIVE_AREA_RATIO[t] / C.AVG_EXCLUSIVE_AREA[t])
        units_recommend = int(
            gfa * svc._get_type_efficiency_ratio(t) / svc._get_type_avg_unit_area(t)
        )
        assert units_comprehensive == units_recommend, t


def test_unknown_type_falls_back_honestly():
    # 미등록 유형은 임의 합성 없이 보수 폴백(공동주택 표준).
    assert get_avg_exclusive_area_sqm("M99") == 84
    assert get_exclusive_ratio("M99") == 0.75
    assert get_typical_far_pct("M99") == 250
