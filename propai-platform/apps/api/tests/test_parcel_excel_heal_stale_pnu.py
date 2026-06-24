"""엑셀 bad-data 자가치유 검증 — 잘못된 법정동코드로 만든 PNU 라 용도지역을 못 불러온 행이
주소로 재지오코딩되어 올바른 PNU·용도지역을 회복하는지(또는 정직하게 failed 가 되는지) 확인.

근본문제: 엑셀에 적힌 bcode 가 실제 주소와 어긋나면 그 코드로 만든 PNU 가 '존재하지 않는 필지'를
가리켜 NED 조회가 빈값 → 용도지역/건폐율/용적률이 영구히 안 불러와짐. need_geocode 에도 안 들어가
재시도조차 없던 것을 _heal_stale_pnu 로 해소.
"""
import asyncio

import pytest

from app.services.land_intelligence import parcel_excel_service as pes

# 올바른/틀린 PNU (서울 동작구 상도동 가정). 둘 다 19자리.
CORRECT_PNU = "1159010300102100453"  # 주소 지오코딩이 돌려주는 진짜 PNU
WRONG_PNU = "4115010300102100453"   # 엑셀에 어긋난 bcode(4115=의정부)로 만들어진 가짜 PNU


class _FakeVWorld:
    """get_land_characteristics: 올바른 PNU 에만 zone 데이터. 틀린 PNU 는 빈값(존재하지 않는 필지).
    geocode_address: 주소로 올바른 PNU 회복.
    """

    async def get_land_characteristics(self, pnu):
        if pnu == CORRECT_PNU:
            return {
                "zone_type": "제2종일반주거지역",
                "land_category": "대",
                "official_price_per_sqm": 3_000_000,
                "area_sqm": 200.0,
            }
        return None  # 틀린 PNU → NED 빈값(용도지역 미로드)

    async def geocode_address(self, query):
        # 주소(시군구+번지 포함)면 올바른 PNU 회복.
        if "상도동" in query and any(c.isdigit() for c in query):
            return {"lat": 37.5, "lon": 126.9, "pnu": CORRECT_PNU}
        return None

    async def search_address(self, query, size=8):
        return []


@pytest.fixture(autouse=True)
def _patch_vworld(monkeypatch):
    import app.services.external_api.vworld_service as vmod
    monkeypatch.setattr(vmod, "VWorldService", _FakeVWorld)


def test_heal_recovers_zone_from_address_when_bcode_wrong():
    """틀린 bcode→가짜 PNU(status ok·zone None) 행이 주소 재해소로 올바른 PNU·용도지역 회복."""
    svc = pes.ParcelExcelService()
    items = [{
        "__rid": "r1",
        "address": "서울특별시 동작구 상도동 210-453",
        "jibun": "210-453",
        "bcode": "4115010300",  # ★어긋난 법정동코드(의정부) — 엑셀 오기 시뮬
        "pnu": WRONG_PNU,        # 그 코드로 만들어진 가짜 PNU
    }]
    out = asyncio.run(svc.enrich_parcel_list(items, with_building=False))
    p = out[0]
    assert p["pnu"] == CORRECT_PNU, "주소로 올바른 PNU 를 회복해야 함"
    assert p["zone_type"] == "제2종일반주거지역", "회복된 PNU 로 용도지역이 채워져야 함"
    assert p["status"] == "ok"


def test_heal_marks_failed_when_address_also_unresolvable():
    """주소로도 PNU 를 못 잡으면 silent 'ok' 가 아니라 정직하게 failed."""
    svc = pes.ParcelExcelService()
    items = [{
        "__rid": "r2",
        "address": "알 수 없는 동",  # 번지 없음 → 지오코딩 실패
        "jibun": "",
        "bcode": "4115010300",
        "pnu": WRONG_PNU,
    }]
    out = asyncio.run(svc.enrich_parcel_list(items, with_building=False))
    p = out[0]
    assert p["zone_type"] is None
    assert p["status"] == "failed", "치유 실패 행은 ok 가 아니라 failed 여야 함(silent bad data 차단)"
    assert p.get("reason")


def test_good_row_untouched():
    """올바른 PNU 행은 자가치유가 건드리지 않고 정상 보강(회귀 방지)."""
    svc = pes.ParcelExcelService()
    items = [{
        "__rid": "r3",
        "address": "서울특별시 동작구 상도동 210-453",
        "jibun": "210-453",
        "bcode": "1159010300",
        "pnu": CORRECT_PNU,
    }]
    out = asyncio.run(svc.enrich_parcel_list(items, with_building=False))
    p = out[0]
    assert p["pnu"] == CORRECT_PNU
    assert p["zone_type"] == "제2종일반주거지역"
    assert p["status"] == "ok"
    assert not p.get("_stale_pnu_retried"), "정상 행은 재시도 마킹이 없어야 함"
