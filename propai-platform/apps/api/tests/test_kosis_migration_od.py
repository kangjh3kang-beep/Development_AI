"""I2 KOSIS 국내인구이동(OD) 파싱 회귀 테스트 — 정렬·Top3·합계제외·전입필터·live승격·정직 unavailable."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.integrations.kosis_client import KosisClient  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _with_key(monkeypatch, k):
    monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "DUMMY", raising=False)


def _patch_search(monkeypatch, k, result):
    async def fake_search(keyword, max_items=20):
        return result
    monkeypatch.setattr(k, "search_tables", fake_search)


class TestMigrationOD:
    def test_키없음_정직_unavailable(self):
        r = _run(KosisClient().get_migration_od("11680", "2026"))
        assert r["data_source"] == "unavailable"
        assert r["top_inflow_regions"] == []
        assert r["target_adm_cd"] == "11680"

    def test_파싱_정렬_top3_합계제외_미확정fallback(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)
        _patch_search(monkeypatch, k, [])  # 통합검색 매칭 없음 → resolved=False → fallback
        rows = [
            {"C1_NM": "계", "DT": "99999"},          # 합계 → 제외
            {"C1_NM": "강남구", "DT": "1500"},
            {"C1_NM": "서초구", "DT": "1200"},
            {"C1_NM": "송파구", "DT": "850"},
            {"C1_NM": "분당구", "DT": "300"},          # Top3 밖
            {"C1_NM": "노원구", "DT": "0"},            # 0 → 제외
        ]

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return rows
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)

        r = _run(k.get_migration_od("11680", "2026", use_mock=False))
        names = [x["name"] for x in r["top_inflow_regions"]]
        assert names == ["강남구", "서초구", "송파구"]      # 내림차순 Top3
        assert "계" not in names and "노원구" not in names   # 합계·0 제외
        assert r["total_inflow"] == 1500 + 1200 + 850 + 300  # 유효 권역 합(계 제외)
        assert r["top_inflow_regions"][0]["ratio"] > 0
        assert r["data_source"] == "fallback"                # 통계표 미확정 → 정직 fallback

    def test_전입항목_필터_및_live승격(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)
        # 통합검색이 '인구이동' 표 확정 → resolved=True → live
        _patch_search(monkeypatch, k, [
            {"tbl_id": "DT_1B26001_A01", "tbl_nm": "국내인구이동통계 시군구별 전입", "org_id": "101"},
        ])
        rows = [
            {"C1_NM": "강남구", "ITM_NM": "전입자수", "DT": "1500"},
            {"C1_NM": "서초구", "ITM_NM": "전입자수", "DT": "1200"},
            {"C1_NM": "강남구", "ITM_NM": "전출자수", "DT": "9999"},  # 전출 → 제외
            {"C1_NM": "강남구", "ITM_NM": "순이동자수", "DT": "8888"},  # 순이동 → 제외
        ]

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            assert tbl_id == "DT_1B26001_A01"  # 확정된 표ID 전달 확인
            return rows
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)

        r = _run(k.get_migration_od("11680", "2026", use_mock=False))
        names = [x["name"] for x in r["top_inflow_regions"]]
        assert names == ["강남구", "서초구"]          # 전입 항목만 집계
        assert r["total_inflow"] == 1500 + 1200       # 전출/순이동 제외
        assert r["data_source"] == "live"             # 실표 확정 → live 승격

    def test_빈응답_정직_unavailable(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)
        _patch_search(monkeypatch, k, [])

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return {"errMsg": "non-json-response"}
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_od("11680", "2026", use_mock=False))
        assert r["data_source"] == "unavailable"


class TestSearchTables:
    def test_키없음_빈목록(self):
        assert _run(KosisClient().search_tables("인구이동")) == []

    def test_빈키워드_빈목록(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)
        assert _run(k.search_tables("")) == []
