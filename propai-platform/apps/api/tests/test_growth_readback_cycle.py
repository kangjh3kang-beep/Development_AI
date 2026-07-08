"""성장루프 프롬프트 A/B read-back + 절대 안전밴드 검증(Lane BE-3 잔존 고유분).

★#199(feat/growth-loop)와의 수렴 이력: 임계(threshold.*)·피처(feature.llm_narrative)
read-back 은 main 의 dynamic_config(+analyzer._effective_threshold) 가 정본으로 먼저
머지돼 그 테스트(test_growth_dynamic_config.py)가 커버한다 — 여기서는 이 브랜치의
**고유 잔존분**만 검증한다:
  1) 프롬프트 A/B 후보 read-back — L3(improvement_agent)가 등록한
     prompt_candidates.<service> 를 feature_flags.apply_prompt_ab(화이트리스트 확장)와
     base_interpreter._resolve_prompt_version_async(활성버전 해석)가 실제로 읽는다
     (과거 이중 빈 dict 로 영구 미발화이던 단선의 해소 검증).
  2) 절대 안전밴드(THRESHOLD_ABS_BANDS) — read-back 복리 보정의 장기 드리프트 차단
     (독립리뷰 MEDIUM 회귀잠금).

_FakeSettingsStore 는 schema_guard get/set_setting 계약(키·스코프별 JSON)만 보존한
in-memory 대체물(실DB 불요·결정론). dynamic_config 는 TTL 캐시를 쓰므로 테스트마다
reset_cache() 로 격리한다.
"""

from __future__ import annotations

import app.services.ai.base_interpreter as bi
import app.services.growth.dynamic_config as dynamic_config
import app.services.growth.feature_flags as feature_flags
import app.services.growth.schema_guard as schema_guard


class _FakeSettingsStore:
    """schema_guard.get_setting/set_setting 을 대체하는 in-memory platform_settings."""

    def __init__(self):
        self._store: dict[tuple[str, str], object] = {}

    async def get_setting(self, db, key, scope="global"):
        return self._store.get((key, scope))

    async def set_setting(self, db, key, value, *, scope="global", ttl_expires_at=None,
                          updated_by=None):
        self._store[(key, scope)] = value
        return True

    def seed(self, key, value, scope="global"):
        self._store[(key, scope)] = value


def _patch_settings(monkeypatch, store: _FakeSettingsStore) -> None:
    monkeypatch.setattr(schema_guard, "get_setting", store.get_setting)
    monkeypatch.setattr(schema_guard, "set_setting", store.set_setting)
    dynamic_config.reset_cache()


class _AsyncCtx:
    """async with AsyncSessionLocal() as db 모사(test_reference_feedback.py 패턴 재사용)."""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False


# ════════════════════════════════════════════════════════════════════════════
# 1) 프롬프트 A/B — 순수함수(allowed_versions 주입) + read-back 소비처 2곳
# ════════════════════════════════════════════════════════════════════════════


def test_pick_better_version_adopts_from_readback_candidates():
    stats = {
        "v3": {"pass": 90, "fail": 10, "up": 40, "down": 10, "samples": 100},
        "cand-1": {"pass": 98, "fail": 2, "up": 48, "down": 2, "samples": 100},
    }
    best, meta = feature_flags._pick_better_version(
        "market", stats, allowed_versions=["v3", "cand-1"]
    )
    assert best == "cand-1"
    assert meta["reason"] == "ok"


def test_pick_better_version_empty_candidates_no_adoption():
    """빈 후보(read-back 미등록)면 기존과 동일하게 채택 안 함(무회귀)."""
    stats = {"v3": {"pass": 90, "fail": 10, "up": 40, "down": 10, "samples": 100}}
    best, meta = feature_flags._pick_better_version("market", stats, allowed_versions=[])
    assert best is None
    assert meta["reason"] == "no_candidates"


async def test_dynamic_config_reads_prompt_candidates(monkeypatch):
    """공용 리더 get_prompt_candidates — 등록 포맷({"candidates":[...]}) 파싱·부재 시 []."""
    store = _FakeSettingsStore()
    store.seed("prompt_candidates.svc_x", {"candidates": ["cand-1", "cand-2"]})
    _patch_settings(monkeypatch, store)

    assert await dynamic_config.get_prompt_candidates(object(), "svc_x") == ["cand-1", "cand-2"]
    dynamic_config.reset_cache()
    assert await dynamic_config.get_prompt_candidates(object(), "svc_none") == []
    dynamic_config.reset_cache()


async def test_apply_prompt_ab_accepts_readback_candidate(monkeypatch):
    """apply_prompt_ab 은 정적 PROMPT_AB_CANDIDATES 에 없어도 prompt_candidates.<service>
    (L3 등록분)에 있으면 채택한다(read-back 화이트리스트 확장, 임의 문자열은 여전히 거부)."""
    store = _FakeSettingsStore()
    store.seed("prompt_candidates.market_rb", {"candidates": ["cand-1"], "active": False})
    _patch_settings(monkeypatch, store)

    accepted = await feature_flags.apply_prompt_ab(object(), "market_rb", "cand-1")
    assert accepted["applied"] is True
    assert accepted["reason"] == "ok"

    rejected = await feature_flags.apply_prompt_ab(object(), "market_rb", "cand-999")
    assert rejected["applied"] is False
    assert rejected["reason"] == "not_in_candidates"
    dynamic_config.reset_cache()


async def test_resolve_prompt_version_reads_readback_candidates(monkeypatch):
    """base_interpreter 가 prompt_candidates.<service>(L3)+prompt.<service>(L1 채택)를
    읽어 후보군 내 버전만 활성화한다(이중 빈 dict 단선 해소 검증)."""
    bi._PROMPT_VERSION_CACHE._store.clear()  # noqa: SLF001 — 테스트 격리용 캐시 초기화.
    store = _FakeSettingsStore()
    store.seed("prompt_candidates.svc_rb", {"candidates": ["cand-1"], "active": False})
    store.seed("prompt.svc_rb", {"version": "cand-1", "auto": True})
    _patch_settings(monkeypatch, store)

    import apps.api.database.session as session_mod
    monkeypatch.setattr(session_mod, "AsyncSessionLocal", lambda: _AsyncCtx(object()))

    class _Interp(bi.BaseInterpreter):
        name = "svc_rb"

    interp = _Interp()
    version = await interp._resolve_prompt_version_async()
    assert version == "cand-1"
    bi._PROMPT_VERSION_CACHE._store.clear()  # noqa: SLF001
    dynamic_config.reset_cache()


async def test_resolve_prompt_version_empty_candidates_stays_default(monkeypatch):
    """후보 미등록 service 는 기존처럼 기본 _PROMPT_VERSION 을 유지한다(무회귀)."""
    bi._PROMPT_VERSION_CACHE._store.clear()  # noqa: SLF001
    store = _FakeSettingsStore()  # 후보 없음
    _patch_settings(monkeypatch, store)

    import apps.api.database.session as session_mod
    monkeypatch.setattr(session_mod, "AsyncSessionLocal", lambda: _AsyncCtx(object()))

    class _Interp(bi.BaseInterpreter):
        name = "svc_rb_empty"

    interp = _Interp()
    version = await interp._resolve_prompt_version_async()
    assert version == bi._PROMPT_VERSION
    bi._PROMPT_VERSION_CACHE._store.clear()  # noqa: SLF001
    dynamic_config.reset_cache()


# ════════════════════════════════════════════════════════════════════════════
# 2) 절대 안전밴드 — 복리 드리프트 차단(독립리뷰 MEDIUM 회귀잠금)
# ════════════════════════════════════════════════════════════════════════════


def test_clamp_abs_band_bounds_long_term_drift():
    """★독립리뷰 MEDIUM 회귀잠금: read-back 복리 보정이 절대 안전밴드를 넘지 못한다 —
    상대 ±20% 클램프를 여러 사이클 누적해도 최종값은 THRESHOLD_ABS_BANDS 내로 강제된다."""
    from app.services.growth.feature_flags import (
        THRESHOLD_ABS_BANDS,
        clamp_abs_band,
        clamp_change,
    )

    lo, hi = THRESHOLD_ABS_BANDS["fallback_warn_pct"]
    # 상향 드리프트 시뮬레이션: 매 사이클 +20%를 30회 복리 — 밴드 상한에서 멈춰야 한다.
    v = 20.0
    for _ in range(30):
        v = clamp_abs_band("fallback_warn_pct", clamp_change(v, v * 2))
    assert v == hi
    # 하향 드리프트도 대칭으로 하한에서 멈춘다.
    v = 20.0
    for _ in range(30):
        v = clamp_abs_band("fallback_warn_pct", clamp_change(v, v * 0.1))
    assert v == lo
    # 밴드 미정의 임계는 그대로 통과(기존 동작 불변).
    assert clamp_abs_band("unknown_threshold", 12345.0) == 12345.0
