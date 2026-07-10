"""P0-1(RC1) far_tier_service 폴백 리터럴 제거 — 무날조 회귀 테스트.

라이브 재현: 용인 고기동 자연녹지+개발제한구역+도로 9필지 통합 시 zone 미매칭 필지
(개발제한구역 등)에 60%/200% 하드코딩 폴백이 적용되어 면적가중 블렌드가 139.6%로
오염됐다. 수정: legal_limits_for도 zone_limits도 유효값이 없으면 calc_effective_far가
eff/legal 모두 None을 정직 반환하고, 소비처(_aggregate_integrated_zoning)의 기존 결측
제외 로직이 그 필지를 가중에서 제외해 블렌드가 자연녹지 값(100%)으로 복원되는지 검증한다.
"""
from __future__ import annotations

from app.services.land_intelligence import far_tier_service as fts
from app.services.zoning.special_parcel import _aggregate_integrated_zoning


def test_unmatched_zone_returns_none_not_hardcoded_fallback():
    """zone_type이 법정 SSOT·zone_limits 어디에도 없으면(개발제한구역) 60/200을 지어내지 않는다."""
    out = fts.calc_effective_far({}, "개발제한구역", land_area=1785.0)
    assert out["effective_far_pct"] is None
    assert out["effective_bcr_pct"] is None
    assert out["national_far_pct"] is None
    assert out["national_bcr_pct"] is None
    assert out["far_basis"] == "zone_unmatched"
    assert out["far_optimization"] == {}
    # 정직 고지 문구가 annotations에 포함(임의 수치 미생성).
    assert any("정직" in a for a in out["annotations"])


def test_unmatched_zone_with_zone_limits_override_still_uses_provided_values():
    """zone_limits에 유효값이 있으면(업스트림이 실제로 제공) 정직-None 경로를 타지 않는다."""
    out = fts.calc_effective_far(
        {"zone_limits": {"max_bcr_pct": 40, "max_far_pct": 120}}, "미지정용도", land_area=1000.0,
    )
    assert out["far_basis"] != "zone_unmatched"
    assert out["national_bcr_pct"] == 40.0
    assert out["national_far_pct"] == 120.0


def test_natural_green_zone_unaffected_by_p0_1():
    """정상 자연녹지 단일필지 — 기존과 동일(법정 20/100)하게 산출된다(무회귀)."""
    out = fts.calc_effective_far({}, "자연녹지지역", land_area=500.0)
    assert out["national_bcr_pct"] == 20.0
    assert out["national_far_pct"] == 100.0
    assert out["effective_far_pct"] == 100.0
    assert out["effective_bcr_pct"] == 20.0
    assert out["far_basis"] != "zone_unmatched"


def _p(zone, area, far_eff, bcr_eff, far_legal, bcr_legal, far_basis="조례"):
    """다필지 통합 집계 테스트 필지 dict 헬퍼(_enrich_effective_and_special 부착 형태)."""
    return {
        "zone_type": zone, "area_sqm": area,
        "_far_eff": far_eff, "_bcr_eff": bcr_eff,
        "_far_legal": far_legal, "_bcr_legal": bcr_legal,
        "_far_basis": far_basis,
    }


def test_reproduces_139_6_case_restored_to_100_after_fix():
    """라이브 재현: 자연녹지 8066㎡(eff100) + 개발제한구역 1785㎡(P0-1 수정 후 eff=None 혼입)
    → 면적가중에서 개발제한구역 필지가 제외되어 blended_far_eff가 100.0(자연녹지 단독값)으로
    복원된다(수정 전에는 200% 하드코딩 폴백이 섞여 139.6%가 산출됐다)."""
    gb_eff = fts.calc_effective_far({}, "개발제한구역", land_area=1785.0)
    assert gb_eff["effective_far_pct"] is None  # P0-1 수정 확인(선행조건)

    enriched = [
        _p("자연녹지지역", 8066.0, 100.0, 20.0, 100.0, 20.0, far_basis="법정/조례"),
        _p("개발제한구역", 1785.0, gb_eff["effective_far_pct"], gb_eff["effective_bcr_pct"],
           gb_eff["national_far_pct"], gb_eff["national_bcr_pct"], far_basis=gb_eff["far_basis"]),
    ]
    r = _aggregate_integrated_zoning(enriched)
    assert r["blended_far_eff_pct"] == 100.0, r["blended_far_eff_pct"]
    assert r["blended_far_eff_pct"] != 139.6
    assert r["total_area_sqm"] == 9851.0  # 8066+1785 = 전체 면적(제외는 blend에서만, 면적 합은 보존)
    # 용도 미확인 필지 제외 사유가 far_basis_note에 명시.
    assert "용도 미확인" in r["far_basis_note"], r["far_basis_note"]
    assert "1개" in r["far_basis_note"]
