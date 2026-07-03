"""[MAP-007 P1] /zoning/parcel-at-point 응답 보강 회귀 테스트.

결함: parcel_at_point가 vworld.get_land_characteristics()로 공시지가를 이미 받아오면서도
응답 dict에 official_price_per_sqm·built_year·building_age_years를 누락 →
지도 클릭으로 채워진 필지는 공시지가/노후도 레이어 색상이 항상 비어(null) 렌더 불가.
(프론트 ParcelAtPointResult 계약은 세 필드를 기대 — SatongMultiMap.tsx:44-65)

comprehensive 엔드포인트(routers/auto_zoning.py:755-766)와 동일 규칙:
- official_price_per_sqm: 토지특성 응답 재사용(추가 호출 0), 0/누락은 None(가짜값 금지)
- built_year/building_age_years: 건축물대장 표제부 use_approval_date 기반, 무자료는 None
외부 API는 전부 monkeypatch — 네트워크 없이 결정론 검증.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.app.services.external_api.building_registry_service import (  # noqa: E402
    BuildingRegistryService,
)
from apps.api.app.services.external_api.vworld_service import VWorldService  # noqa: E402
from apps.api.routers.auto_zoning import ParcelAtPointRequest, parcel_at_point  # noqa: E402

_PNU = "1168010100101230045"
_GEOMETRY = {"type": "Polygon", "coordinates": [[[127.0, 37.5], [127.001, 37.5], [127.001, 37.501], [127.0, 37.5]]]}


def _patch_point(monkeypatch, *, price=12_000_000, use_approval_date="19950630"):
    async def fake_point(self, lat, lon):
        return {"pnu": _PNU, "address": "서울특별시 강남구 역삼동 123-45", "geometry": _GEOMETRY}

    async def fake_lc(self, pnu):
        assert pnu == _PNU
        return {
            "area_sqm": 330.0,
            "zone_type": "제2종일반주거지역",
            "land_category": "대",
            "official_price_per_sqm": price,
        }

    async def fake_title(self, pnu):
        assert pnu == _PNU
        if use_approval_date is None:
            return None
        return {"use_approval_date": use_approval_date, "building_name": "테스트빌딩", "main_purpose": "업무시설"}

    monkeypatch.setattr(VWorldService, "get_parcel_by_point", fake_point)
    monkeypatch.setattr(VWorldService, "get_land_characteristics", fake_lc)
    monkeypatch.setattr(BuildingRegistryService, "get_title_by_pnu", fake_title)


async def test_공시지가_노후도_필드가_응답에_포함된다(monkeypatch):
    _patch_point(monkeypatch)
    res = await parcel_at_point(ParcelAtPointRequest(lat=37.5, lon=127.0))
    assert res["found"] is True
    assert res["pnu"] == _PNU
    # 공시지가 — 토지특성 재사용(무날조: 실제 patched 값 그대로)
    assert res["official_price_per_sqm"] == 12_000_000
    # 노후도 — 사용승인일 1995 → built_year=1995, age=현재연도-1995
    assert res["built_year"] == 1995
    assert res["building_age_years"] == datetime.now().year - 1995


async def test_공시지가_0이면_None_가짜값_금지(monkeypatch):
    _patch_point(monkeypatch, price=0, use_approval_date=None)
    res = await parcel_at_point(ParcelAtPointRequest(lat=37.5, lon=127.0))
    assert res["found"] is True
    assert res["official_price_per_sqm"] is None
    # 건축물대장 무자료 → 노후도 None(나대지 등 — 가짜 생성 금지)
    assert res["built_year"] is None
    assert res["building_age_years"] is None


async def test_건축물대장_조회실패해도_기존_필드는_보존(monkeypatch):
    _patch_point(monkeypatch)

    async def boom(self, pnu):
        raise RuntimeError("MOLIT down")

    monkeypatch.setattr(BuildingRegistryService, "get_title_by_pnu", boom)
    res = await parcel_at_point(ParcelAtPointRequest(lat=37.5, lon=127.0))
    # 기존 계약(무회귀): found/pnu/면적/용도/지목/건폐·용적/geometry 유지
    assert res["found"] is True
    assert res["area_sqm"] == 330.0
    assert res["zone_type"] == "제2종일반주거지역"
    assert res["jimok"] == "대"
    assert res["bcr_pct"] == 60 and res["far_pct"] == 250
    assert res["geometry"] == _GEOMETRY
    # 실패는 정직 None(응답 자체는 성공)
    assert res["built_year"] is None
    assert res["building_age_years"] is None
