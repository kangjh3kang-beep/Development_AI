"""AI 사용량 추적기."""
from collections import defaultdict
from datetime import datetime, timezone, UTC


MODEL_COSTS = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-5-20250929": {"input": 3.0, "output": 15.0},
}


class UsageRecord:
    """AI 사용 기록."""

    __slots__ = (
        "model",
        "input_tokens",
        "output_tokens",
        "cost_usd",
        "timestamp",
        "user_id",
        "purpose",
    )

    def __init__(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: str = "system",
        purpose: str = "",
    ):
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        costs = MODEL_COSTS.get(model, {"input": 1.0, "output": 1.0})
        self.cost_usd = (
            input_tokens * costs["input"] + output_tokens * costs["output"]
        ) / 1_000_000
        self.timestamp = datetime.now(UTC)
        self.user_id = user_id
        self.purpose = purpose

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "purpose": self.purpose,
        }


class AIUsageTracker:
    """모델별 토큰 사용량 + 비용 추적."""

    def __init__(self, daily_budget_usd: float = 100.0):
        self._records: list[UsageRecord] = []
        self._daily_budget = daily_budget_usd

    def track(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user_id: str = "system",
        purpose: str = "",
    ) -> UsageRecord:
        """사용량 기록 추가."""
        record = UsageRecord(model, input_tokens, output_tokens, user_id, purpose)
        self._records.append(record)
        return record

    def get_total_cost(self) -> float:
        """총 비용 조회."""
        return sum(r.cost_usd for r in self._records)

    def get_total_tokens(self) -> int:
        """총 토큰 수 조회."""
        return sum(r.input_tokens + r.output_tokens for r in self._records)

    def get_by_model(self) -> dict:
        """모델별 사용량 집계."""
        result = defaultdict(
            lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "count": 0}
        )
        for r in self._records:
            result[r.model]["input_tokens"] += r.input_tokens
            result[r.model]["output_tokens"] += r.output_tokens
            result[r.model]["cost_usd"] += r.cost_usd
            result[r.model]["count"] += 1
        return dict(result)

    def get_daily_summary(self, date=None) -> dict:
        """일별 요약 조회."""
        if date is None:
            date = datetime.now(UTC).date()
        day_records = [r for r in self._records if r.timestamp.date() == date]
        total_cost = sum(r.cost_usd for r in day_records)
        return {
            "date": str(date),
            "total_cost_usd": round(total_cost, 4),
            "record_count": len(day_records),
            "budget_usd": self._daily_budget,
            "budget_remaining": round(self._daily_budget - total_cost, 4),
            "over_budget": total_cost > self._daily_budget,
        }

    def check_budget(self) -> bool:
        """예산 초과 여부 확인."""
        summary = self.get_daily_summary()
        return not summary["over_budget"]

    @property
    def total_records(self) -> int:
        """총 기록 수."""
        return len(self._records)
