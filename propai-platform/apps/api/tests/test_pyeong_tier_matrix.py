"""평수 티어 개발방식 매트릭스 — 사용자 요청("총평수별 가능·불가 개발방식 상세 분류") 검증.

_classify_by_pyeong_tier 는 _scenarios 의 applicable 판정(이미 면적 게이트 반영)을 평수 축으로
재집계하는 순수 additive 뷰. 신규 게이트 없음(결정론·무회귀).
"""
from app.services.development.scenario_simulator import DevelopmentScenarioSimulator as Sim


def _scn(scheme, applicable, est_far=None, notes=""):
    return {"scheme": scheme, "applicable": applicable, "est_far": est_far, "notes": notes, "cons": []}


def test_tier_boundaries():
    """면적별 티어 분류(T1~T5) 정확성."""
    cases = [(100, "T1"), (165, "T2"), (330, "T3"), (1000, "T4"), (3300, "T5"), (50000, "T5")]
    for area, expected in cases:
        out = Sim._classify_by_pyeong_tier(area, [_scn("단순 건축", "가능")])
        assert out["tier"] == expected, f"{area}㎡ → {expected} 여야 함 (현재 {out['tier']})"


def test_pyeong_conversion():
    """㎡→평 환산(÷3.3058)."""
    out = Sim._classify_by_pyeong_tier(330.58, [_scn("단순 건축", "가능")])
    assert abs(out["pyeong"] - 100.0) < 0.5


def test_self_standing_only_small_parcel():
    """단순건축만 가능 → self_standing_only=True + 인접통합 안내."""
    scenarios = [
        _scn("단순 건축", "가능"),
        _scn("지구단위계획 연계", "불가"),
        _scn("역세권 활성화사업", "불가"),
    ]
    out = Sim._classify_by_pyeong_tier(165, scenarios)
    assert out["self_standing_only"] is True
    assert out["possible"] == ["단순 건축"]
    assert "인접" in out["note"]


def test_matrix_sorted_possible_first():
    """매트릭스는 가능>조건부>불가 순 정렬."""
    scenarios = [
        _scn("도시개발사업(도시개발법)", "불가"),
        _scn("단순 건축", "가능"),
        _scn("가로주택정비사업", "조건부"),
    ]
    out = Sim._classify_by_pyeong_tier(2000, scenarios)
    statuses = [m["status"] for m in out["matrix"]]
    assert statuses == ["가능", "조건부", "불가"], f"정렬 오류: {statuses}"


def test_tier_guide_present():
    """5개 티어 가이드(평수구간별 해금 방식) 제공."""
    out = Sim._classify_by_pyeong_tier(500, [_scn("단순 건축", "가능")])
    assert len(out["tier_guide"]) == 5
    assert out["tier_guide"][0]["tier"] == "T1"
    assert "단순건축" in out["tier_guide"][0]["unlocks"]


def test_large_parcel_not_self_standing():
    """대형 부지(가능 방식 다수)는 self_standing_only=False."""
    scenarios = [
        _scn("단순 건축", "가능"),
        _scn("도시개발사업(도시개발법)", "가능"),
        _scn("지구단위계획 연계", "가능"),
    ]
    out = Sim._classify_by_pyeong_tier(20000, scenarios)
    assert out["self_standing_only"] is False
    assert len(out["possible"]) == 3
