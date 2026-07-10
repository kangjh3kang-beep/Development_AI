"""P4 T1 — 절감 시나리오 서비스(saving_scenarios.py) 단위 테스트.

캡·override 계약(alternatives의 5축 중 3축만 사용)·랭킹 정렬·비절감 필터링을 검증한다.
"""

from __future__ import annotations

import pytest

from app.services.cost.alternatives_engine import ALLOWED_OVERRIDE_KEYS
from app.services.cost.saving_scenarios import (
    MAX_CANDIDATES,
    Variant,
    build_variant_candidates,
    rank_savings,
)

BASE_SPEC = {
    "building_type": "apartment", "total_gfa_sqm": 30000.0,
    "floor_count_above": 20, "floor_count_below": 2, "structure_type": "RC",
}


class TestBuildVariantCandidates:

    def test_capped_at_max_candidates(self):
        candidates = build_variant_candidates(BASE_SPEC)
        assert len(candidates) <= MAX_CANDIDATES

    def test_only_allowed_override_axes(self):
        """생성된 후보의 override 키는 alternatives_engine이 실제로 지원하는 5축 안이어야 한다
        (구조/층수/GFA 3축만 실사용 — 지원 않는 축 발명 금지)."""
        candidates = build_variant_candidates(BASE_SPEC)
        used_keys = {k for c in candidates for k in c.overrides}
        assert used_keys <= ALLOWED_OVERRIDE_KEYS
        assert used_keys <= {"structure_type", "floor_count_above", "total_gfa_sqm"}

    def test_structure_swap_rc_to_sc(self):
        candidates = build_variant_candidates(BASE_SPEC)
        structure_variants = [c for c in candidates if "structure_type" in c.overrides]
        assert len(structure_variants) == 1
        assert structure_variants[0].overrides["structure_type"] == "SC"

    def test_floor_candidates_skip_below_one(self):
        """지상 3층 기준이면 -1/-2는 유지되지만 층수<1이 되는 조합은 생성되지 않아야 한다."""
        spec = {**BASE_SPEC, "floor_count_above": 1}
        candidates = build_variant_candidates(spec)
        floor_variants = [c for c in candidates if "floor_count_above" in c.overrides]
        for c in floor_variants:
            assert c.overrides["floor_count_above"] >= 1

    def test_gfa_candidates_only_reduce(self):
        candidates = build_variant_candidates(BASE_SPEC)
        gfa_variants = [c for c in candidates if "total_gfa_sqm" in c.overrides]
        assert len(gfa_variants) == 2
        for c in gfa_variants:
            assert c.overrides["total_gfa_sqm"] < BASE_SPEC["total_gfa_sqm"]


class TestRankSavings:

    @pytest.mark.asyncio
    async def test_ranked_descending_by_savings(self):
        candidates = build_variant_candidates(BASE_SPEC)
        result = await rank_savings(BASE_SPEC, candidates, top_n=10)
        savings = [c["savings"] for c in result["candidates"]]
        assert savings == sorted(savings, reverse=True)

    @pytest.mark.asyncio
    async def test_only_positive_savings_included(self):
        candidates = build_variant_candidates(BASE_SPEC)
        result = await rank_savings(BASE_SPEC, candidates, top_n=10)
        for c in result["candidates"]:
            assert c["savings"] > 0
            assert c["delta"] < 0

    @pytest.mark.asyncio
    async def test_top_n_respected(self):
        candidates = build_variant_candidates(BASE_SPEC)
        result = await rank_savings(BASE_SPEC, candidates, top_n=1)
        assert len(result["candidates"]) <= 1
        assert result["top_n"] == 1

    @pytest.mark.asyncio
    async def test_gfa_10pct_saving_matches_recomputed_delta(self):
        """절감 최상위 후보(GFA -10%)의 delta_pct가 실제 재계산치와 일치(수치 날조 없음)."""
        candidates = [Variant(
            label="연면적 -10%", overrides={"total_gfa_sqm": 27000.0},
            rationale="테스트",
        )]
        result = await rank_savings(BASE_SPEC, candidates, top_n=5)
        assert len(result["candidates"]) == 1
        c = result["candidates"][0]
        assert c["delta_pct"] == -10.0
        assert c["savings"] == -c["delta"]

    @pytest.mark.asyncio
    async def test_rejects_invalid_base_gfa(self):
        with pytest.raises(ValueError):
            await rank_savings({"total_gfa_sqm": 0}, [], top_n=5)

    @pytest.mark.asyncio
    async def test_evaluated_count_matches_candidate_count(self):
        candidates = build_variant_candidates(BASE_SPEC)
        result = await rank_savings(BASE_SPEC, candidates, top_n=10)
        assert result["evaluated_count"] == len(candidates)
        assert result["saving_count"] <= result["evaluated_count"]
