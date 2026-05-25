"""요청 제한(Rate Limit) 테스트."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestSlidingWindowCounter:
    """슬라이딩 윈도우 카운터 테스트."""

    def test_initial_count_zero(self):
        from app.core.rate_limit import SlidingWindowCounter
        counter = SlidingWindowCounter()
        assert counter.count() == 0

    def test_add_increases_count(self):
        from app.core.rate_limit import SlidingWindowCounter
        counter = SlidingWindowCounter()
        counter.add()
        counter.add()
        assert counter.count() == 2


class TestRateLimiter:
    """RateLimiter 테스트."""

    def test_allows_under_limit(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter(default_limit=5)
        for _ in range(5):
            assert limiter.check("test-key") is True

    def test_blocks_over_limit(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter(default_limit=3)
        for _ in range(3):
            limiter.check("test-key")
        assert limiter.check("test-key") is False

    def test_remaining_count(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter(default_limit=10)
        limiter.check("key-a")
        limiter.check("key-a")
        assert limiter.get_remaining("key-a") == 8

    def test_reset_clears_counter(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter(default_limit=2)
        limiter.check("key-b")
        limiter.check("key-b")
        assert limiter.check("key-b") is False
        limiter.reset("key-b")
        assert limiter.check("key-b") is True

    def test_custom_limit(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter(default_limit=5)
        limiter.set_limit("vip", 1000)
        assert limiter.get_limit("vip") == 1000
        assert limiter.get_limit("normal") == 5

    def test_get_usage_info(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter(default_limit=100, window_seconds=60)
        limiter.check("info-key")
        usage = limiter.get_usage("info-key")
        assert usage["used"] == 1
        assert usage["remaining"] == 99
        assert usage["window_seconds"] == 60

    def test_tenant_tier_free(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter()
        assert limiter.check_tenant("tenant-1", "free") is True

    def test_tenant_tier_enterprise_high_limit(self):
        from app.core.rate_limit import RateLimiter, TIER_LIMITS
        limiter = RateLimiter()
        assert TIER_LIMITS["enterprise"] == 999_999
        assert limiter.check_tenant("tenant-2", "enterprise") is True

    def test_separate_keys_independent(self):
        from app.core.rate_limit import RateLimiter
        limiter = RateLimiter(default_limit=1)
        assert limiter.check("key-x") is True
        assert limiter.check("key-y") is True
        assert limiter.check("key-x") is False
        assert limiter.check("key-y") is False

    def test_get_rate_limiter_singleton(self):
        from app.core.rate_limit import get_rate_limiter, RateLimiter
        limiter = get_rate_limiter()
        assert isinstance(limiter, RateLimiter)
