"""설계 대안 선정기 (MCDM + MC) 테스트."""

from app.services.drawing.design_alternative_selector import (
    WEIGHTS,
    DesignAlternativeSelector,
    _normalize_scores,
)

SAMPLE_ALTS = [
    {"name": "A: 최적 밸런스", "profit_score": 80, "legal_score": 90,
     "design_score": 70, "esg_score": 60},
    {"name": "B: 최대 세대수", "profit_score": 90, "legal_score": 85,
     "design_score": 60, "esg_score": 50},
    {"name": "C: 최적 일조", "profit_score": 60, "legal_score": 95,
     "design_score": 85, "esg_score": 90},
]


class TestNormalization:

    def test_normalize_basic(self):
        scores = _normalize_scores(SAMPLE_ALTS, "profit_score")
        assert len(scores) == 3
        # 최소 60→0, 최대 90→1
        assert scores[0] > 0  # 80
        assert abs(scores[1] - 1.0) < 0.01  # 90
        assert abs(scores[2] - 0.0) < 0.01  # 60

    def test_normalize_equal(self):
        alts = [{"x": 5}, {"x": 5}, {"x": 5}]
        scores = _normalize_scores(alts, "x")
        assert all(s == 1.0 for s in scores)


class TestWeights:

    def test_weights_sum_to_one(self):
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_profit_highest(self):
        assert WEIGHTS["profit"] >= max(
            WEIGHTS["legal"], WEIGHTS["design"], WEIGHTS["esg"])


class TestDesignAlternativeSelector:

    def test_simulate_basic(self):
        sel = DesignAlternativeSelector()
        result = sel.simulate(SAMPLE_ALTS, iterations=1000)

        assert "ranked" in result
        assert "mc_results" in result
        assert "winner" in result
        assert len(result["ranked"]) == 3

    def test_mcdm_scores_assigned(self):
        sel = DesignAlternativeSelector()
        result = sel.simulate(SAMPLE_ALTS, iterations=100)
        for alt in result["ranked"]:
            assert "mcdm_score" in alt
            assert 0.0 <= alt["mcdm_score"] <= 1.0

    def test_win_rates_sum_100(self):
        sel = DesignAlternativeSelector()
        result = sel.simulate(SAMPLE_ALTS, iterations=5000)
        rates = [a["mc_win_rate"] for a in result["ranked"]]
        total = sum(rates)
        assert abs(total - 100.0) < 1.0  # 반올림 오차 허용

    def test_winner_is_best(self):
        sel = DesignAlternativeSelector()
        result = sel.simulate(SAMPLE_ALTS, iterations=5000)
        winner = result["winner"]
        # 승자의 MCDM 점수가 최고
        assert winner["mcdm_score"] == max(
            a["mcdm_score"] for a in result["ranked"])

    def test_empty_input(self):
        sel = DesignAlternativeSelector()
        result = sel.simulate([], iterations=100)
        assert result["ranked"] == []
        assert result["winner"] is None

    def test_single_alternative(self):
        sel = DesignAlternativeSelector()
        result = sel.simulate([SAMPLE_ALTS[0]], iterations=100)
        assert len(result["ranked"]) == 1
        assert result["ranked"][0]["mc_win_rate"] == 100.0

    def test_deterministic_with_seed(self):
        sel = DesignAlternativeSelector()
        r1 = sel.simulate(SAMPLE_ALTS, iterations=1000, seed=42)
        r2 = sel.simulate(SAMPLE_ALTS, iterations=1000, seed=42)
        rates1 = [a["mc_win_rate"] for a in r1["ranked"]]
        rates2 = [a["mc_win_rate"] for a in r2["ranked"]]
        assert rates1 == rates2
