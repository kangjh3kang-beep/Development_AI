"""S4 반복 검증 루프 — 필지 면적 3원(공부·좌표·입력) 교차검증 테스트.

계약(계획서 MULTI_PARCEL_ATTRIBUTES_PLAN_2026-07-03 §S4):
  - 신호 3원: 공부(area_sqm 등) / 좌표면적(geometry→dims_from_polygon) / 입력(area_input_sqm).
  - cross_validate(trust.py) 재사용 — anchor=공부.
  - 수렴 정책: 괴리 필지는 refresh_fn 주입 시 1회 재보강 후 재판정.
    자동 보정 금지 — 불수렴은 discrepancy 정직 표기 + 지적측량 권고.
  - 네트워크 직접 호출 금지(전부 주입) — 본 테스트는 순수 dict/콜러블만 사용.
"""
from __future__ import annotations

import math

import pytest

from app.services.land_intelligence.parcel_verification import (
    SIGNAL_CADASTRAL,
    SIGNAL_POLYGON,
    SIGNAL_USER_INPUT,
    collect_area_signals,
    verify_parcel_areas,
)


def _square_geometry(side_m: float = 100.0, lat: float = 37.5, lon: float = 127.0) -> dict:
    """등거리 근사 기준 한 변 side_m 정사각형 폴리곤(GeoJSON) — dims_from_polygon 역산."""
    dlat = side_m / 110540.0
    dlon = side_m / (111320.0 * math.cos(math.radians(lat)))
    return {
        "type": "Polygon",
        "coordinates": [[
            [lon, lat], [lon + dlon, lat], [lon + dlon, lat + dlat],
            [lon, lat + dlat], [lon, lat],
        ]],
    }


# ── 신호 수집 ────────────────────────────────────────────────────────────────

class TestCollectAreaSignals:
    def test_cadastral_and_input_signals(self):
        parcel = {"pnu": "1111", "area_sqm": 1000.0, "area_input_sqm": 995.0}
        signals = collect_area_signals(parcel)
        names = {s.name for s in signals}
        assert SIGNAL_CADASTRAL in names
        assert SIGNAL_USER_INPUT in names
        cad = next(s for s in signals if s.name == SIGNAL_CADASTRAL)
        assert cad.value == 1000.0

    def test_polygon_signal_from_geometry(self):
        pytest.importorskip("shapely")
        parcel = {"pnu": "1111", "area_sqm": 10000.0, "geometry": _square_geometry(100.0)}
        signals = collect_area_signals(parcel)
        poly = next((s for s in signals if s.name == SIGNAL_POLYGON), None)
        assert poly is not None
        # 등거리 근사 — 100m×100m ≈ 10,000㎡(±1%)
        assert abs(poly.value - 10000.0) / 10000.0 < 0.01

    def test_no_signals_for_empty_parcel(self):
        assert collect_area_signals({}) == []

    def test_nonpositive_values_ignored(self):
        signals = collect_area_signals({"area_sqm": 0, "area_input_sqm": -5})
        assert signals == []


# ── 정합(consistent) ─────────────────────────────────────────────────────────

class TestConsistent:
    def test_three_signals_agree(self):
        pytest.importorskip("shapely")
        parcel = {
            "pnu": "1111", "area_sqm": 10000.0,
            "geometry": _square_geometry(100.0), "area_input_sqm": 10050.0,
        }
        out = verify_parcel_areas([parcel])
        assert out["parcel_count"] == 1
        entry = out["per_parcel"][0]
        assert entry["status"] == "consistent"
        assert entry["pnu"] == "1111"
        assert entry["confidence"] > 0
        assert entry["consensus_ratio"] is not None
        assert entry["consensus_ratio"] <= 1.10
        # 설명가능성 — 근거·한계 동반
        assert entry["rationale"]
        assert entry["limitations"]
        assert out["all_consistent"] is True

    def test_two_signals_agree(self):
        parcel = {"pnu": "2222", "area_sqm": 500.0, "area_input_sqm": 505.0}
        out = verify_parcel_areas([parcel])
        assert out["per_parcel"][0]["status"] == "consistent"


# ── 괴리(discrepancy) ────────────────────────────────────────────────────────

class TestDiscrepancy:
    def test_one_outlier_signal(self):
        # 입력값이 공부 대비 30% 괴리 — 이상치
        parcel = {"pnu": "3333", "area_sqm": 1000.0, "area_input_sqm": 1300.0}
        out = verify_parcel_areas([parcel])
        entry = out["per_parcel"][0]
        assert entry["status"] == "discrepancy"
        assert "지적측량" in entry["recommendation"]
        assert entry["refresh_attempted"] is False  # refresh_fn 미주입
        assert out["discrepancy_count"] == 1
        assert out["all_consistent"] is False

    def test_no_auto_correction(self):
        """자동 보정 금지 — 입력 parcel dict는 절대 변형하지 않는다(무날조)."""
        parcel = {"pnu": "3333", "area_sqm": 1000.0, "area_input_sqm": 1300.0}
        snapshot = dict(parcel)
        verify_parcel_areas([parcel])
        assert parcel == snapshot


# ── 재보강 수렴 정책 ─────────────────────────────────────────────────────────

class TestRefreshPolicy:
    def test_refresh_converges(self):
        """재보강으로 입력 괴리가 해소되면 consistent + 수렴 표기."""
        parcel = {"pnu": "4444", "area_sqm": 1000.0, "area_input_sqm": 1300.0}
        calls: list[dict] = []

        def refresh_fn(p: dict) -> dict:
            calls.append(p)
            return {"area_input_sqm": 1005.0}  # 재보강된 정정값

        out = verify_parcel_areas([parcel], refresh_fn=refresh_fn)
        entry = out["per_parcel"][0]
        assert entry["status"] == "consistent"
        assert entry["refresh_attempted"] is True
        assert entry["converged_after_refresh"] is True
        assert len(calls) == 1  # 1회만 재보강

    def test_refresh_not_converged_stays_discrepancy(self):
        """불수렴 — 자동 보정 없이 discrepancy 정직 표기 + 지적측량 권고."""
        parcel = {"pnu": "5555", "area_sqm": 1000.0, "area_input_sqm": 1300.0}

        def refresh_fn(p: dict) -> dict:
            return {"area_input_sqm": 1300.0}  # 여전히 괴리

        out = verify_parcel_areas([parcel], refresh_fn=refresh_fn)
        entry = out["per_parcel"][0]
        assert entry["status"] == "discrepancy"
        assert entry["refresh_attempted"] is True
        assert entry["converged_after_refresh"] is False
        assert "지적측량" in entry["recommendation"]

    def test_refresh_only_called_for_discrepant_parcels(self):
        good = {"pnu": "6666", "area_sqm": 1000.0, "area_input_sqm": 1001.0}
        bad = {"pnu": "7777", "area_sqm": 1000.0, "area_input_sqm": 1500.0}
        called_pnus: list = []

        def refresh_fn(p: dict) -> dict:
            called_pnus.append(p.get("pnu"))
            return {}

        out = verify_parcel_areas([good, bad], refresh_fn=refresh_fn)
        assert called_pnus == ["7777"]
        assert out["per_parcel"][0]["status"] == "consistent"
        assert out["per_parcel"][1]["status"] == "discrepancy"

    def test_refresh_fn_exception_is_honest(self):
        """재보강 실패(예외)는 삼키되 discrepancy 유지 + 사유 기록."""
        parcel = {"pnu": "8888", "area_sqm": 1000.0, "area_input_sqm": 1300.0}

        def refresh_fn(p: dict) -> dict:
            raise RuntimeError("upstream down")

        out = verify_parcel_areas([parcel], refresh_fn=refresh_fn)
        entry = out["per_parcel"][0]
        assert entry["status"] == "discrepancy"
        assert entry["refresh_attempted"] is True
        assert entry["converged_after_refresh"] is False


# ── 신호 부족(insufficient) ──────────────────────────────────────────────────

class TestInsufficient:
    def test_single_signal(self):
        parcel = {"pnu": "9999", "area_sqm": 1000.0}
        out = verify_parcel_areas([parcel])
        entry = out["per_parcel"][0]
        assert entry["status"] == "insufficient"
        assert out["insufficient_count"] == 1
        assert out["all_consistent"] is False

    def test_zero_signal(self):
        out = verify_parcel_areas([{"pnu": "0000"}])
        assert out["per_parcel"][0]["status"] == "insufficient"

    def test_empty_parcels(self):
        out = verify_parcel_areas([])
        assert out["parcel_count"] == 0
        assert out["per_parcel"] == []
