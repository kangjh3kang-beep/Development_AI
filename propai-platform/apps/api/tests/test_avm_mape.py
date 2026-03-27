"""AVM 서비스 확장 메서드 테스트 (Phase 6 강화).

validate_mape, _apply_regional_weight, _fetch_with_retry 메서드를 검증한다.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.avm_service import AVMService


# ── validate_mape 테스트 ──


class TestValidateMape:
    """MAPE 산출 메서드 테스트."""

    def test_perfect_prediction(self):
        """예측값 == 실제값이면 MAPE 0%."""
        result = AVMService.validate_mape([100.0, 200.0], [100.0, 200.0])
        assert result["mape_pct"] == 0.0
        assert result["is_acceptable"] is True

    def test_within_threshold(self):
        """MAPE 5% 이내면 acceptable."""
        # 실제값 100 대비 예측값 103 → 오차 3%
        result = AVMService.validate_mape([103.0], [100.0])
        assert result["mape_pct"] == pytest.approx(3.0, abs=0.01)
        assert result["is_acceptable"] is True

    def test_exceeds_threshold(self):
        """MAPE 5% 초과면 not acceptable."""
        # 실제값 100 대비 예측값 110 → 오차 10%
        result = AVMService.validate_mape([110.0], [100.0])
        assert result["mape_pct"] == pytest.approx(10.0, abs=0.01)
        assert result["is_acceptable"] is False

    def test_multiple_values(self):
        """여러 건의 MAPE 평균 산출."""
        preds = [105.0, 200.0, 300.0]
        actuals = [100.0, 200.0, 280.0]
        result = AVMService.validate_mape(preds, actuals)
        # (5/100 + 0/200 + 20/280) / 3 * 100
        expected = (0.05 + 0.0 + 20 / 280) / 3 * 100
        assert result["mape_pct"] == pytest.approx(expected, abs=0.01)

    def test_threshold_value(self):
        """threshold_pct는 항상 5.0."""
        result = AVMService.validate_mape([100.0], [100.0])
        assert result["threshold_pct"] == 5.0

    def test_empty_list_raises(self):
        """빈 리스트는 ValueError."""
        with pytest.raises(ValueError, match="비어있을 수 없습니다"):
            AVMService.validate_mape([], [])

    def test_mismatched_length_raises(self):
        """길이 불일치는 ValueError."""
        with pytest.raises(ValueError, match="길이가 같아야"):
            AVMService.validate_mape([1.0, 2.0], [1.0])

    def test_zero_actual_raises(self):
        """실제값 0은 ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError, match="0이므로"):
            AVMService.validate_mape([1.0], [0.0])


# ── _apply_regional_weight 테스트 ──


class TestApplyRegionalWeight:
    """지역별 보정 계수 테스트."""

    def test_gangnam_weight(self):
        """강남 보정 계수 1.15."""
        result = AVMService._apply_regional_weight(1_000_000.0, "강남")
        assert result == pytest.approx(1_150_000.0)

    def test_unknown_region_defaults_to_etc(self):
        """미등록 지역은 기타(0.80) 적용."""
        result = AVMService._apply_regional_weight(1_000_000.0, "제주")
        assert result == pytest.approx(800_000.0)

    def test_etc_weight(self):
        """기타 보정 계수 0.80."""
        result = AVMService._apply_regional_weight(1_000_000.0, "기타")
        assert result == pytest.approx(800_000.0)

    def test_seongnam_weight_neutral(self):
        """성남 보정 계수 1.00 (중립)."""
        result = AVMService._apply_regional_weight(500_000.0, "성남")
        assert result == pytest.approx(500_000.0)

    def test_busan_weight(self):
        """부산 보정 계수 0.85."""
        result = AVMService._apply_regional_weight(1_000_000.0, "부산")
        assert result == pytest.approx(850_000.0)


# ── _fetch_with_retry 테스트 ──


class TestFetchWithRetry:
    """외부 API 재시도 메서드 테스트."""

    def _make_svc(self) -> AVMService:
        """DB 없이 AVMService 인스턴스를 생성한다."""
        svc = object.__new__(AVMService)
        svc._model = None
        svc._model_stage = "fallback"
        return svc

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        """첫 시도에 성공하면 즉시 반환."""
        svc = self._make_svc()

        async def ok_fn():
            return "ok"

        result = await svc._fetch_with_retry(ok_fn, max_retries=3)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        """2회 실패 후 3번째 성공."""
        svc = self._make_svc()
        call_count = 0

        async def flaky_fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("일시 장애")
            return "recovered"

        result = await svc._fetch_with_retry(flaky_fn, max_retries=3)
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """모든 재시도 소진 시 예외 발생."""
        svc = self._make_svc()

        async def always_fail():
            raise ConnectionError("영구 장애")

        with pytest.raises(ConnectionError, match="영구 장애"):
            await svc._fetch_with_retry(always_fail, max_retries=1)
