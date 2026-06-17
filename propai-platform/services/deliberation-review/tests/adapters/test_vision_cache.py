"""INC-8 — 비전 응답 캐시: 결정론(동일키 단일호출·동일결과), None 미캐시(재시도), 키 변별."""
from app.adapters.vision.vision_cache import cache_key, clear, get_or_call


def test_cache_hit_calls_once_and_returns_same():
    clear()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return [{"type": "PARKING"}]

    k = cache_key("model-x", "img.png", "prompt")
    r1 = get_or_call(k, fn)
    r2 = get_or_call(k, fn)
    assert r1 == r2 == [{"type": "PARKING"}]
    assert calls["n"] == 1  # 두 번째는 캐시 적중 → 실호출 1회(재현성·비용절감)


def test_none_not_cached_allows_retry():
    clear()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return None  # 라이브 실패

    k = cache_key("m", "i", "p")
    get_or_call(k, fn)
    get_or_call(k, fn)
    assert calls["n"] == 2  # None은 캐시 안 함 → 재시도 허용(graceful)


def test_cache_key_deterministic_and_distinct():
    assert cache_key("m", "i", "p") == cache_key("m", "i", "p")  # 결정론
    assert cache_key("m", "i", "p") != cache_key("m", "i", "p2")  # 프롬프트 다르면 다른 키
    assert cache_key("m", "i", "p") != cache_key("m2", "i", "p")  # 모델 다르면 다른 키
