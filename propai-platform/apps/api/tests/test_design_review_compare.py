"""설계심사 사례비교 결합 테스트 (HUB-C — compare_with_nearby_cases).

case_summary는 PermitCaseService.summarize 출력을 호출자가 주입하는 계약 —
여기서는 고정 정답값으로 결정론 산술(LLM 0)·정직한 빈결과를 검증한다.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.design_review.design_review_service import DesignReviewService


def make_summary(**overrides):
    """고정 사례 통계: 표본 12건, FAR p25/p50/p75=250/380/420, BCR=45/52/58."""
    summary = {
        "available": True,
        "sample_count": 12,
        "far_stats": {"p25": 250.0, "p50": 380.0, "p75": 420.0},
        "bcr_stats": {"p25": 45.0, "p50": 52.0, "p75": 58.0},
    }
    summary.update(overrides)
    return summary


class TestCompareWithNearbyCases:
    """사례비교 — 4밴드 + 표본부족 + graceful."""

    def setup_method(self):
        self.svc = DesignReviewService()

    # ── 4밴드(정답값 고정) ──

    def test_far_above_p75(self):
        """설계 FAR 462 vs 사례 p50 380(p75 420) → above_p75, 중위 대비 +82.0pp."""
        result = self.svc.compare_with_nearby_cases(
            {"far_applied": 462, "bcr_applied": 60}, make_summary()
        )
        assert result["available"] is True
        assert result["sample_count"] == 12
        assert result["far_position"]["band"] == "above_p75"
        assert result["far_position"]["value"] == 462.0
        assert result["far_position"]["p25"] == 250.0
        assert result["far_position"]["p50"] == 380.0
        assert result["far_position"]["p75"] == 420.0
        assert result["vs_median_far_pp"] == 82.0

    def test_far_below_p25(self):
        """설계 FAR 200 < p25 250 → below_p25, 중위 대비 -180.0pp."""
        result = self.svc.compare_with_nearby_cases({"far_applied": 200}, make_summary())
        assert result["far_position"]["band"] == "below_p25"
        assert result["vs_median_far_pp"] == -180.0

    def test_far_p25_p50(self):
        """설계 FAR 300 (250≤300<380) → p25_p50."""
        result = self.svc.compare_with_nearby_cases({"far_applied": 300}, make_summary())
        assert result["far_position"]["band"] == "p25_p50"
        assert result["vs_median_far_pp"] == -80.0

    def test_far_p50_p75(self):
        """설계 FAR 400 (380≤400<420) → p50_p75."""
        result = self.svc.compare_with_nearby_cases({"far_applied": 400}, make_summary())
        assert result["far_position"]["band"] == "p50_p75"
        assert result["vs_median_far_pp"] == 20.0

    def test_band_boundaries(self):
        """경계값: p25→p25_p50, p50→p50_p75, p75→above_p75 (하한 포함 규칙)."""
        for far, expected in [(250, "p25_p50"), (380, "p50_p75"), (420, "above_p75")]:
            result = self.svc.compare_with_nearby_cases({"far_applied": far}, make_summary())
            assert result["far_position"]["band"] == expected, f"FAR {far}"

    def test_bcr_position(self):
        """BCR 60 > p75 58 → above_p75, 중위(52) 대비 +8.0pp."""
        result = self.svc.compare_with_nearby_cases(
            {"far_applied": 300, "bcr_applied": 60}, make_summary()
        )
        assert result["bcr_position"]["band"] == "above_p75"
        assert result["vs_median_bcr_pp"] == 8.0

    # ── 표본부족(정직한 통계 비표기) ──

    def test_insufficient_sample(self):
        """표본 3건(<5) → available True지만 band=insufficient_sample·분위/pp 비표기."""
        result = self.svc.compare_with_nearby_cases(
            {"far_applied": 462, "bcr_applied": 60}, make_summary(sample_count=3)
        )
        assert result["available"] is True
        assert result["sample_count"] == 3
        assert result["far_position"]["band"] == "insufficient_sample"
        assert result["bcr_position"]["band"] == "insufficient_sample"
        assert result["far_position"]["p50"] is None
        assert result["vs_median_far_pp"] is None
        assert result["vs_median_bcr_pp"] is None

    def test_missing_stats_with_enough_samples(self):
        """표본 충분해도 분위 통계 결손 → insufficient_sample(가짜 수치 금지)."""
        result = self.svc.compare_with_nearby_cases(
            {"far_applied": 462}, {"sample_count": 12}
        )
        assert result["available"] is True
        assert result["far_position"]["band"] == "insufficient_sample"
        assert result["vs_median_far_pp"] is None

    # ── graceful(빈결과 정직) ──

    def test_none_case_summary(self):
        """case_summary None → available False(예외 없음)."""
        result = self.svc.compare_with_nearby_cases({"far_applied": 462}, None)
        assert result["available"] is False
        assert result["sample_count"] == 0
        assert result["far_position"] is None
        assert result["vs_median_far_pp"] is None

    def test_empty_case_summary(self):
        """빈 dict → available False."""
        result = self.svc.compare_with_nearby_cases({"far_applied": 462}, {})
        assert result["available"] is False

    def test_upstream_unavailable_passthrough(self):
        """summarize가 available=False 반환 → 그대로 비교 생략."""
        result = self.svc.compare_with_nearby_cases(
            {"far_applied": 462}, {"available": False, "sample_count": 0}
        )
        assert result["available"] is False

    def test_zero_samples(self):
        """표본 0건 → 사례 없음으로 available False."""
        result = self.svc.compare_with_nearby_cases(
            {"far_applied": 462}, make_summary(sample_count=0)
        )
        assert result["available"] is False

    def test_missing_design_value_graceful(self):
        """설계 FAR 결손 → 해당 밴드만 insufficient_sample, BCR은 정상 산출."""
        result = self.svc.compare_with_nearby_cases({"bcr_applied": 50}, make_summary())
        assert result["far_position"]["band"] == "insufficient_sample"
        assert result["far_position"]["value"] is None
        assert result["vs_median_far_pp"] is None
        assert result["bcr_position"]["band"] == "p25_p50"
        assert result["vs_median_bcr_pp"] == -2.0

    # ── 계약 변형 수용 + 결정론 + 하위호환 ──

    def test_flat_key_variant_accepted(self):
        """평면 표기(far_p25 등)도 동일 결과(graceful 수용)."""
        flat = {
            "sample_count": 12,
            "far_p25": 250.0, "far_p50": 380.0, "far_p75": 420.0,
            "bcr_p25": 45.0, "bcr_p50": 52.0, "bcr_p75": 58.0,
        }
        result = self.svc.compare_with_nearby_cases({"far_applied": 462}, flat)
        assert result["far_position"]["band"] == "above_p75"
        assert result["vs_median_far_pp"] == 82.0

    def test_deterministic(self):
        """동일 입력 → 동일 출력(LLM 0, 결정론 산술)."""
        params = {"far_applied": 462, "bcr_applied": 60}
        assert self.svc.compare_with_nearby_cases(params, make_summary()) == \
            self.svc.compare_with_nearby_cases(params, make_summary())

    def test_existing_review_unchanged(self):
        """기존 review_design_parameters 무변경(하위호환 회귀)."""
        result = self.svc.review_design_parameters(
            {"far_applied": 200, "bcr_applied": 50},
            {"max_far": 300, "max_bcr": 60},
        )
        assert result["review_status"] == "pass"
        assert result["error_count"] == 0
        assert result["pass_rate_pct"] == 100.0
        assert result["legal_basis"] == "건축법 제25조"
