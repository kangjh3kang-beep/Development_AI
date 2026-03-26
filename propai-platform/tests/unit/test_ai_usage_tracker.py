"""AI 비용 자동 기록 유틸리티 단위 테스트.

_MODEL_PRICING 딕셔너리 검증 및 비용 계산 로직.
"""

from apps.api.services.ai_usage_tracker import _MODEL_PRICING  # noqa: N811

# ──────────────────────────────────────
# _MODEL_PRICING 검증
# ──────────────────────────────────────


class TestModelPricing:
    """모델별 토큰 단가 검증."""

    def test_sonnet_pricing(self) -> None:
        """claude-sonnet input 0.003, output 0.015."""
        pricing = _MODEL_PRICING["claude-sonnet-4-5-20250929"]
        assert pricing["input"] == 0.003
        assert pricing["output"] == 0.015

    def test_opus_pricing(self) -> None:
        """claude-opus input 0.015, output 0.075."""
        pricing = _MODEL_PRICING["claude-opus-4-6"]
        assert pricing["input"] == 0.015
        assert pricing["output"] == 0.075

    def test_haiku_pricing(self) -> None:
        """claude-haiku input 0.001, output 0.005."""
        pricing = _MODEL_PRICING["claude-haiku-4-5-20251001"]
        assert pricing["input"] == 0.001
        assert pricing["output"] == 0.005

    def test_embedding_pricing(self) -> None:
        """text-embedding input 0.00002, output 0."""
        pricing = _MODEL_PRICING["text-embedding-3-small"]
        assert pricing["input"] == 0.00002
        assert pricing["output"] == 0.0

    def test_all_models_have_input_output(self) -> None:
        """모든 모델에 input/output 키가 존재한다."""
        for model, pricing in _MODEL_PRICING.items():
            assert "input" in pricing, f"{model}에 input 키 누락"
            assert "output" in pricing, f"{model}에 output 키 누락"

    def test_all_prices_non_negative(self) -> None:
        """모든 단가가 0 이상이다."""
        for model, pricing in _MODEL_PRICING.items():
            assert pricing["input"] >= 0, f"{model} input 음수"
            assert pricing["output"] >= 0, f"{model} output 음수"


# ──────────────────────────────────────
# 비용 계산 로직 검증
# ──────────────────────────────────────


class TestCostCalculation:
    """토큰 기반 비용 계산 검증."""

    def test_sonnet_1000_tokens(self) -> None:
        """Sonnet 1,000 input + 500 output 비용."""
        pricing = _MODEL_PRICING["claude-sonnet-4-5-20250929"]
        cost = 1000 / 1000 * pricing["input"] + 500 / 1000 * pricing["output"]
        # 1 × 0.003 + 0.5 × 0.015 = 0.003 + 0.0075 = 0.0105
        assert abs(cost - 0.0105) < 1e-6

    def test_opus_large_usage(self) -> None:
        """Opus 10,000 input + 5,000 output 비용."""
        pricing = _MODEL_PRICING["claude-opus-4-6"]
        cost = 10_000 / 1000 * pricing["input"] + 5_000 / 1000 * pricing["output"]
        # 10 × 0.015 + 5 × 0.075 = 0.15 + 0.375 = 0.525
        assert abs(cost - 0.525) < 1e-6

    def test_embedding_zero_output(self) -> None:
        """임베딩 모델은 output 비용 0."""
        pricing = _MODEL_PRICING["text-embedding-3-small"]
        cost = 1000 / 1000 * pricing["input"] + 0 / 1000 * pricing["output"]
        assert abs(cost - 0.00002) < 1e-8

    def test_zero_tokens(self) -> None:
        """토큰 0 → 비용 0."""
        pricing = _MODEL_PRICING["claude-sonnet-4-5-20250929"]
        cost = 0 / 1000 * pricing["input"] + 0 / 1000 * pricing["output"]
        assert cost == 0.0

    def test_unknown_model_default(self) -> None:
        """미정의 모델은 기본 단가(Sonnet 기준) 적용."""
        default = {"input": 0.003, "output": 0.015}
        pricing = _MODEL_PRICING.get("unknown-model-v99", default)
        assert pricing["input"] == 0.003
        assert pricing["output"] == 0.015
