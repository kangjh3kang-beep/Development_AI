"""Stage 1 — 건축가능항목 선정·랭킹(buildable_options) 결정론 테스트.

인허가가능성 × 가용용적률 랭킹·현행/종상향 버킷 분리·별표 허용용도 승격·정직 경계를 검증.
신규 의존성 0(결정론 순수함수) — DB/네트워크 불필요.
"""

from __future__ import annotations

from app.services.land_intelligence.buildable_options import rank_buildable_options


def _upzoning(scenarios: list[dict]) -> dict:
    """UpzoningPotentialAnalyzer.analyze 출력 형태의 최소 스텁."""
    return {"current_zone": "제2종일반주거지역", "scenarios": scenarios}


def test_zone_none_returns_empty_honest() -> None:
    out = rank_buildable_options(zone_type=None, effective_far_pct=200)
    assert out["options"] == []
    assert out["top_recommendation"] is None
    assert "용도지역 미상" in out["summary"]


def test_current_zone_allowed_uses_promoted() -> None:
    """제2종일반주거 — 별표 허용용도가 건축가능항목으로 승격되고 현행 far가 점수에 반영."""
    out = rank_buildable_options(zone_type="제2종일반주거지역", effective_far_pct=200)
    products = {o["product"] for o in out["options"]}
    # 별표: 단독주택·공동주택·근생·오피스텔.
    assert "공동주택(아파트)" in products
    assert "오피스텔" in products
    assert "근린생활시설" in products
    # 현행 옵션은 전부 인허가 '현행'(가장 용이)·is_current.
    assert all(o["permit_feasibility"] == "현행" for o in out["options"])
    assert all(o["is_current"] for o in out["options"])
    # 현행 점수 = 1.0 × 200.
    assert out["top_recommendation"]["score"] == 200.0
    assert out["top_recommendation"]["achievable_far_pct"] == 200


def test_upzoning_high_far_outranks_current_when_score_higher() -> None:
    """종상향(제3종 far 250·가능성 상=0.85→212.5)이 현행(200)보다 점수 높으면 상위 랭크."""
    upz = _upzoning([
        {
            "target_zone": "제3종일반주거지역",
            "expected_far_pct_high": 250,
            "feasibility": "상",
            "path": "역세권 활성화사업(용도상향)",
            "path_key": "역세권활성화",
            "legal_refs": [],
        }
    ])
    out = rank_buildable_options(
        zone_type="제2종일반주거지역", effective_far_pct=200, upzoning=upz
    )
    top = out["top_recommendation"]
    assert top["is_upzoning"] is True
    assert top["zone"] == "제3종일반주거지역"
    assert top["score"] == round(0.85 * 250, 1)  # 212.5
    # 현행/종상향 버킷이 둘 다 존재(같은 사업유형이라도 의사결정 분리).
    buckets = {o["is_current"] for o in out["options"]}
    assert buckets == {True, False}


def test_low_feasibility_upzone_does_not_overrank() -> None:
    """가능성 '하'(0.35) 종상향은 용적률이 높아도 현행보다 과대평가되지 않는다."""
    upz = _upzoning([
        {
            "target_zone": "준주거지역",
            "expected_far_pct_high": 400,
            "feasibility": "하",
            "path": "지구단위계획 수립",
            "path_key": "지구단위계획수립",
            "legal_refs": [],
        }
    ])
    out = rank_buildable_options(
        zone_type="제2종일반주거지역", effective_far_pct=200, upzoning=upz
    )
    # 종상향 점수 = 0.35×400 = 140 < 현행 200 → 현행이 top.
    assert out["top_recommendation"]["is_current"] is True
    assert out["top_recommendation"]["score"] == 200.0


def test_greenbelt_no_current_options_only_upzoning() -> None:
    """자연녹지(별표 미매핑) — 현행 옵션 없음(정직), 종상향 후 주거지역 옵션만."""
    upz = {
        "current_zone": "자연녹지지역",
        "scenarios": [
            {
                "target_zone": "제1종일반주거지역",
                "expected_far_pct_high": 200,
                "feasibility": "중",
                "path": "도시개발사업(도시개발법)",
                "path_key": "도시개발사업",
                "legal_refs": [],
            }
        ],
    }
    out = rank_buildable_options(
        zone_type="자연녹지지역", effective_far_pct=80, upzoning=upz
    )
    # 현행(자연녹지) 별표 허용용도 미매핑 → 현행 옵션 0.
    assert all(o["is_upzoning"] for o in out["options"])
    assert len(out["options"]) >= 1
    assert out["top_recommendation"]["zone"] == "제1종일반주거지역"


def test_commercial_zone_residential_is_mixed_use() -> None:
    """상업지역 공동주택은 사업유형 '주상복합'으로 라벨링(massing 분류 반영)."""
    out = rank_buildable_options(zone_type="일반상업지역", effective_far_pct=800)
    products = {o["product"] for o in out["options"]}
    assert "주상복합" in products  # 일반상업+공동주택 → 주상복합
    # 판매·업무·숙박 등 상업 사업유형도 존재.
    assert any(p in products for p in ("판매시설(상업)", "업무시설(오피스)", "숙박시설"))


def test_far_unknown_falls_back_to_legal_and_scores_low() -> None:
    """현행 실효 far 미상 → 법정상한 폴백·far_source 정직 표기."""
    out = rank_buildable_options(zone_type="제2종일반주거지역", effective_far_pct=None)
    top = out["top_recommendation"]
    assert top is not None
    # 법정상한 폴백(제2종일반주거 법정 250%)·source 표기.
    assert "법정" in top["far_source"]
    assert top["achievable_far_pct"] is not None


def test_options_sorted_descending_by_score() -> None:
    upz = _upzoning([
        {
            "target_zone": "제3종일반주거지역", "expected_far_pct_high": 250,
            "feasibility": "상", "path": "역세권활성화", "path_key": "역세권활성화",
            "legal_refs": [],
        },
        {
            "target_zone": "준주거지역", "expected_far_pct_high": 400,
            "feasibility": "중", "path": "지구단위계획수립", "path_key": "지구단위계획수립",
            "legal_refs": [],
        },
    ])
    out = rank_buildable_options(
        zone_type="제2종일반주거지역", effective_far_pct=200, upzoning=upz
    )
    scores = [o["score"] for o in out["options"]]
    assert scores == sorted(scores, reverse=True)
