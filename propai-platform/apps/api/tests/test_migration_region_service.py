"""권역 인구이동망 지도(순이동 발산 코로플레스) 회귀 테스트.

검증 대상:
  1) KosisClient.get_migration_region_map — 전국 시군구 순이동 '단일 조회' 파싱
     (코드/이름 인덱스, 동일명 중복 제외, 순이동 보정, 무키 unavailable).
  2) MigrationRegionService.build_migration_region — SGIS 시군구 경계 + KOSIS 순이동 조립
     (무키 즉시 unavailable·외부콜 0, UTM-K→WGS84 재투영, 코드/이름 조인, 대상 강조, 범례).
  3) 라우터 등록 스모크(/api/v1/market/migration-region).

★dev(무키) 환경이라 라이브 코로플레스는 unavailable 경로만 실검증 가능 — 그 정직 폴백을 필수 검증.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.app.services.market.migration_region_service import (  # noqa: E402
    MigrationRegionService,
    _is_target,
)
from apps.api.integrations.kosis_client import KosisClient  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _with_key(monkeypatch, k):
    monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "DUMMY", raising=False)
    monkeypatch.setenv("KOSIS_API_KEY", "DUMMY")


class _IdentityTf:
    """항등 변환기(입력 x,y 그대로 반환). pyproj 미설치 dev에서 재투영 '배선'만 검증.

    (실좌표 UTM-K→WGS84 값 검증은 pyproj 필요 → 라이브 환경 몫. 여기선 좌표가 tf.transform 을
    거쳐 features 로 흐르는 파이프라인·조인·범례를 검증한다.)
    """
    @staticmethod
    def transform(x, y):
        return x, y


def _square(lon: float, lat: float, d: float = 0.01) -> dict:
    """(lon,lat) 주변 작은 사각형 GeoJSON Polygon. 항등 변환기와 함께 좌표 흐름 검증용."""
    ring = [
        [lon - d, lat - d], [lon + d, lat - d],
        [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _patch_identity_tf(monkeypatch):
    """서비스가 쓰는 공용 변환기 헬퍼를 항등 변환기로 대체(pyproj 비의존)."""
    import apps.api.app.services.market.migration_region_service as mod
    monkeypatch.setattr(mod, "build_utmk_to_wgs84_transformer", lambda: _IdentityTf())


# ────────────────────────── 1) KOSIS 단일 조회 파싱 ──────────────────────────
class TestRegionMap:
    def test_키없음_unavailable(self, monkeypatch):
        monkeypatch.delenv("KOSIS_API_KEY", raising=False)
        k = KosisClient()
        monkeypatch.setattr(k.api_settings, "KOSIS_API_KEY", "", raising=False)
        r = _run(k.get_migration_region_map("2025"))
        assert r["data_source"] == "unavailable"
        assert r["by_code"] == {} and r["by_name"] == {}

    def test_조립_by_code_by_name_live(self, monkeypatch):
        k = KosisClient(); _with_key(monkeypatch, k)
        rows = [
            {"C1": "11", "C1_NM": "전국", "ITM_NM": "총전입", "DT": "6117784"},  # 합계행 제외
            {"C1": "11230", "C1_NM": "강남구", "ITM_NM": "총전입", "DT": "80696", "PRD_DE": "2025"},
            {"C1": "11230", "C1_NM": "강남구", "ITM_NM": "총전출", "DT": "82424", "PRD_DE": "2025"},
            {"C1": "11230", "C1_NM": "강남구", "ITM_NM": "순이동", "DT": "-1728", "PRD_DE": "2025"},
            {"C1": "11215", "C1_NM": "서초구", "ITM_NM": "총전입", "DT": "70000", "PRD_DE": "2025"},
            {"C1": "11215", "C1_NM": "서초구", "ITM_NM": "총전출", "DT": "65000", "PRD_DE": "2025"},
            # 순이동 항목이 없으면 전입-전출로 보정(70000-65000=5000).
        ]

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return rows
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_region_map("2025"))
        assert r["data_source"] == "live"
        assert r["year"] == "2025"
        # 코드 인덱스
        assert r["by_code"]["11230"]["net_migration"] == -1728
        assert r["by_code"]["11215"]["net_migration"] == 5000  # 전입-전출 보정
        # 이름 인덱스(유일명)
        assert r["by_name"]["강남구"]["total_inflow"] == 80696
        # 합계행(전국)은 제외
        assert "전국" not in r["by_name"]

    def test_동일명중복_by_name제외_by_code유지(self, monkeypatch):
        """여러 시도의 '중구'는 이름만으로 구분 불가 → by_name 제외, by_code 는 유지."""
        k = KosisClient(); _with_key(monkeypatch, k)
        rows = [
            {"C1": "11140", "C1_NM": "중구", "ITM_NM": "순이동", "DT": "-500", "PRD_DE": "2025"},
            {"C1": "11140", "C1_NM": "중구", "ITM_NM": "총전입", "DT": "10000"},
            {"C1": "26110", "C1_NM": "중구", "ITM_NM": "순이동", "DT": "300", "PRD_DE": "2025"},
            {"C1": "26110", "C1_NM": "중구", "ITM_NM": "총전입", "DT": "8000"},
        ]

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return rows
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_region_map("2025"))
        assert r["data_source"] == "live"
        assert "중구" not in r["by_name"]          # 중복명 → 이름 조인 후보 제외
        assert r["by_code"]["11140"]["net_migration"] == -500  # 코드로는 구분 가능
        assert r["by_code"]["26110"]["net_migration"] == 300

    def test_수치없음_fallback(self, monkeypatch):
        k = KosisClient(); _with_key(monkeypatch, k)

        async def fake_fetch(sigungu_cd, year, tbl_id=None):
            return [{"C1": "11230", "C1_NM": "강남구", "ITM_NM": "총전입", "DT": "0"}]
        monkeypatch.setattr(k, "_fetch_migration", fake_fetch)
        r = _run(k.get_migration_region_map("2025"))
        assert r["data_source"] == "fallback"


# ────────────────────────── 2) 서비스 조립 ──────────────────────────
class TestService:
    def test_무키_즉시_unavailable_외부콜0(self, monkeypatch):
        """KOSIS 무키면 SGIS 토큰조차 받지 않고(외부콜 0) 즉시 unavailable 반환(정직)."""
        monkeypatch.delenv("KOSIS_API_KEY", raising=False)
        svc = MigrationRegionService()
        monkeypatch.setattr(svc._kosis.api_settings, "KOSIS_API_KEY", "", raising=False)

        called = {"sgis": False}

        async def fake_token():
            called["sgis"] = True
            return "TOKEN"
        monkeypatch.setattr(svc._sgis, "get_access_token", fake_token)

        r = _run(svc.build_migration_region(bcode="1168010100", region_name="강남구"))
        assert r["data_source"] == "unavailable"
        assert r["features"] == []
        assert called["sgis"] is False   # KOSIS 무키 → SGIS 외부호출 안 함

    def test_KOSIS_미live_unavailable(self, monkeypatch):
        svc = MigrationRegionService()
        _with_key(monkeypatch, svc._kosis)

        async def fake_token():
            return "TOKEN"
        monkeypatch.setattr(svc._sgis, "get_access_token", fake_token)

        async def fake_boundaries(token, sido):
            return [{"properties": {"adm_cd": "11230", "adm_nm": "강남구"},
                     "geometry": _square(127.05, 37.5)}]
        monkeypatch.setattr(svc, "_fetch_sigungu_boundaries", fake_boundaries)

        async def fake_mig(year, use_mock=None):
            return {"data_source": "fallback", "by_code": {}, "by_name": {}, "note": "수치 없음"}
        monkeypatch.setattr(svc._kosis, "get_migration_region_map", fake_mig)

        r = _run(svc.build_migration_region(bcode="1168010100", region_name="강남구"))
        assert r["data_source"] in ("fallback", "unavailable")
        assert r["features"] == []

    def test_조립_live_재투영_조인_강조_범례(self, monkeypatch):
        svc = MigrationRegionService()
        _with_key(monkeypatch, svc._kosis)
        _patch_identity_tf(monkeypatch)   # pyproj 비의존(항등 변환기)

        async def fake_token():
            return "TOKEN"
        monkeypatch.setattr(svc._sgis, "get_access_token", fake_token)

        # 시군구 3개: 강남구(코드조인·대상) / 서초구(이름조인) / 송파구(무자료→None).
        async def fake_boundaries(token, sido):
            assert sido == "11"   # 법정동 11 → KOSTAT 11(서울)
            return [
                {"properties": {"adm_cd": "11230", "adm_nm": "강남구"},
                 "geometry": _square(127.05, 37.50)},
                {"properties": {"adm_cd": "11215", "adm_nm": "서초구"},
                 "geometry": _square(127.02, 37.48)},
                {"properties": {"adm_cd": "11240", "adm_nm": "송파구"},
                 "geometry": _square(127.11, 37.51)},
            ]
        monkeypatch.setattr(svc, "_fetch_sigungu_boundaries", fake_boundaries)

        async def fake_mig(year, use_mock=None):
            return {
                "data_source": "live", "year": "2025",
                "by_code": {"11230": {"c1_code": "11230", "name": "강남구",
                                      "total_inflow": 80696, "total_outflow": 82424,
                                      "net_migration": -1728}},
                "by_name": {"서초구": {"c1_code": "11215", "name": "서초구",
                                     "total_inflow": 70000, "total_outflow": 65000,
                                     "net_migration": 5000}},
            }
        monkeypatch.setattr(svc._kosis, "get_migration_region_map", fake_mig)

        r = _run(svc.build_migration_region(bcode="1168010100", region_name="강남구", year="2025"))
        assert r["data_source"] == "live"
        assert r["sido"] == "11"
        assert r["count"] == 3
        assert r["matched"] == 2          # 강남구(코드)+서초구(이름) 조인, 송파구 무자료
        feats = {f["name"]: f for f in r["features"]}

        # 코드 조인(강남구) + 대상 강조
        assert feats["강남구"]["net_migration"] == -1728
        assert feats["강남구"]["is_target"] is True
        # 이름 조인(서초구)
        assert feats["서초구"]["net_migration"] == 5000
        assert feats["서초구"]["is_target"] is False
        # 무자료(송파구)=None(회색·가짜값 없음)
        assert feats["송파구"]["net_migration"] is None

        # 재투영: UTM-K→WGS84 왕복 → 강남구 첫 좌표가 원 WGS84(≈127.04,37.49)로 복원
        first = feats["강남구"]["geometry"]["coordinates"][0][0]
        assert 126.9 < first[0] < 127.2 and 37.4 < first[1] < 37.6

        # 발산 범례: min/max/max_abs (순유출 -1728, 순유입 +5000 → max_abs=5000)
        assert r["legend"]["min_net"] == -1728
        assert r["legend"]["max_net"] == 5000
        assert r["legend"]["max_abs"] == 5000
        assert r["target_found"] is True

    def test_경계무자료_unavailable(self, monkeypatch):
        svc = MigrationRegionService()
        _with_key(monkeypatch, svc._kosis)

        async def fake_token():
            return "TOKEN"
        monkeypatch.setattr(svc._sgis, "get_access_token", fake_token)

        async def fake_boundaries(token, sido):
            return []
        monkeypatch.setattr(svc, "_fetch_sigungu_boundaries", fake_boundaries)

        async def fake_mig(year, use_mock=None):
            return {"data_source": "live", "year": "2025", "by_code": {}, "by_name": {}}
        monkeypatch.setattr(svc._kosis, "get_migration_region_map", fake_mig)

        r = _run(svc.build_migration_region(bcode="1168010100", region_name="강남구"))
        assert r["data_source"] == "unavailable"
        assert r["features"] == []


class TestTargetMatch:
    def test_정확일치_및_통합시_endswith(self):
        assert _is_target("강남구", "강남구") is True
        assert _is_target("장안구", "수원시 장안구") is True   # SGIS 짧은명 vs 주소 긴명
        assert _is_target("강남구", "서초구") is False
        assert _is_target("강남구", None) is False


# ────────────────────────── 3) 라우터 등록 스모크 ──────────────────────────
class TestRouterSmoke:
    def test_엔드포인트_등록됨(self):
        from apps.api.routers.market_report import router
        paths = {getattr(r, "path", "") for r in router.routes}
        assert "/api/v1/market/migration-region" in paths
