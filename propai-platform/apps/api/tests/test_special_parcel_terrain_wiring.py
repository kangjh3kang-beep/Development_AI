"""T1-4 호출부 실배선 계약 테스트 — comprehensive 경로 terrain_facts 전달.

계획(docs/LEGAL_ENGINE_SLOPE_FOREST_PLAN_2026-07-02.md T1-4): terrain 분석 결과가
흐르는 종합분석(comprehensive) 경로에서 detect_special_parcel에 terrain_facts를
전달한다. 계약(E-gate 합의):
    terrain_facts = {"평균경사도_pct": float, "최대경사도_pct": float, "source": str}
원칙(비협상): 전달 데이터 없으면 None=현행 동일(additive), 기존 호출부 무수정 호환
(E-gate 미착지 시그니처에도 TypeError 없이 동작), developability 완화 없음(pass-through).
"""

from __future__ import annotations

from typing import Any

from app.services.land_intelligence.comprehensive_analysis_service import (
    _detect_special_parcel_compat,
    _fetch_terrain_facts,
    _is_forest_slope_candidate,
    _terrain_facts_from_result,
)

# ── 후보 게이트: 임야/산지만 DEM 조회(비후보는 현행 지연·동작 100% 보존) ──


def test_forest_land_category_is_candidate():
    assert _is_forest_slope_candidate({"land_category": "임야", "special_districts": []})


def test_forest_district_is_candidate():
    assert _is_forest_slope_candidate(
        {"land_category": "전", "special_districts": ["보전산지"]}
    )


def test_ordinary_parcel_is_not_candidate():
    assert not _is_forest_slope_candidate({"land_category": "대", "special_districts": []})


def test_non_dict_input_is_not_candidate():
    assert not _is_forest_slope_candidate(None)


# ── terrain_facts 계약 변환(무날조: 불확실 데이터는 None) ──


def _terrain_ok(mean_pct: float = 18.0, max_pct: float = 32.5) -> dict[str, Any]:
    return {"ok": True, "slope": {"mean_pct": mean_pct, "max_pct": max_pct}}


def test_terrain_facts_contract_shape():
    facts = _terrain_facts_from_result(_terrain_ok())
    assert facts == {
        "평균경사도_pct": 18.0,
        "최대경사도_pct": 32.5,
        "source": "SRTM30_DEM",
    }
    assert isinstance(facts["평균경사도_pct"], float)
    assert isinstance(facts["최대경사도_pct"], float)
    assert isinstance(facts["source"], str)


def test_terrain_facts_none_when_not_ok():
    assert _terrain_facts_from_result({"ok": False, "slope": {"mean_pct": 5}}) is None


def test_terrain_facts_none_when_slope_missing_or_non_numeric():
    assert _terrain_facts_from_result({"ok": True}) is None
    assert _terrain_facts_from_result(
        {"ok": True, "slope": {"mean_pct": None, "max_pct": 10}}
    ) is None
    assert _terrain_facts_from_result(None) is None


# ── 조회 배선: 후보만 analyze_terrain 호출, 실패는 전부 None(graceful) ──


async def test_fetch_calls_terrain_for_forest_candidate(monkeypatch):
    calls: list[tuple] = []

    async def _fake_analyze(address, pnu, target_level_m, section_bearing_deg):
        calls.append((address, pnu))
        return _terrain_ok(20.0, 40.0)

    import app.services.terrain.terrain_service as ts

    monkeypatch.setattr(ts, "analyze_terrain", _fake_analyze)
    facts = await _fetch_terrain_facts(
        "강원도 어딘가 산1", "4211010100100010000",
        {"land_category": "임야", "special_districts": []},
    )
    assert calls == [("강원도 어딘가 산1", "4211010100100010000")]
    assert facts == {
        "평균경사도_pct": 20.0,
        "최대경사도_pct": 40.0,
        "source": "SRTM30_DEM",
    }


async def test_fetch_skips_terrain_for_non_candidate(monkeypatch):
    async def _fake_analyze(*a, **k):  # noqa: ANN002, ANN003
        raise AssertionError("비후보 필지에서 DEM 조회가 발생하면 안 된다")

    import app.services.terrain.terrain_service as ts

    monkeypatch.setattr(ts, "analyze_terrain", _fake_analyze)
    facts = await _fetch_terrain_facts(
        "서울 강남구 역삼동 1-1", "1168010100100010000",
        {"land_category": "대", "special_districts": []},
    )
    assert facts is None


async def test_fetch_graceful_on_terrain_failure(monkeypatch):
    async def _fake_analyze(*a, **k):  # noqa: ANN002, ANN003
        raise RuntimeError("DEM 장애")

    import app.services.terrain.terrain_service as ts

    monkeypatch.setattr(ts, "analyze_terrain", _fake_analyze)
    facts = await _fetch_terrain_facts(
        "x", "y", {"land_category": "임야", "special_districts": []}
    )
    assert facts is None


# ── 호환 호출: terrain_facts 지원 시그니처에만 전달(E-gate 병렬 착지 안전) ──


def test_compat_passes_terrain_facts_to_new_signature(monkeypatch):
    received: dict[str, Any] = {}

    def _fake_detect(result: dict, terrain_facts: dict | None = None):
        received["input"] = result
        received["terrain_facts"] = terrain_facts
        return {"is_special": True, "developability": "NEEDS_OFFICIAL_SURVEY"}

    import app.services.zoning.special_parcel as sp_mod

    monkeypatch.setattr(sp_mod, "detect_special_parcel", _fake_detect)
    facts = {"평균경사도_pct": 18.0, "최대경사도_pct": 30.0, "source": "SRTM30_DEM"}
    out = _detect_special_parcel_compat({"land_category": "임야"}, facts)
    assert received["terrain_facts"] == facts
    # developability pass-through — 배선이 게이트를 절대 완화하지 않는다.
    assert out["developability"] == "NEEDS_OFFICIAL_SURVEY"


def test_compat_legacy_signature_without_terrain_facts(monkeypatch):
    """E-gate 미착지(구 시그니처)에서도 TypeError 없이 현행 호출로 폴백."""
    called: dict[str, Any] = {}

    def _fake_detect(result: dict):
        called["input"] = result
        return {"is_special": True, "developability": "BLOCKED"}

    import app.services.zoning.special_parcel as sp_mod

    monkeypatch.setattr(sp_mod, "detect_special_parcel", _fake_detect)
    facts = {"평균경사도_pct": 18.0, "최대경사도_pct": 30.0, "source": "SRTM30_DEM"}
    out = _detect_special_parcel_compat({"land_category": "임야"}, facts)
    assert called["input"] == {"land_category": "임야"}
    assert out["developability"] == "BLOCKED"


def test_compat_no_terrain_facts_calls_plain(monkeypatch):
    """terrain 데이터 부재 시 kwargs 없이 현행과 완전 동일하게 호출(None 유지)."""
    calls: list[Any] = []

    def _fake_detect(result: dict, terrain_facts: dict | None = None):
        calls.append(terrain_facts)
        return None

    import app.services.zoning.special_parcel as sp_mod

    monkeypatch.setattr(sp_mod, "detect_special_parcel", _fake_detect)
    out = _detect_special_parcel_compat({"land_category": "대"}, None)
    assert out is None
    assert calls == [None]


def test_real_detect_special_parcel_compat_smoke():
    """실 모듈 대상 스모크 — 현행/신 시그니처 어느 쪽이든 무예외·게이트 불변.

    임야 입력의 developability는 어떤 경우에도 완화되지 않아야 한다
    (NEEDS_OFFICIAL_SURVEY 계열 유지 — 예비판정 필드 추가만 허용).
    """
    out = _detect_special_parcel_compat(
        {"zone_type": "자연녹지지역", "land_category": "임야", "special_districts": []},
        {"평균경사도_pct": 10.0, "최대경사도_pct": 20.0, "source": "SRTM30_DEM"},
    )
    assert out is not None and out.get("is_special")
    assert out.get("developability") == "NEEDS_OFFICIAL_SURVEY"
