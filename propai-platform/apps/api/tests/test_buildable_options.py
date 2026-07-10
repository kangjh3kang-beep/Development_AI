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


def test_greenzone_has_current_options_from_zone_permit_ssot() -> None:
    """자연녹지 — 별표 SSOT(development_type_analyzer)로 현행 단독·근생 등이 채워진다(P0-6/RC5 수정).

    ★과거 버그: design_geometry.ALLOWED_USES_BY_ZONE에 녹지 키가 없어 현행 옵션이 0건이었다
    (개발방식 섹션은 별표 기준 단독·전원 가능이라고 답하는데 랭킹은 0건 — 라이브 재현 모순).
    """
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
    current_opts = [o for o in out["options"] if o["is_current"]]
    assert current_opts, "자연녹지 현행 옵션이 여전히 0건(별표 SSOT 수렴 실패)"
    products = {o["product"] for o in current_opts}
    # 별표17(자연녹지): 단독주택·제1종근린생활시설 등.
    assert "단독·다가구주택" in products
    # 종상향 옵션도 여전히 함께 존재(제거 아님 — additive).
    assert any(o["is_upzoning"] for o in out["options"])


def test_second_general_residential_current_options_unchanged() -> None:
    """제2종일반주거 — 별표 SSOT 전환 후에도 기존 사업유형(공동주택·오피스텔·근생)이 유지된다(무회귀)."""
    out = rank_buildable_options(zone_type="제2종일반주거지역", effective_far_pct=200)
    products = {o["product"] for o in out["options"] if o["is_current"]}
    assert "공동주택(아파트)" in products
    assert "오피스텔" in products
    assert "근린생활시설" in products


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


def test_malformed_upzoning_does_not_crash() -> None:
    """malformed upzoning(비-dict·비-list scenarios·비-dict 요소)도 crash 없이 현행만 반환."""
    for bad in (
        "notadict",                       # 비-dict upzoning
        {"scenarios": "notalist"},        # 비-list scenarios
        {"scenarios": [None, "x", 3]},     # 비-dict 요소
        {"scenarios": [{"feasibility": "상"}]},  # target_zone 누락 요소
    ):
        out = rank_buildable_options(
            zone_type="제2종일반주거지역", effective_far_pct=200, upzoning=bad  # type: ignore[arg-type]
        )
        # 현행 옵션은 정상 산출(종상향만 무시).
        assert out["options"], f"malformed={bad!r} 에서 현행 옵션이 비었음"
        assert all(o["is_current"] for o in out["options"])


def test_unknown_feasibility_falls_back_to_default_weight() -> None:
    """미상 feasibility 문자열 → 0.5 가중치 폴백·난이도 '확인필요'(crash 없이 정직)."""
    upz = _upzoning([
        {
            "target_zone": "제3종일반주거지역", "expected_far_pct_high": 200,
            "feasibility": "이상한값", "path": "X", "path_key": "x", "legal_refs": [],
        }
    ])
    out = rank_buildable_options(
        zone_type="제2종일반주거지역", effective_far_pct=300, upzoning=upz
    )
    up_opts = [o for o in out["options"] if o["is_upzoning"]]
    assert up_opts
    # 0.5 × 200 = 100.
    assert any(o["score"] == 100.0 for o in up_opts)
    assert any(o["permit_difficulty"] == "확인필요" for o in up_opts)


def test_missing_feasibility_defaults_to_medium() -> None:
    """scenario에 feasibility 키 누락 → '중'(0.6) 폴백."""
    upz = _upzoning([
        {"target_zone": "제3종일반주거지역", "expected_far_pct_high": 250,
         "path": "X", "path_key": "x", "legal_refs": []},
    ])
    out = rank_buildable_options(
        zone_type="제2종일반주거지역", effective_far_pct=100, upzoning=upz
    )
    up_opts = [o for o in out["options"] if o["is_upzoning"]]
    assert up_opts and all(o["permit_feasibility"] == "중" for o in up_opts)


def test_duplicate_use_grouped_without_redundant_alternatives() -> None:
    """제1·2종근생이 모두 '근린생활시설'로 그룹화되며, 동일 (via,zone,score) 대안은 중복 제외."""
    out = rank_buildable_options(zone_type="제2종일반주거지역", effective_far_pct=200)
    geun = [o for o in out["options"] if o["product"] == "근린생활시설"]
    assert len(geun) == 1  # 단일 대표로 그룹화
    # 대표와 동일 (via,zone,score)인 무가치 중복 대안은 제외됨.
    for alt in geun[0].get("alternatives", []):
        assert (alt["via"], alt["zone"], alt["score"]) != (
            geun[0]["via"], geun[0]["zone"], geun[0]["score"]
        )


def test_max_options_truncates() -> None:
    """max_options 절단이 적용된다."""
    upz = _upzoning([
        {"target_zone": "제3종일반주거지역", "expected_far_pct_high": 250,
         "feasibility": "상", "path": "A", "path_key": "a", "legal_refs": []},
        {"target_zone": "준주거지역", "expected_far_pct_high": 400,
         "feasibility": "중", "path": "B", "path_key": "b", "legal_refs": []},
    ])
    out = rank_buildable_options(
        zone_type="제2종일반주거지역", effective_far_pct=200, upzoning=upz, max_options=3
    )
    assert len(out["options"]) == 3


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
