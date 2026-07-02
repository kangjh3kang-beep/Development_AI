"""KOSIS 시군구 인구이동·소득 라이브 파싱 회귀 테스트.

마이그레이션: 「시군구별 이동자수」(DT_1B26001_A01, 단일분류)에서 대상 시군구의
총전입·총전출·순이동을 추출(OD 출발지 분해는 이 표에 없음 → top_inflow_regions=[]).
소득: 국세청 「시군구별 근로소득 연말정산」(DT_133001N_4215)에서 총급여 금액/인원 → 평균연소득.
검색: KOSIS statisticsSearch.do 의 비표준 JSON(따옴표 없는 키) 파싱.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.integrations.kosis_client import KosisClient, _parse_search_records  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _with_key(monkeypatch, k):
    monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "DUMMY", raising=False)
    monkeypatch.setenv("KOSIS_API_KEY", "DUMMY")


class TestMigration:
    def test_키없음_unavailable(self, monkeypatch):
        monkeypatch.delenv("KOSIS_API_KEY", raising=False)
        k = KosisClient()
        monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "", raising=False)
        r = _run(k.get_migration_od("11680", "2025", region_name="강남구"))
        assert r["data_source"] == "unavailable"
        assert r["total_inflow"] == 0 and r["top_inflow_regions"] == []

    def test_시군구명_없으면_unavailable(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return [{"C1_NM": "강남구", "ITM_NM": "총전입", "DT": "80696"}]
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_od("11680", "2025", region_name=None, use_mock=False))
        assert r["data_source"] == "unavailable"

    def test_대상시군구_총전입전출순이동_live(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)
        rows = [
            {"C1_NM": "전국", "ITM_NM": "총전입", "DT": "6117784"},
            {"C1_NM": "강남구", "ITM_NM": "총전입", "DT": "80696", "PRD_DE": "2025"},
            {"C1_NM": "강남구", "ITM_NM": "총전출", "DT": "82424", "PRD_DE": "2025"},
            {"C1_NM": "강남구", "ITM_NM": "순이동", "DT": "-1728", "PRD_DE": "2025"},
            {"C1_NM": "서초구", "ITM_NM": "총전입", "DT": "70000"},
        ]

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return rows
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_od("11680", "2025", region_name="강남구", use_mock=False))
        assert r["data_source"] == "live"
        assert r["total_inflow"] == 80696
        assert r["total_outflow"] == 82424
        assert r["net_migration"] == -1728
        assert r["top_inflow_regions"] == []     # 단일분류 — OD 출발지 없음
        assert r["year"] == "2025"

    def test_행없음_fallback(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return [{"C1_NM": "서초구", "ITM_NM": "총전입", "DT": "70000"}]
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_od("11680", "2025", region_name="강남구", use_mock=False))
        assert r["data_source"] == "fallback"

    def test_빈응답_unavailable(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return {"err": "30", "errMsg": "데이터가 존재하지 않습니다."}
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_od("11680", "2025", region_name="강남구", use_mock=False))
        assert r["data_source"] == "unavailable"


class TestIncome:
    def test_대상시군구_평균소득_live(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)
        # 총급여 금액 20,320,151백만원 / 인원 238,504명 → 8,520만원/인
        rows = [
            {"C1_NM": "강남구", "C2_NM": "과세대상근로소득(총급여)", "ITM_NM": "금액",
             "DT": "20320151", "PRD_DE": "2023"},
            {"C1_NM": "강남구", "C2_NM": "과세대상근로소득(총급여)", "ITM_NM": "인원", "DT": "238504"},
            {"C1_NM": "강남구", "C2_NM": "결정세액", "ITM_NM": "금액", "DT": "3351039"},  # 다른 항목 무시
        ]

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return rows
        monkeypatch.setattr(k, "_fetch_income", fake_fetch)
        r = _run(k.get_macro_income_stats("11680", "2024", region_name="강남구", use_mock=False))
        assert r["data_source"] == "live"
        assert r["avg_income_10k"] == 8520        # 20320151*100/238504 ≈ 8520
        assert r["year"] == "2023"
        assert "note" in r

    def test_이름없음_fallback(self, monkeypatch):
        k = KosisClient()
        _with_key(monkeypatch, k)

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return [{"C1_NM": "강남구", "C2_NM": "과세대상근로소득(총급여)", "ITM_NM": "금액", "DT": "1"}]
        monkeypatch.setattr(k, "_fetch_income", fake_fetch)
        r = _run(k.get_macro_income_stats("11680", "2024", use_mock=False))
        assert r["data_source"] == "fallback"


class TestSearchParse:
    def test_비표준JSON_파싱(self):
        body = ('[{ORG_ID:"101",ORG_NM:"국가데이터처",TBL_ID:"DT_1B26001_A01",'
                'TBL_NM:"시군구별 이동자수",CONTENTS:"행정구역(시군구)별 전입 전출"},'
                '{ORG_ID:"101",TBL_ID:"DT_X",TBL_NM:"기타표"}]')
        recs = _parse_search_records(body, 20)
        assert len(recs) == 2
        assert recs[0]["tbl_id"] == "DT_1B26001_A01"
        assert recs[0]["tbl_nm"] == "시군구별 이동자수"
        assert recs[0]["org_id"] == "101"

    def test_키없음_빈목록(self, monkeypatch):
        monkeypatch.delenv("KOSIS_API_KEY", raising=False)
        k = KosisClient()
        monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "", raising=False)
        assert _run(k.search_tables("인구이동")) == []
