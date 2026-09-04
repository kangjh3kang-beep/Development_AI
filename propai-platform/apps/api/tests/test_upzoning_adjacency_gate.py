"""과제 A(P0) — 종상향 랭킹에 인접성/개발제한구역 게이트 전파 회귀 테스트.

확정 근본원인: comprehensive_analysis_service._calc_upzoning이 adjacency_contiguous를
far_tier_service.calc_upzoning에 전달하지 않아 upzoning_potential._grade의 인접성 감점이
항상 None(무발동)이었다. 파편 9필지+개발제한구역 혼합 부지에서 "지구단위 종상향
가능성 상·1순위"가 산출되던 실버그를 3계층(엔진→배선→응답 노출)에서 검증한다.
"""
from __future__ import annotations

from app.services.zoning.upzoning_potential import UpzoningPotentialAnalyzer


# ────────────────────────────────────────────
# 1) 엔진 계층 — 비연접 파편 필지는 점수와 무관하게 '하' 확정 강등 + blocked_reasons
# ────────────────────────────────────────────
def test_non_contiguous_fragmented_parcels_force_grade_ha_with_blocked_reasons():
    a = UpzoningPotentialAnalyzer()
    r = a.analyze(
        "자연녹지지역", land_area_sqm=20000, sigungu="서울특별시 강남구",
        parcel_count=9, adjacency_contiguous=False,
        special_districts=["개발제한구역"],
    )
    assert r["scenarios"], "시나리오 자체는 산출되어야 함(등급만 강등)"
    for s in r["scenarios"]:
        assert s["feasibility"] == "하", s
        assert s["blocked_reasons"], "강등 사유가 blocked_reasons에 명시되어야 함"
        joined = " ".join(s["blocked_reasons"])
        assert "비연접" in joined
        assert "개발제한" in joined


def test_contiguous_parcels_not_forced_to_ha():
    """연접(adjacency=True)이면 인접성 사유로 강제 강등되지 않는다(무회귀)."""
    a = UpzoningPotentialAnalyzer()
    r = a.analyze(
        "자연녹지지역", land_area_sqm=20000, sigungu="서울특별시 강남구",
        parcel_count=9, adjacency_contiguous=True,
    )
    assert r["scenarios"]
    assert any(s["feasibility"] != "하" for s in r["scenarios"])
    assert all(s["blocked_reasons"] == [] for s in r["scenarios"])


def test_single_parcel_default_unaffected_by_adjacency_gate():
    """단일필지(parcel_count=1, 기본값)는 인접성 게이트 자체가 발동하지 않는다(무회귀)."""
    a = UpzoningPotentialAnalyzer()
    r = a.analyze("자연녹지지역", land_area_sqm=20000, sigungu="서울특별시 강남구")
    assert r["scenarios"]
    assert all(s["blocked_reasons"] == [] for s in r["scenarios"])


# ────────────────────────────────────────────
# 2) 배선 계층 — _calc_upzoning이 integrated의 adjacency_contiguous·parcel_count를
#    far_tier_service.calc_upzoning에 실제로 전달하는지(과거엔 항상 기본값 1/None만 전달됐음).
# ────────────────────────────────────────────
def test_calc_upzoning_forwards_integrated_adjacency_and_parcel_count(monkeypatch):
    from app.services.land_intelligence import far_tier_service
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    captured: dict = {}

    def _fake_calc_upzoning(
        base, zone_type, land_area, location=None, dev_plans=None,
        *, parcel_count=1, adjacency_contiguous=None,
    ):
        captured["parcel_count"] = parcel_count
        captured["adjacency_contiguous"] = adjacency_contiguous
        return {"scenarios": [], "potential_far_range": None}

    monkeypatch.setattr(far_tier_service, "calc_upzoning", _fake_calc_upzoning)

    svc = ComprehensiveAnalysisService()
    integrated = {"parcel_count": 9, "adjacency_contiguous": False, "cluster_count": 3}
    svc._calc_upzoning({}, "자연녹지지역", 5000.0, None, None, integrated)

    assert captured["parcel_count"] == 9
    assert captured["adjacency_contiguous"] is False


def test_calc_upzoning_single_parcel_default_when_integrated_none(monkeypatch):
    """integrated=None(단일필지·미제공)이면 기존과 동일하게 parcel_count=1·adjacency=None."""
    from app.services.land_intelligence import far_tier_service
    from app.services.land_intelligence.comprehensive_analysis_service import (
        ComprehensiveAnalysisService,
    )

    captured: dict = {}

    def _fake_calc_upzoning(
        base, zone_type, land_area, location=None, dev_plans=None,
        *, parcel_count=1, adjacency_contiguous=None,
    ):
        captured["parcel_count"] = parcel_count
        captured["adjacency_contiguous"] = adjacency_contiguous
        return {"scenarios": [], "potential_far_range": None}

    monkeypatch.setattr(far_tier_service, "calc_upzoning", _fake_calc_upzoning)

    svc = ComprehensiveAnalysisService()
    svc._calc_upzoning({}, "자연녹지지역", 500.0, None, None, None)

    assert captured["parcel_count"] == 1
    assert captured["adjacency_contiguous"] is None


# ────────────────────────────────────────────
# 3) 응답 노출 계층 — build_integrated_context가 adjacency_contiguous·cluster_count를
#    integrated_zoning 최상위(응답 공유 계약)로 additive 노출하는지.
# ────────────────────────────────────────────
async def test_integrated_context_exposes_adjacency_contiguous_and_cluster_count():
    from app.services.land_intelligence.comprehensive_analysis_service import (
        build_integrated_context,
    )

    def _square(lon0: float, lat0: float, size: float = 0.001) -> dict:
        lon1, lat1 = lon0 + size, lat0 + size
        return {
            "type": "Polygon",
            "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]],
        }

    parcels = [
        {
            "pnu": "A", "zone_type": "자연녹지지역", "area_sqm": 500.0,
            "farPct": 100.0, "bcrPct": 20.0, "farLegalPct": 100.0, "bcrLegalPct": 20.0,
            "geometry": _square(127.0, 37.0),
        },
        {
            "pnu": "B", "zone_type": "자연녹지지역", "area_sqm": 500.0,
            "farPct": 100.0, "bcrPct": 20.0, "farLegalPct": 100.0, "bcrLegalPct": 20.0,
            "geometry": _square(128.0, 38.0),  # 비연접(멀리 떨어짐)
        },
    ]
    out = await build_integrated_context(parcels)
    assert out is not None
    # 기존 adjacency 자산 그대로(재계산 없음) — additive 최상위 키가 그 값을 그대로 반영.
    assert out["adjacency_contiguous"] == out["adjacency"]["contiguous"] is False
    assert out["cluster_count"] == out["adjacency"]["components"] == 2
