"""cost_index_service(KOSIS 건설공사비지수 시점보정) — 무날조 폴백·계수 산출 계약 테스트."""

from __future__ import annotations

import pytest

from app.services.cost import cost_index_service as idx


def test_kosis_key_reads_env_override(monkeypatch):
    monkeypatch.setenv("KOSIS_API_KEY", "ENV-KEY")
    assert idx._kosis_key() == "ENV-KEY"
    assert idx.kosis_ready() is True


def test_kosis_key_missing_returns_empty(monkeypatch):
    monkeypatch.delenv("KOSIS_API_KEY", raising=False)
    monkeypatch.setattr("app.core.config.settings.KOSIS_API_KEY", "", raising=False)
    assert idx._kosis_key() == ""
    assert idx.kosis_ready() is False


# ── _index_for_ym: 동일 시점 다중분류 시 '총지수/전체/계' 우선 ──


def test_index_for_ym_prefers_total_class():
    rows = [
        {"PRD_DE": "202601", "C1_NM": "주거용건물", "DT": "150.0"},
        {"PRD_DE": "202601", "C1_NM": "총지수", "DT": "148.5"},
    ]
    assert idx._index_for_ym(rows, "202601") == 148.5


def test_index_for_ym_falls_back_to_first_when_no_total():
    rows = [{"PRD_DE": "202601", "C1_NM": "주거용건물", "DT": "150.0"}]
    assert idx._index_for_ym(rows, "202601") == 150.0


def test_index_for_ym_no_match_returns_none():
    rows = [{"PRD_DE": "202601", "DT": "150.0"}]
    assert idx._index_for_ym(rows, "202512") is None


def test_index_for_ym_bad_value_returns_none():
    rows = [{"PRD_DE": "202601", "DT": "N/A"}]
    assert idx._index_for_ym(rows, "202601") is None


# ── escalation_factor: 무날조 폴백 ──


async def test_escalation_factor_no_series_unavailable(monkeypatch):
    async def _empty_series():
        return []

    monkeypatch.setattr(idx, "_get_series", _empty_series)
    result = await idx.escalation_factor("202601")
    assert result["factor"] == 1.0
    assert result["confidence"] == "unavailable"
    assert result["base_index"] is None and result["target_index"] is None


async def test_escalation_factor_missing_month_unavailable(monkeypatch):
    async def _series():
        return [{"PRD_DE": "202601", "C1_NM": "총지수", "DT": "148.5"}]

    monkeypatch.setattr(idx, "_get_series", _series)
    result = await idx.escalation_factor("202512")  # 시드에 없는 시점
    assert result["factor"] == 1.0
    assert result["confidence"] == "unavailable"


async def test_escalation_factor_computes_ratio(monkeypatch):
    async def _series():
        return [
            {"PRD_DE": "202501", "C1_NM": "총지수", "DT": "140.0"},
            {"PRD_DE": "202607", "C1_NM": "총지수", "DT": "154.0"},
        ]

    monkeypatch.setattr(idx, "_get_series", _series)
    result = await idx.escalation_factor("202501", "202607")
    assert result["confidence"] == "live"
    assert result["base_index"] == 140.0 and result["target_index"] == 154.0
    assert abs(result["factor"] - 1.1) < 1e-9


async def test_escalation_factor_defaults_target_to_latest(monkeypatch):
    async def _series():
        return [
            {"PRD_DE": "202501", "C1_NM": "총지수", "DT": "140.0"},
            {"PRD_DE": "202502", "C1_NM": "총지수", "DT": "141.0"},
            {"PRD_DE": "202607", "C1_NM": "총지수", "DT": "154.0"},
        ]

    monkeypatch.setattr(idx, "_get_series", _series)
    result = await idx.escalation_factor("202501")  # target_ym 미지정 → 최신월(202607)
    assert result["target_ym"] == "202607"
    assert result["confidence"] == "live"


# ── _fetch_series: 키 미설정/비JSON 응답 graceful ──


async def test_fetch_series_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(idx, "_kosis_key", lambda: "")
    assert await idx._fetch_series("202501", "202607") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
