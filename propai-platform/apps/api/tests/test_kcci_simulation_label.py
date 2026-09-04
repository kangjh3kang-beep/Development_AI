"""P1 T5 정직화 — KCCI 시장단가는 결정론 시뮬레이션(실시세 API 아님) 라벨 계약 테스트."""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.services.cost.boq_builder import _kcci_market_source_label
from apps.api.services.kcci_material_price_service import (
    MARKET_PRICE_SOURCE_LABEL,
    KCCIMaterialPriceService,
)


def test_market_price_source_label_is_simulation():
    assert MARKET_PRICE_SOURCE_LABEL == "simulation"


def test_kcci_market_source_label_for_mapped_key():
    assert _kcci_market_source_label("concrete") == "simulation"
    assert _kcci_market_source_label("rebar") == "simulation"
    assert _kcci_market_source_label("window") == "simulation"


def test_kcci_market_source_label_none_for_unmapped_key():
    # formwork/masonry/waterproof는 _KEY_TO_KCCI에 대응 없음 — 라벨도 없어야 정직.
    assert _kcci_market_source_label("formwork") is None
    assert _kcci_market_source_label("masonry") is None


# ── _build_snapshot: 산출 items[]에 source="simulation"이 정직하게 실린다 ──


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """execute() 1회 호출(과거이력 조회)만 응답 — project_id=None이라 원가추정 쿼리는 없음."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _FakeResult(self._rows)


async def test_build_snapshot_items_carry_simulation_source():
    row = SimpleNamespace(
        material_code="ready_mix_concrete", material_name="Ready-mix concrete 25-240-15",
        category="concrete", unit="m3", source_name="kcci-simulated",
        snapshot_at=datetime(2026, 1, 1, tzinfo=UTC),
        unit_price_krw=94500.0, price_index=100.0, mom_change_ratio=0.0, yoy_change_ratio=0.0,
    )
    db = _FakeSession([row])
    service = KCCIMaterialPriceService(db)
    service.settings = SimpleNamespace(kcci_api_key="")

    snapshot = await service._build_snapshot(
        tenant_id=uuid.uuid4(), project_id=None, region_code="KR",
        material_codes=["ready_mix_concrete"],
    )
    assert len(snapshot["items"]) == 1
    assert snapshot["items"][0]["source"] == MARKET_PRICE_SOURCE_LABEL == "simulation"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
