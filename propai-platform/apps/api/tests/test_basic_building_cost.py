"""basic_building_cost — 기본형건축비 baseline 매트릭스(확정구간만) + 개정감지 계약 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.cost import basic_building_cost as bbc

# ── get_baseline: 확정 구간만 값 반환, 그 외는 None(무날조) ──


def test_get_baseline_confirmed_cell():
    result = bbc.get_baseline(20, 70.0)
    assert result["value"] == 2_220_000
    assert result["confidence"] == "verified_press"
    assert result["floor_band"] == "16~25층"
    assert result["prev_value"] == 2_174_000
    assert result["change_pct"] == 2.12


def test_get_baseline_boundary_inclusive():
    # 층수 경계(16·25) 포함, 면적은 하한 초과·상한 이하(60 초과 ~ 85 이하).
    assert bbc.get_baseline(16, 85.0)["value"] == 2_220_000
    assert bbc.get_baseline(25, 61.0)["value"] == 2_220_000


def test_get_baseline_floor_out_of_range_none():
    result = bbc.get_baseline(5, 70.0)
    assert result["value"] is None
    assert result["confidence"] == "unavailable"
    assert "고시 원문 확인 필요" in result["basis"]


def test_get_baseline_area_out_of_range_none():
    result = bbc.get_baseline(20, 40.0)
    assert result["value"] is None
    assert result["confidence"] == "unavailable"


def test_get_baseline_area_exactly_lower_bound_excluded():
    # unit_area_min(60.0)은 초과 조건이라 정확히 60.0은 매칭되지 않음(전용 60㎡초과~85㎡이하).
    result = bbc.get_baseline(20, 60.0)
    assert result["value"] is None


# ── detect_gosi_update: 감지만, 자동 수치 갱신 없음 ──


async def test_detect_gosi_update_unavailable_when_search_fails(monkeypatch):
    class _FakeGosi:
        async def search_admrule(self, query, *, max_results=3):
            return {"available": False, "reason": "MOLEG_API_KEY 미설정(법제처)", "results": []}

    monkeypatch.setattr(
        "app.services.legal.gosi_search_service.GosiSearchService", _FakeGosi
    )
    result = await bbc.detect_gosi_update()
    assert result["checked"] is False
    assert "MOLEG" in result["reason"] or "법제처" in result["reason"]


async def test_detect_gosi_update_no_change_when_dates_match(monkeypatch):
    class _FakeGosi:
        async def search_admrule(self, query, *, max_results=3):
            return {
                "available": True,
                "results": [{"name": "분양가상한제 적용주택의 기본형건축비 및 가산비용",
                             "id": "1", "dept": "국토교통부", "date": "2026-03-01"}],
            }

    record = AsyncMock()
    monkeypatch.setattr(
        "app.services.legal.gosi_search_service.GosiSearchService", _FakeGosi
    )
    monkeypatch.setattr(bbc, "_record_regulation_change", record)
    result = await bbc.detect_gosi_update()
    assert result["checked"] is True
    assert result["changed"] is False
    record.assert_not_called()


async def test_detect_gosi_update_flags_change_and_records(monkeypatch):
    class _FakeGosi:
        async def search_admrule(self, query, *, max_results=3):
            return {
                "available": True,
                "results": [{"name": "분양가상한제 적용주택의 기본형건축비 및 가산비용",
                             "id": "2", "dept": "국토교통부", "date": "2026-09-15"}],
            }

    record = AsyncMock()
    monkeypatch.setattr(
        "app.services.legal.gosi_search_service.GosiSearchService", _FakeGosi
    )
    monkeypatch.setattr(bbc, "_record_regulation_change", record)
    result = await bbc.detect_gosi_update()
    assert result["checked"] is True
    assert result["changed"] is True
    assert result["latest_gosi_date"] == "2026-09-15"
    record.assert_awaited_once()
    # 시드 수치 자체는 자동 변경되지 않는다(감지만).
    assert bbc._BASELINE_MATRIX[0]["above_ground_won_per_sqm"] == 2_220_000


async def test_detect_gosi_update_empty_results():
    class _FakeGosi:
        async def search_admrule(self, query, *, max_results=3):
            return {"available": True, "results": []}

    import app.services.legal.gosi_search_service as gosi_mod
    orig = gosi_mod.GosiSearchService
    gosi_mod.GosiSearchService = _FakeGosi
    try:
        result = await bbc.detect_gosi_update()
        assert result["checked"] is True and result["changed"] is False
    finally:
        gosi_mod.GosiSearchService = orig


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
