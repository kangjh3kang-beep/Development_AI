"""LLM 실패 **사유 분포** 계약.

## 왜 이것이 개선보다 먼저인가

지금 우리가 아는 것은 *"폴백률 80.77%"* 뿐이다(라이브 실측 · `site_analysis` 21/26).
그 안에 절단·타임아웃·스키마 위반이 섞여 있는데 **처방이 셋 다 다르다**.
원인을 모르고 고치면 그 수정이 **다음 조사의 잡음**이 된다.

## 이 스위트가 지키는 두 가지

1. **분류표가 새 실패 유형을 숨기지 못한다.** 어느 라벨에도 안 맞으면 `other` 로 두되
   `error_type`(예외 클래스명)을 **항상** 함께 싣는다 — `other` 안에서도 타입별로 셀 수 있다.
   (사람이 만든 목록이 곧 상한이 되는 것을 막는다.)
2. **분포가 비율과 같은 자리에 있다.** 새 인사이트 타입을 만들지 않고 `fallback_rate` 의
   `metrics_json` 에 붙였다 — 비율만 보고는 어디를 고칠지 정할 수 없다.
"""

from __future__ import annotations

import json

import pytest

from app.services.ai.llm_failure import classify_failure


class TestClassifier:
    @pytest.mark.parametrize(("exc", "expected"), [
        (TimeoutError("deadline exceeded"), "timeout"),
        (json.JSONDecodeError("Unterminated string", "{", 1), "parse"),
        (ConnectionError("connection reset"), "network"),
        (KeyError("ownership"), "shape"),
        (TypeError("list indices must be integers"), "shape"),
        (RuntimeError("Error code: 429 - rate limit exceeded"), "rate_limit"),
        (RuntimeError("Error code: 529 - Overloaded"), "overloaded"),
        (RuntimeError("invalid x-api-key"), "auth"),
        (RuntimeError("Your credit balance is too low"), "auth"),
        (RuntimeError("request timed out after 70s"), "timeout"),
    ])
    def test_알려진_유형을_집계_가능한_라벨로_묶는다(self, exc, expected):
        assert classify_failure(exc) == expected

    def test_핵심_모르는_유형은_other_지만_숨지_않는다(self):
        class BrandNewProviderError(Exception):
            """분류표에 없는 새 예외 — 이런 것이 생겨도 묻히면 안 된다."""

        exc = BrandNewProviderError("무언가 새로운 실패")
        assert classify_failure(exc) == "other"
        # ★`other` 로 묶여도 **예외 타입은 별도로 실린다** — 분류표가 낡아도 새 유형을 셀 수 있다.
        from app.services.ai.base_interpreter import record_llm_failure
        from app.services.growth import capture_service as gcap

        gcap._QUEUE.clear()
        record_llm_failure("svc", exc)
        pl = list(gcap._QUEUE)[-1].get("payload") or {}
        assert pl.get("reason") == "other"
        assert pl.get("error_type") == "BrandNewProviderError", "예외 타입이 안 실렸다 — other 안이 깜깜해진다"
        gcap._QUEUE.clear()

    def test_대조군_서로_다른_예외는_서로_다른_라벨이_된다(self):
        """전부 같은 라벨로 뭉개지면 분포가 정보가 아니다."""
        labels = {
            classify_failure(TimeoutError("x")),
            classify_failure(json.JSONDecodeError("x", "{", 1)),
            classify_failure(RuntimeError("429 rate limit")),
            classify_failure(KeyError("k")),
        }
        assert len(labels) == 4, f"라벨이 뭉개졌다: {labels}"


class TestRecordedPayload:
    def test_실패_이벤트에_사유와_타입이_함께_실린다(self):
        from app.services.ai.base_interpreter import record_llm_failure
        from app.services.growth import capture_service as gcap

        gcap._QUEUE.clear()
        record_llm_failure("registry", json.JSONDecodeError("Unterminated string", "{", 1))
        pl = list(gcap._QUEUE)[-1].get("payload") or {}
        assert pl.get("ok") is False
        assert pl.get("reason") == "parse"
        assert pl.get("error_type") == "JSONDecodeError"
        assert "Unterminated" in (pl.get("error") or ""), "사람이 읽을 원문도 남아야 한다"
        gcap._QUEUE.clear()

    def test_대조군_성공_이벤트에는_사유가_붙지_않는다(self):
        """성공에 reason 이 붙으면 분포 SQL 이 성공까지 세어 분포가 거짓이 된다."""
        import asyncio

        from app.services.ai.base_interpreter import record_llm_response_billing
        from app.services.growth import capture_service as gcap

        class _Resp:
            usage_metadata = {"input_tokens": 1, "output_tokens": 2}

        class _LLM:
            model = "m"

        gcap._QUEUE.clear()
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            record_llm_response_billing(_LLM(), _Resp(), service="registry"))
        pl = list(gcap._QUEUE)[-1].get("payload") or {}
        assert pl.get("ok") is True
        assert "reason" not in pl and "error_type" not in pl
        gcap._QUEUE.clear()


class TestAnalyzerWiring:
    """분포가 **비율과 같은 자리**에 실리는지 — 소스 배선 락."""

    def _src(self) -> str:
        from pathlib import Path
        return (Path(__file__).resolve().parents[1]
                / "app/services/growth/analyzer.py").read_text(encoding="utf-8")

    def test_전제_fallback_rate_산출부가_있다(self):
        assert '"insight_type": "fallback_rate"' in self._src()

    def test_핵심_metrics_에_사유_분포가_실린다(self):
        src = self._src()
        assert '"reasons": reasons' in src, "분포가 인사이트에 안 실린다"
        assert '"top_reason": top' in src, "최다 사유가 없으면 착수 지점을 못 고른다"

    def test_핵심_라벨이_없는_옛_이벤트를_감추지_않는다(self):
        """0으로 세면 분포가 거짓이 된다 — `unlabeled` 로 드러낸다."""
        assert "unlabeled" in self._src()

    def test_핵심_분포_집계가_성공_이벤트를_세지_않는다(self):
        """성공까지 세면 '사유 분포'가 아니라 '호출 분포'가 된다."""
        src = self._src()
        assert "payload->>'ok'='false'" in src
