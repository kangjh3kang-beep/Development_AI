"""분석 실행 상태 발행 — **인사이트가 0건인 구간의 커버리지가 사라지지 않게** (2026-09-05).

## 왜 (라이브 실측)

성장루프가 **11.3시간째 산출 0** 이었다(관측 최대 간격 8.7시간 → 배수 1.30, **전례 초과**).
원인은 고장이 아니라 **표본 부족**이다 — `09-05 01` 이후 어떤 시간대에도 하한(20)을 넘긴
키가 없었다. 분석기는 매시 돌고(워터마크 `13:11:41Z`) 이벤트도 쌓인다(86건/180분).

★**그런데 그 사실이 어디에도 저장되지 않았다.** 커버리지는 **인사이트 행의 `metrics_json`**
에만 실려서, **0건이면 설명이 통째로 사라진다** — 설명이 가장 필요한 바로 그때.
그 사이 화면은 `open 175` 로 가득 차 **건강해 보였다.**
★워터마크는 **「돌았다」를 말하지 「됐다」를 말하지 않는다.**

## 이 파일이 잠그는 것

**0건 실행에서도 발행된다** · **세 모집단(`judged`/`starved`/`idle`)이 갈린다** ·
**TTL 이 붙는다**(없으면 「멈춤」이 「정상」으로 읽힌다) · **화면 표시 계약을 지킨다** ·
**발행 실패가 배치를 죽이지 않는다**.

★한계(정직 바운딩): 화면에서 실제로 어떻게 보이는지는 **미측정**이다(배포 후 확인 대상).
"""
from __future__ import annotations

import asyncio

import pytest

from app.services.growth import analyzer as A

# ★CI 전수 실행에서는 이 서브모듈이 **먼저 임포트돼 있다.** 그 조건을 이 파일이 **스스로 만들어**
#   로컬 단독 실행과 CI 가 **같은 모집단**을 보게 한다(순서 의존으로 초록이 나지 않게).
from app.services.growth import schema_guard as _real_schema_guard  # noqa: F401

FULL = {"latency_regression": {"judged": 3, "total": 40, "floor": 20},
        "fallback_rate": {"judged": 0, "total": 2, "floor": 10}}
STARVED = {"latency_regression": {"judged": 0, "total": 8, "floor": 20},
           "fallback_rate": {"judged": 0, "total": 0, "floor": 10},
           "quality_drop": {"judged": 0, "total": 0, "floor": 5}}


class TestThreePopulations:
    """★세 모집단 — 둘로 만들면 **표면이 죽은 것이 「정상 유휴」로 읽힌다**."""

    def test_judged_when_any_axis_judged(self):
        assert A.analysis_status_payload(FULL, 2)["state"] == "judged"

    def test_starved_when_all_axes_below_floor(self):
        """오늘의 상태 — 돌았으나 전부 하한 미달. 처방은 **대기**다."""
        assert A.analysis_status_payload(STARVED, 0)["state"] == "starved"

    def test_idle_when_no_axis_at_all(self):
        assert A.analysis_status_payload({}, 0)["state"] == "idle"

    def test_starved_and_judged_are_distinguishable(self):
        """★한쪽만 단언하면 «전부 starved 를 내는 구현»과 구별되지 않는다."""
        assert (A.analysis_status_payload(STARVED, 0)["state"]
                != A.analysis_status_payload(FULL, 2)["state"])


class TestRenderContract:
    """★화면 표시 계약 — 상한을 **상수에서 파생**시킨다(손으로 4·24 를 적지 않는다)."""

    @pytest.mark.parametrize("cov,n", [(FULL, 2), (STARVED, 0), ({}, 0)])
    def test_key_count_within_cap(self, cov, n):
        p = A.analysis_status_payload(cov, n)
        assert len(p) <= A._RENDER_KEY_CAP, (
            f"키 {len(p)}개 > 상한 {A._RENDER_KEY_CAP} — 화면이 「외 N종」으로 버린다. "
            f"★jsonb 가 (길이,바이트순)으로 재정렬하므로 «앞에 놓기» 로는 못 고친다")

    def test_state_survives_even_if_a_value_is_truncated(self):
        """★판별 필드(`state`)는 **24자 절단에 걸리지 않는다**."""
        p = A.analysis_status_payload(STARVED, 0)
        assert len(str(p["state"])) <= A._RENDER_VALUE_CAP

    def test_value_is_a_dict_not_a_list(self):
        """★`ActiveFlagOut.value` 실측: dict ◎ · **list → ValidationError(500)**."""
        assert isinstance(A.analysis_status_payload(STARVED, 0), dict)

    def test_axes_names_are_derived_not_listed(self):
        """★손 매핑표를 두지 않았다 — 새 축이 생기면 **자동으로** 들어온다."""
        p = A.analysis_status_payload({"brand_new_axis": {"judged": 1, "total": 5}}, 1)
        assert "bra" in p["axes"] and "1/5" in p["axes"]


class _FakeGuard:
    def __init__(self, ok=True, boom=False):
        self.ok, self.boom, self.calls = ok, boom, []

    async def set_setting(self, db, key, value, *, scope, ttl_expires_at, updated_by):
        if self.boom:
            raise RuntimeError("boom")
        self.calls.append({"key": key, "value": value, "scope": scope,
                           "ttl": ttl_expires_at, "by": updated_by})
        return self.ok


class _FakeDb:
    def __init__(self): self.committed = self.rolled = 0
    async def commit(self): self.committed += 1
    async def rollback(self): self.rolled += 1


def _publish(monkeypatch, guard, cov, n):
    """★`sys.modules` 만 갈아끼우면 **CI 에서 우회된다.**

    `publish_analysis_status` 는 `from app.services.growth import schema_guard` 로
    **패키지 속성**을 읽는다. 그 서브모듈이 **이미 임포트돼 있으면**(전수 실행에서는 항상)
    파이썬은 `sys.modules` 를 보지 않고 **패키지에 붙은 속성**을 그대로 쓴다.
    ★실측(2026-09-05): 이 파일만 단독 실행하면 초록, **CI 전수에서는 빨강**이었다 —
      ***로컬 단독 실행은 CI 의 모집단이 아니다.***
    → **둘 다** 갈아끼운다. 아래 `len(calls) == 1` 단언이 우회를 잡는다.
    """
    import importlib
    import sys
    import types
    mod = types.ModuleType("app.services.growth.schema_guard")
    mod.set_setting = guard.set_setting
    monkeypatch.setitem(sys.modules, "app.services.growth.schema_guard", mod)
    pkg = importlib.import_module("app.services.growth")
    monkeypatch.setattr(pkg, "schema_guard", mod, raising=False)
    db = _FakeDb()
    ok = asyncio.new_event_loop().run_until_complete(A.publish_analysis_status(db, cov, n))
    return ok, db


class TestPublish:
    def test_ttl_is_attached(self, monkeypatch):
        """★TTL 이 없으면 「분석기가 멈췄다」가 낡은 값으로 남아 「정상」과 구별되지 않는다."""
        g = _FakeGuard()
        ok, _ = _publish(monkeypatch, g, STARVED, 0)
        assert ok and len(g.calls) == 1
        assert g.calls[0]["ttl"] is not None, "TTL 없이 발행하면 멈춤이 정상으로 읽힌다"
        assert g.calls[0]["key"] == A.ANALYSIS_STATUS_SETTING_KEY
        assert g.calls[0]["scope"] == "global"

    def test_publishes_even_with_zero_insights(self, monkeypatch):
        """★두 모집단 — 0건 실행이 **바로 그때** 발행돼야 한다."""
        g0 = _FakeGuard(); _publish(monkeypatch, g0, STARVED, 0)
        g2 = _FakeGuard(); _publish(monkeypatch, g2, FULL, 2)
        assert len(g0.calls) == 1 and len(g2.calls) == 1        # 둘 다 발행
        assert g0.calls[0]["value"]["insights"] == 0
        assert g2.calls[0]["value"]["insights"] == 2

    def test_failure_does_not_raise(self, monkeypatch):
        """★best-effort — 관측이 배치의 임계경로에 있으면 안 된다."""
        g = _FakeGuard(boom=True)
        ok, db = _publish(monkeypatch, g, STARVED, 0)
        assert ok is False and db.rolled >= 1


def test_analyze_window_calls_the_publisher(monkeypatch):
    """★배선 락 — 이름이 소스에 있는 것과 **불리는 것**은 다르다."""
    seen: list[tuple] = []

    async def _spy(db, coverage, n):
        seen.append((coverage, n)); return True

    monkeypatch.setattr(A, "publish_analysis_status", _spy)
    for name in ("_analyze_error_cluster", "_analyze_recurring_verify_errors",
                 "_analyze_selection_contamination"):
        async def _empty(*a, **k): return []
        monkeypatch.setattr(A, name, _empty)
    for name in ("_analyze_fallback_rate", "_analyze_quality_drop", "_analyze_latency_regression"):
        async def _empty_cov(db, w0, w1, cov, _n=name):
            cov[_n.replace("_analyze_", "")] = {"judged": 0, "total": 0, "floor": 5}
            return []
        monkeypatch.setattr(A, name, _empty_cov)

    class _Db:
        async def execute(self, *a, **k): raise AssertionError("스캔 스텁을 우회했다")
        async def commit(self): pass
        async def rollback(self): pass

    from datetime import UTC, datetime
    now = datetime.now(UTC)
    out = asyncio.new_event_loop().run_until_complete(A.analyze_window(_Db(), now, now))
    assert out == [], "인사이트 0건이어야 한다(스텁)"
    assert len(seen) == 1, "★0건 실행에서 발행이 불리지 않았다"
    assert seen[0][1] == 0 and seen[0][0], "커버리지가 실려야 한다"
