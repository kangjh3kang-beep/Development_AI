"""W3-3(P9) 적산 back-test 계약(backtest.py) 단위 테스트 — 무목업 원칙 검증.

검증 범위:
- compute_stats_from_pairs(순수 함수): APE/MAPE/bias/outlier(IQR) 산식·edge case.
- 실적 0건이면 가짜 정확도 없이 null + 사유(무목업).
- record_estimate/record_actual/compute_accuracy 는 DB 미가용 시에도 예외를 흡수하고
  ok=False 로 정직 반환한다(호출부 무중단 — cost_estimate_repository 와 동일 관례).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.services.cost.backtest import (  # noqa: E402
    compute_accuracy,
    compute_stats_from_pairs,
    record_actual,
    record_estimate,
)


class TestComputeStatsEmptyActuals:
    def test_실적_0건이면_null과_사유(self):
        r = compute_stats_from_pairs([])
        assert r["n_pairs"] == 0
        assert r["mape"] is None
        assert r["bias_pct"] is None
        assert r["outliers"] == []
        assert "수집되지 않음" in r["reason"]


class TestComputeStatsAccuracy:
    def test_예측_실적_동일하면_APE_0(self):
        r = compute_stats_from_pairs([{"estimate_id": "a", "predicted_total_won": 100, "actual_total_won": 100}])
        assert r["items"][0]["ape_pct"] == 0.0
        assert r["items"][0]["bias_pct"] == 0.0
        assert r["mape"] == 0.0

    def test_과대추정은_bias_양수(self):
        r = compute_stats_from_pairs([{"estimate_id": "a", "predicted_total_won": 120, "actual_total_won": 100}])
        assert r["items"][0]["bias_pct"] == pytest.approx(20.0)
        assert r["items"][0]["ape_pct"] == pytest.approx(20.0)

    def test_과소추정은_bias_음수(self):
        r = compute_stats_from_pairs([{"estimate_id": "a", "predicted_total_won": 80, "actual_total_won": 100}])
        assert r["items"][0]["bias_pct"] == pytest.approx(-20.0)
        assert r["items"][0]["ape_pct"] == pytest.approx(20.0)  # APE는 절대값(방향 무시)

    def test_actual_0이면_APE_None(self):
        # 나눗셈 회피(정의 불가) — 가짜값 생성 금지.
        r = compute_stats_from_pairs([{"estimate_id": "a", "predicted_total_won": 100, "actual_total_won": 0}])
        assert r["items"][0]["ape_pct"] is None
        assert r["mape"] is None  # 유효 표본 0건이면 MAPE도 None

    def test_MAPE는_APE의_평균(self):
        pairs = [
            {"estimate_id": "a", "predicted_total_won": 110, "actual_total_won": 100},  # APE 10
            {"estimate_id": "b", "predicted_total_won": 90, "actual_total_won": 100},   # APE 10
        ]
        r = compute_stats_from_pairs(pairs)
        assert r["mape"] == pytest.approx(10.0)
        assert r["bias_pct"] == pytest.approx(0.0)  # 방향 상쇄(과대+과소)


class TestOutlierDetection:
    def test_소표본_n미만4는_이상치_판정_생략(self):
        pairs = [
            {"estimate_id": "a", "predicted_total_won": 100, "actual_total_won": 100},
            {"estimate_id": "b", "predicted_total_won": 100, "actual_total_won": 50},
        ]
        r = compute_stats_from_pairs(pairs)
        assert r["outliers"] == []
        assert r["outlier_bounds"] is None

    def test_극단치_IQR로_검출(self):
        pairs = [
            {"estimate_id": "a", "predicted_total_won": 105, "actual_total_won": 100},
            {"estimate_id": "b", "predicted_total_won": 95, "actual_total_won": 100},
            {"estimate_id": "c", "predicted_total_won": 102, "actual_total_won": 100},
            {"estimate_id": "d", "predicted_total_won": 500, "actual_total_won": 100},  # 극단
        ]
        r = compute_stats_from_pairs(pairs)
        assert "d" in r["outliers"]
        assert "a" not in r["outliers"]


class TestGracefulDbFailure:
    """DB(async_session_factory) 접속 불가 환경에서도 예외 없이 ok=False 로 정직 반환.

    tests/test_source_snapshot.py 의 monkeypatch(dbm.async_session_factory, _boom) 관례와
    동일 — 실 DB 가용 여부(로컬 개발 postgres 유무)에 환경의존하지 않고 결정론적으로
    예외 경로를 강제한다(CI 는 DB 서비스 없이 pytest 를 돌리므로 이 경로가 실제로도 정상 상태).
    """

    @pytest.mark.asyncio
    async def test_record_estimate_실패해도_ok_false(self, monkeypatch):
        import app.core.database as dbm

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(dbm, "async_session_factory", _boom)
        r = await record_estimate(estimate_id="w3s3-test-nonexistent", predicted_total_won=1000)
        assert r["ok"] is False

    @pytest.mark.asyncio
    async def test_record_actual_실패해도_ok_false(self, monkeypatch):
        import app.core.database as dbm

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(dbm, "async_session_factory", _boom)
        r = await record_actual(estimate_id="w3s3-test-nonexistent", actual_total_won=1000)
        assert r["ok"] is False

    @pytest.mark.asyncio
    async def test_compute_accuracy_실패해도_ok_false_및_null(self, monkeypatch):
        import app.core.database as dbm

        def _boom():
            raise RuntimeError("db down")

        monkeypatch.setattr(dbm, "async_session_factory", _boom)
        r = await compute_accuracy()
        assert r["ok"] is False
        assert r["mape"] is None
        assert r["reason"] is not None


class TestRoundTripAgainstDb:
    """실 DB(로컬 개발 postgres)가 가용할 때만 record_estimate→record_actual→compute_accuracy
    풀 라운드트립을 검증한다(가용 안 하면 skip — CI 의 무DB 실행과 공존).

    ★공유 개발 DB 오염 방지: 세션 유일 estimate_id(uuid)를 쓰고, finally 에서 반드시 정리한다.
    """

    @pytest.mark.asyncio
    async def test_예측_실적_기록후_APE_산출(self):
        import uuid

        try:
            from sqlalchemy import text

            from app.core.database import async_session_factory
            async with async_session_factory() as db:
                await db.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 — DB 미가용 환경(CI 등)에서는 라운드트립 생략
            pytest.skip("로컬 개발 DB 미가용 — 라운드트립 skip(CI 기본 상태)")

        eid = f"w3s3-roundtrip-{uuid.uuid4().hex[:12]}"
        try:
            rec = await record_estimate(estimate_id=eid, predicted_total_won=1_000_000)
            assert rec["ok"] is True
            act = await record_actual(estimate_id=eid, actual_total_won=900_000, source_note="테스트")
            assert act["ok"] is True

            result = await compute_accuracy()
            assert result["ok"] is True
            matched = [it for it in result["items"] if it["estimate_id"] == eid]
            assert len(matched) == 1
            assert matched[0]["ape_pct"] == pytest.approx(11.11, abs=0.05)
        finally:
            # ★공유 개발 DB 정리 — 테스트 잔여물이 다른 세션/개발자를 오염시키지 않도록.
            from sqlalchemy import text

            from app.core.database import async_session_factory
            async with async_session_factory() as db:
                await db.execute(
                    text("DELETE FROM cost_backtest_prediction WHERE estimate_id = :e"), {"e": eid})
                await db.execute(
                    text("DELETE FROM cost_backtest_actual WHERE estimate_id = :e"), {"e": eid})
                await db.commit()
