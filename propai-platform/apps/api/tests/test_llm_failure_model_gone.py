"""폐기된 모델 실패가 **「기타」로 묻히고 무한 재시도**되던 것을 잠근다.

## 왜 필요한가 — 라이브 실측 2026-08-27

배포된 진단 라우트(`GET /admin/secrets/llm-health`)를 admin 계정으로 직접 태웠다:

    gemini-2.5-flash   ok=false  NotFound  404 "no longer available to new users"
    gemini-2.5-pro     ok=false  NotFound  404 "no longer available to new users"
    gemini-2.0-flash   ok=false  NotFound  404 "no longer available"
    ★대조군 anthropic  ok=true   "PONG"     ← 조회기·경로 생존
             openai    ok=true              ← 판별력 확인

**`llm_provider.py` 의 google 카탈로그 3모델이 전부 404** 다. 사용자가 google 을 고르면
100% 실패한다. 그런데 `classify_failure` 의 분류표에는:

    _REASON_BY_TEXT:  400 · 401 · 403 · 429 · 529 는 있는데  ★404 만 없다
    _REASON_BY_TYPE:  NotFound 없음

→ 그 실패는 **`other`("기타")** 로 분류됐고, 두 가지 대가를 치렀다:

1. **대시보드에서 「기타」로만 보인다** — 운영자가 *무엇이* 문제인지 알 수 없다.
2. ★**재시도 대상이 된다** — `is_retry_worthwhile("other") == True`.
   모델이 폐기된 것은 **재시도해도 영원히 같은데**, `registry_analysis_service` 는
   그 판정으로 실패 메모를 남길지 정한다(`:591`). 즉 **볼 때마다 LLM 을 다시 산다.**

★그 대가를 **코드가 스스로 경고해 뒀다**(`llm_failure.py:116~119`):

> 같은 문서가 같은 이유로 계속 실패하는데 **볼 때마다 LLM 을 다시 산다.**
> 등기 재발급 누수와 **같은 얼굴**이고, 축만 다르다(벤더 발급 → LLM 토큰).

★그리고 *"모르면 일시 실패로 본다"* 는 보수 규칙은 **`other`(모르는 것)** 를 위한 것이다.
404 는 **모르는 것이 아니다** — 우리가 라이브에서 정확히 관측했다.
"""

from __future__ import annotations

import pytest

from app.services.ai.llm_failure import (
    _DETERMINISTIC,
    classify_failure,
    is_retry_worthwhile,
)


class _NotFound(Exception):
    """프로바이더 SDK 가 던지는 형태(타입 이름으로 갈리는 경로)."""

    __name__ = "NotFound"


#: ★라이브에서 **실제로 관측한** 문구다(지어낸 것이 아니다).
LIVE_404 = (
    "404 This model models/gemini-2.5-flash is no longer available to new users. "
    "Please update your code"
)


def test_live_observed_404_is_model_gone() -> None:
    """회귀 고정 — 라이브에서 관측한 그 문구."""
    assert classify_failure(Exception(LIVE_404)) == "model_gone"


@pytest.mark.parametrize(
    "text",
    [
        "404 models/gemini-2.0-flash is no longer available.",
        "model not found: gpt-9",
        "The model `x` does not exist",
        "this model has been deprecated",
    ],
)
def test_model_gone_variants(text: str) -> None:
    assert classify_failure(Exception(text)) == "model_gone"


def test_notfound_type_is_model_gone() -> None:
    """타입으로도 갈린다 — 프로바이더가 문구를 바꿔도 큰 범주는 유지된다."""
    e = _NotFound("something")
    e.__class__.__name__ = "NotFoundError"
    assert classify_failure(e) == "model_gone"


def test_model_gone_is_deterministic() -> None:
    """★핵심 — 재시도해도 영원히 같다. 여기 없으면 볼 때마다 LLM 을 다시 산다."""
    assert "model_gone" in _DETERMINISTIC
    assert is_retry_worthwhile("model_gone") is False


def test_two_populations_retry_split() -> None:
    """★두 모집단 — 결정론과 일시가 **다른 판정**을 받아야 한다.

    이게 없으면 「전부 재시도 안 함」 구현도, 「전부 재시도」 구현도 통과한다.
    """
    deterministic = ["model_gone", "parse", "shape", "bad_request", "content_filter"]
    transient = ["timeout", "rate_limit", "overloaded", "network", "auth", "other"]
    assert all(is_retry_worthwhile(r) is False for r in deterministic), deterministic
    assert all(is_retry_worthwhile(r) is True for r in transient), transient


def test_404_does_not_steal_auth_or_rate_limit() -> None:
    """★위양성 방지 — 새 규칙이 기존 분류를 빼앗지 않는다(가드의 위양성도 결함).

    `model_gone` 을 `auth` 보다 앞에 뒀으므로, 401/403/429 가 여전히 제 라벨을 받는지 본다.
    """
    assert classify_failure(Exception("401 unauthorized")) == "auth"
    assert classify_failure(Exception("invalid x-api-key")) == "auth"
    assert classify_failure(Exception("Your credit balance is too low")) == "auth"
    assert classify_failure(Exception("429 too many requests")) == "rate_limit"
    assert classify_failure(Exception("bad request")) == "bad_request"


def test_unknown_stays_other() -> None:
    """★대조군 — 모르는 것은 여전히 `other` 이고 재시도 쪽이다(보수 규칙 유지)."""
    assert classify_failure(Exception("brand new provider hiccup")) == "other"
    assert is_retry_worthwhile("other") is True
