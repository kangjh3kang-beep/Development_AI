"""N2 BIM 물량 우선 병합(boq_bim_merge.merge_bim) 단위 테스트 — 결정론·정직성.

검증 범위(§3 N2 명세):
- 우선순위 user > bim > parametric. BIM 1:1 매칭 항목은 qty 를 실측치로 교체하고
  qty_source='bim'(원 파라메트릭 수량은 qty_parametric 로 보존).
- 단위 불일치는 변환하지 않고 경고(정직) — qty 유지·qty_source='parametric'.
- 모호(한 work_code 가 다수 draft 항목과 매칭) 시 자동 배분하지 않음(허위 분배 금지).
- BIM 0건/미매칭 코드 → parametric 그대로 + 안내(가짜값 금지).
- additive·비파괴: 입력 draft/아이템 불변, qty_source 등 신규 키만 가산.

work_code→공종명 매핑은 ifc_work_map.IFC_WORK_MAP 역참조(A04='방수공사' 등).
"""
from __future__ import annotations

import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.cost.boq_bim_merge import merge_bim  # noqa: E402


def _draft(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "disciplines": {"건축": {"items": items, "item_count": len(items), "sections": []}},
        "summary": {"total_items": len(items), "params_used": {}, "warnings": []},
        "provenance": {"name": "의정부동 424 주상복합", "sample_count": 1},
        "badges": {"note": "실적 1건 기반 — 전문 적산 검토 필수", "confidence": "낮음(n=1)"},
    }


def _item(name: str, unit: str, qty: float, *, spec: str = "", **extra: Any) -> dict[str, Any]:
    base = {
        "id": extra.get("id", "건축-0001"), "discipline": "건축",
        "section_code": "0104", "section_name": "방수공사",
        "name": name, "spec": spec, "unit": unit, "qty": qty,
        "qty_sample": qty, "driver": "gfa", "basis": "표본 비례", "confidence": "낮음(n=1)",
    }
    if "qty_source" in extra:
        base["qty_source"] = extra["qty_source"]
    return base


def _bim(work_code: str, unit: str, quantity: float, line_count: int = 1) -> dict[str, Any]:
    return {"work_code": work_code, "unit": unit, "quantity": quantity, "line_count": line_count}


def _items_out(out: dict[str, Any]) -> list[dict[str, Any]]:
    return out["disciplines"]["건축"]["items"]


class TestBimReplace:
    def test_1대1_매칭_실측치_교체(self):
        d = _draft([_item("우레탄 방수", "m2", 100.0)])
        out = merge_bim(d, [_bim("A04", "m2", 250.0)])
        it = _items_out(out)[0]
        assert it["qty"] == 250.0
        assert it["qty_source"] == "bim"
        assert it["qty_parametric"] == 100.0  # 원 파라메트릭 수량 보존(정직)
        assert it["bim_work_code"] == "A04"
        assert out["summary"]["bim_merge"]["bim_matched_count"] == 1

    def test_단위_불일치_변환안함_경고(self):
        d = _draft([_item("방수 처리", "식", 5.0)])
        out = merge_bim(d, [_bim("A04", "m2", 250.0)])
        it = _items_out(out)[0]
        assert it["qty"] == 5.0  # 교체 안 함
        assert it["qty_source"] == "parametric"
        mm = out["summary"]["bim_merge"]["unit_mismatch"]
        assert mm and mm[0]["work_code"] == "A04"
        assert any("단위" in w for w in out["summary"]["bim_merge"]["warnings"])

    def test_모호매칭_자동배분안함(self):
        # 두 항목이 같은 work_code(A01-03=콘크리트)에 매칭 → 허위 분배 금지
        d = _draft([
            _item("레미콘 기초", "m3", 10.0, id="건축-1"),
            _item("레미콘 벽체", "m3", 20.0, id="건축-2"),
        ])
        out = merge_bim(d, [_bim("A01-03", "m3", 500.0)])
        for it in _items_out(out):
            assert it["qty_source"] == "parametric"  # 둘 다 교체 안 함
        amb = out["summary"]["bim_merge"]["ambiguous"]
        assert amb and amb[0]["work_code"] == "A01-03" and amb[0]["match_count"] == 2

    def test_user_우선_보존(self):
        d = _draft([_item("우레탄 방수", "m2", 100.0, qty_source="user")])
        out = merge_bim(d, [_bim("A04", "m2", 250.0)])
        it = _items_out(out)[0]
        assert it["qty"] == 100.0  # user 입력 보존(bim 이 덮지 않음)
        assert it["qty_source"] == "user"


class TestBimEdgeCases:
    def test_bim_0건_전부_parametric(self):
        d = _draft([_item("우레탄 방수", "m2", 100.0)])
        out = merge_bim(d, [])
        it = _items_out(out)[0]
        assert it["qty"] == 100.0
        assert it["qty_source"] == "parametric"
        bm = out["summary"]["bim_merge"]
        assert bm["bim_rows_count"] == 0
        assert bm["bim_matched_count"] == 0

    def test_미매칭_bim_코드_안내(self):
        d = _draft([_item("우레탄 방수", "m2", 100.0)])
        # A03=조적공사 → 방수 항목과 매칭 안 됨
        out = merge_bim(d, [_bim("A03", "m2", 30.0)])
        bm = out["summary"]["bim_merge"]
        assert "A03" in bm["unmatched_bim_codes"]
        assert _items_out(out)[0]["qty_source"] == "parametric"

    def test_by_source_집계(self):
        d = _draft([
            _item("우레탄 방수", "m2", 100.0, id="건축-1"),          # → bim
            _item("가설국기게양시설", "식", 1.0, id="건축-2"),        # parametric
            _item("창호 유리", "m2", 50.0, id="건축-3", qty_source="user"),  # user 보존
        ])
        out = merge_bim(d, [_bim("A04", "m2", 250.0)])
        by = out["summary"]["bim_merge"]["by_source"]
        assert by["bim"] == 1
        assert by["user"] == 1
        assert by["parametric"] == 1

    def test_additive_비파괴_입력불변(self):
        src = _item("우레탄 방수", "m2", 100.0)
        d = _draft([src])
        merge_bim(d, [_bim("A04", "m2", 250.0)])
        # 입력 항목 불변
        assert src["qty"] == 100.0
        assert "qty_source" not in src
        # 기존 배지/출처 보존은 출력에서 확인
        out = merge_bim(d, [_bim("A04", "m2", 250.0)])
        assert out["badges"]["confidence"] == "낮음(n=1)"
        assert out["provenance"]["sample_count"] == 1


class TestTierDistributionW33:
    """W3-3(P9) — merge_bim 이 부착하는 Q1~Q4 등급(사실 재-표기, qty_source 기반)."""

    def test_항목별_tier_부착(self):
        d = _draft([_item("우레탄 방수", "m2", 100.0)])
        out = merge_bim(d, [_bim("A04", "m2", 250.0)])
        it = _items_out(out)[0]
        assert it["tier"] == "Q1_MEASURED"  # qty_source='bim'으로 교체된 항목

    def test_bim_merge_summary에_tier_distribution(self):
        d = _draft([
            _item("우레탄 방수", "m2", 100.0),                     # bim 매칭 → Q1
            _item("가설국기게양시설", "식", 1.0, id="건축-2"),      # parametric → Q2
            _item("창호 유리", "m2", 50.0, id="건축-3", qty_source="user"),  # user → Q1
        ])
        out = merge_bim(d, [_bim("A04", "m2", 250.0)])
        td = out["summary"]["bim_merge"]["tier_distribution"]
        by_tier = td["by_tier"]
        assert by_tier["Q1_MEASURED"]["count"] == 2  # bim 1건 + user 1건
        assert by_tier["Q2_PARAMETRIC"]["count"] == 1
        assert td["dominant_tier"] == "Q1_MEASURED"
