"""자가성장 L1 산출물 소비 배선 테스트 — dynamic_config + analyzer + feature_flags.

과거 L1 자가수정(feature_flags)이 platform_settings 에 기록한 값을 아무도 읽지
않는(write-only dead-end) 결함의 회귀 방지:
  1) dynamic_config.get_dynamic / get_cached / as_float — TTL 캐시·best-effort 폴백.
  2) analyzer._effective_threshold / _classify_fallback — 자동보정 임계 실소비.
  3) analyzer._llm_enabled — feature.llm_narrative 토글이 env 기본값을 오버레이.
  4) feature_flags.evaluate — current 가 정적상수(15.0)가 아닌 실제 현재 실효값.

DB 는 가짜 세션으로 대체(무목업 원칙과 무관한 단위검증 — 실계약과 동일 SQL 계면).
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.growth import analyzer, dynamic_config


@pytest.fixture(autouse=True)
def _clean_dynamic_cache():
    """테스트 간 TTL 캐시 격리(프로세스-로컬 전역이라 반드시 리셋)."""
    dynamic_config.reset_cache()
    yield
    dynamic_config.reset_cache()


# ── 가짜 DB(schema_guard.get_setting 이 실행하는 SELECT 계면과 동일) ──────────

class _FakeResult:
    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _SettingsDB:
    """platform_settings SELECT 에 (value, ttl) 1행을 돌려주는 가짜 세션."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    async def execute(self, clause, params=None):
        sql = str(clause)
        if "platform_settings" in sql:
            self.calls += 1
            if self.value is None:
                return _FakeResult(row=None)
            return _FakeResult(row=(self.value, None))
        return _FakeResult()

    async def commit(self):
        pass

    async def rollback(self):
        pass


# ════════════════════════════════════════════════════════════════════════════
# 1) dynamic_config 자체
# ════════════════════════════════════════════════════════════════════════════

def test_as_float_extracts_value_dict_and_scalar():
    # L1 autotune 저장 형태({"value": x})와 스칼라 모두 해석
    assert dynamic_config.as_float({"value": 18.0, "previous": 15.0}, 15.0) == 18.0
    assert dynamic_config.as_float(12.5, 15.0) == 12.5
    assert dynamic_config.as_float("9.75", 15.0) == 9.75


def test_as_float_rejects_garbage_and_nonpositive():
    # 비정상 값(문자열 쓰레기·NaN·0 이하·None)은 기본값(폭주 방지)
    assert dynamic_config.as_float("abc", 15.0) == 15.0
    assert dynamic_config.as_float(float("nan"), 15.0) == 15.0
    assert dynamic_config.as_float(-3.0, 15.0) == 15.0
    assert dynamic_config.as_float(0, 15.0) == 15.0
    assert dynamic_config.as_float(None, 15.0) == 15.0
    assert dynamic_config.as_float({"no_value": 1}, 15.0) == 15.0


def test_get_cached_cold_returns_default():
    # 프라임 전(콜드 캐시)엔 default — 순수 판정 함수의 stdlib 검증성 유지
    assert dynamic_config.get_cached("threshold.x", 15.0) == 15.0


def test_get_dynamic_reads_db_then_caches():
    db = _SettingsDB({"value": 18.0})

    async def _go():
        v1 = await dynamic_config.get_dynamic("threshold.fallback_warn_pct", db=db)
        v2 = await dynamic_config.get_dynamic("threshold.fallback_warn_pct", db=db)
        return v1, v2

    v1, v2 = asyncio.run(_go())
    assert v1 == {"value": 18.0}
    assert v2 == {"value": 18.0}
    assert db.calls == 1  # 두 번째는 TTL 캐시 히트(DB 미조회)
    # sync 리더도 같은 캐시를 본다
    assert dynamic_config.get_cached("threshold.fallback_warn_pct") == {"value": 18.0}


def test_get_dynamic_missing_key_negative_cache():
    db = _SettingsDB(None)

    async def _go():
        a = await dynamic_config.get_dynamic("threshold.none", 15.0, db=db)
        b = await dynamic_config.get_dynamic("threshold.none", 15.0, db=db)
        return a, b

    a, b = asyncio.run(_go())
    assert a == 15.0 and b == 15.0
    assert db.calls == 1  # 키 부재도 캐시(반복 DB 조회 방지)


def test_get_dynamic_db_error_returns_default():
    class _BoomDB:
        async def execute(self, *a, **k):
            raise RuntimeError("db down")

    # schema_guard.get_setting 이 예외를 삼켜 None → default (호출경로 비차단)
    out = asyncio.run(dynamic_config.get_dynamic("threshold.x", 15.0, db=_BoomDB()))
    assert out == 15.0


# ════════════════════════════════════════════════════════════════════════════
# 2) analyzer — 실효 임계 소비(자동보정 dead-end 해소)
# ════════════════════════════════════════════════════════════════════════════

def test_effective_threshold_default_when_cold():
    assert analyzer._effective_threshold("fallback_warn_pct") == analyzer.FALLBACK_WARN_PCT


def test_effective_threshold_overlays_primed_setting():
    # L1 이 기록한 threshold.* 값을 프라임하면 판정 기준이 바뀐다
    dynamic_config._put("threshold.fallback_warn_pct", "global", {"value": 5.0})
    assert analyzer._effective_threshold("fallback_warn_pct") == 5.0


def test_effective_threshold_garbage_falls_back():
    dynamic_config._put("threshold.fallback_warn_pct", "global", {"value": "쓰레기"})
    assert analyzer._effective_threshold("fallback_warn_pct") == analyzer.FALLBACK_WARN_PCT


def test_classify_fallback_uses_dynamic_threshold():
    # 기본 임계(15%)에선 10% 는 정상
    assert analyzer._classify_fallback(1, 10) == (None, 10.0)
    # 자동보정이 warn 임계를 5% 로 낮추면 같은 10% 가 warn 으로 판정(실소비 증명)
    dynamic_config._put("threshold.fallback_warn_pct", "global", {"value": 5.0})
    assert analyzer._classify_fallback(1, 10) == ("warn", 10.0)


def test_classify_fallback_min_calls_still_guarded():
    # 분모 부족 가드는 동적 임계와 무관하게 유지
    dynamic_config._put("threshold.fallback_warn_pct", "global", {"value": 1.0})
    assert analyzer._classify_fallback(5, 5) == (None, 0.0)


def test_llm_enabled_toggle_overlays_env(monkeypatch):
    # env 켜짐 + L1 토글 enabled=False → 꺼짐(자동 비활성 소비 지점)
    monkeypatch.setenv("GROWTH_LLM_NARRATIVE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert analyzer._llm_enabled() is True
    dynamic_config._put("feature.llm_narrative", "global", {"enabled": False, "auto": True})
    assert analyzer._llm_enabled() is False
    # env 꺼짐 + 토글 enabled=True → 켜짐(키 존재 전제)
    monkeypatch.setenv("GROWTH_LLM_NARRATIVE", "0")
    dynamic_config._put("feature.llm_narrative", "global", {"enabled": True})
    assert analyzer._llm_enabled() is True
    # 단 키 없으면 어떤 경우에도 off(호출 불가)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert analyzer._llm_enabled() is False


# ════════════════════════════════════════════════════════════════════════════
# 3) feature_flags.evaluate — current 가 실제 현재 실효값(누적수렴)
# ════════════════════════════════════════════════════════════════════════════

class _EvaluateDB(_SettingsDB):
    """evaluate 가 던지는 인사이트 조회 SQL 에도 응답하는 가짜 세션."""

    def __init__(self, value, fallback_pcts):
        super().__init__(value)
        self.pcts = fallback_pcts

    async def execute(self, clause, params=None):
        sql = str(clause)
        if "insight_type='fallback_rate'" in sql:
            return _FakeResult(rows=[(p,) for p in self.pcts])
        if "insight_type='quality_drop'" in sql:
            return _FakeResult(rows=[])
        return await super().execute(clause, params)


def test_evaluate_current_reads_previous_autotuned_value(monkeypatch):
    """직전 자동보정값(18.0)이 다음 사이클의 current 가 된다(15.0 고정루프 제거)."""
    from app.services.growth import feature_flags as ff
    from app.services.growth import healing_rules

    db = _EvaluateDB({"value": 18.0}, [10.0, 12.0, 11.0, 9.0, 13.0])  # baseline=11.0

    async def _fake_guard_counts(_db, _atype, _tkey, _now):
        return 0, 0, None  # 가드 항상 통과(가드 로직은 별도 테스트 대상)

    captured: dict = {}

    async def _fake_apply(_db, name, current, proposed, **kw):
        captured.update({"name": name, "current": current, "proposed": proposed})
        return {"action_id": "t", "applied": True, "setting_key": f"threshold.{name}",
                "old": current, "new": proposed, "clamped": False}

    monkeypatch.setattr(healing_rules, "_guard_counts", _fake_guard_counts)
    monkeypatch.setattr(ff, "apply_threshold_autotune", _fake_apply)

    summary = asyncio.run(ff.evaluate(db))
    assert summary["candidates"] >= 1
    assert captured["name"] == "fallback_warn_pct"
    # ★핵심: 정적상수 15.0 이 아니라 직전 기록값 18.0 기준으로 보정(누적수렴)
    assert captured["current"] == 18.0
    assert captured["proposed"] == 16.5  # baseline 11.0 × 1.5


def test_evaluate_current_falls_back_to_constant_when_unset(monkeypatch):
    """설정 미존재(첫 사이클)면 기존과 동일하게 모듈상수 기준."""
    from app.services.growth import feature_flags as ff
    from app.services.growth import healing_rules

    db = _EvaluateDB(None, [10.0, 12.0, 11.0, 9.0, 13.0])

    async def _fake_guard_counts(_db, _atype, _tkey, _now):
        return 0, 0, None

    captured: dict = {}

    async def _fake_apply(_db, name, current, proposed, **kw):
        captured.update({"current": current})
        return {"action_id": "t", "applied": True}

    monkeypatch.setattr(healing_rules, "_guard_counts", _fake_guard_counts)
    monkeypatch.setattr(ff, "apply_threshold_autotune", _fake_apply)

    asyncio.run(ff.evaluate(db))
    assert captured["current"] == analyzer.FALLBACK_WARN_PCT
