"""I2 KOSIS 국내인구이동(OD) 파싱 회귀 테스트 — 정렬·Top3·합계제외·정직 unavailable."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.integrations.kosis_client import KosisClient  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestMigrationOD:
    def test_키없음_정직_unavailable(self):
        r = _run(KosisClient().get_migration_od("11680", "2026"))
        assert r["data_source"] == "unavailable"
        assert r["top_inflow_regions"] == []
        assert r["target_adm_cd"] == "11680"

    def test_파싱_정렬_top3_합계제외(self, monkeypatch):
        k = KosisClient()
        # 키 있는 것으로 강제 + _fetch_migration 모킹(전출지별 전입자수 rows).
        monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "DUMMY", raising=False)
        rows = [
            {"C1_NM": "계", "DT": "99999"},          # 합계 → 제외
            {"C1_NM": "강남구", "DT": "1500"},
            {"C1_NM": "서초구", "DT": "1200"},
            {"C1_NM": "송파구", "DT": "850"},
            {"C1_NM": "분당구", "DT": "300"},          # Top3 밖
            {"C1_NM": "노원구", "DT": "0"},            # 0 → 제외
        ]

        async def fake_fetch(sigungu_cd, year):
            return rows
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)

        r = _run(k.get_migration_od("11680", "2026", use_mock=False))
        names = [x["name"] for x in r["top_inflow_regions"]]
        assert names == ["강남구", "서초구", "송파구"]      # 내림차순 Top3
        assert "계" not in names and "노원구" not in names   # 합계·0 제외
        assert r["total_inflow"] == 1500 + 1200 + 850 + 300  # 합계는 유효 권역 합(계 제외)
        assert r["top_inflow_regions"][0]["ratio"] > 0
        assert r["data_source"] == "fallback"                # 통계표 미확정 → 정직 fallback

    def test_빈응답_정직_unavailable(self, monkeypatch):
        k = KosisClient()
        monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "DUMMY", raising=False)

        async def fake_fetch(sigungu_cd, year):
            return {"errMsg": "non-json-response"}
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_od("11680", "2026", use_mock=False))
        assert r["data_source"] == "unavailable"
