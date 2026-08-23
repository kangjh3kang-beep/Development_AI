"""★/zoning/parcel-boundaries — 탈락한 필지를 응답이 스스로 말한다(2026-08-23).

배경: `parcel_boundaries()` 는 `asyncio.gather(..., return_exceptions=True)` 결과를
``if not isinstance(r, dict): continue`` 로 걸렀다. 입력 N 개를 넣어 출력 M 개가 나와도
**어디로 갔는지 알 방법이 없었다** — 계수도 사유도 응답에 없었다.

`#772` 가 `build_integrated_context` 에서 봉합한 것과 **같은 침묵의 형제 함수**다
(규율 §6 "고친 자리의 형제·미러를 반드시 스윕한다" 미이행분).

★이 스위트가 잠그는 것 — **두 탈락 경로를 갈라서** 본다. 하나로 뭉뚱그리면 사유 분기를
  지워도 초록이 된다(픽스처가 두 모집단을 갈라야 배선 변이가 죽는다):
    ① `pnu_unresolved` : `_resolve_one` 의 `return None`(지오코딩·점조회 모두 실패)
    ② `lookup_error`   : `return_exceptions=True` 가 담아 온 예외

★무회귀 앵커: `features`·`parcel_count` 의 의미는 **바뀌지 않는다**(계수는 추가만).

hermetic: 외부 I/O 만 대역. 해석 로직·집계는 실물을 태운다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

_OK_PNU = "4146025021100010000"
_ERR_PNU = "4146025021100020000"
_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[127.1, 37.3], [127.1001, 37.3], [127.1001, 37.3001],
                      [127.1, 37.3001], [127.1, 37.3]]],
}


def _stub(monkeypatch):
    """`_OK_PNU` 만 해석되고, `_ERR_PNU` 는 예외, 주소-only 입력은 지오코딩 실패로 만든다."""
    import apps.api.routers.auto_zoning as az
    from apps.api.app.services.external_api.building_registry_service import (
        BuildingRegistryService,
    )
    from apps.api.app.services.external_api.vworld_service import VWorldService
    from apps.api.app.services.land_intelligence.ordinance_service import OrdinanceService

    async def _fake_land_info(self, pnu):  # noqa: ANN001
        if pnu == _ERR_PNU:
            # ② 예외 경로 — ★어디에 주입하느냐가 중요하다. `get_land_characteristics` 에
            #   raise 해도 **_resolve_one 내부의** `gather(..., return_exceptions=True)` 가
            #   삼켜서 탈출하지 못한다(실측: 그렇게 짰더니 3필지 중 2건이 성공으로 나왔다).
            #   실제로 탈출하는 자리는 그 결과를 **쓰는** 쪽이다 —
            #   `float((li_res["properties"]).get("area"))` 는 try 밖이라, 상류가 숫자가 아닌
            #   값을 주면 ValueError 가 그대로 올라간다(VWorld 응답 오염의 현실적 형태).
            return {"geometry": _GEOMETRY, "properties": {"area": "N/A"}}
        return {"geometry": _GEOMETRY, "properties": {"area": 1000.0}}

    async def _fake_land_characteristics(self, pnu):  # noqa: ANN001
        return {
            "area_sqm": 1000.0, "zone_type": "제2종일반주거지역", "zone_type_2": None,
            "official_price_per_sqm": 500_000, "land_category": "대",
            "land_use_situation": None, "terrain_form": None,
        }

    async def _fake_geocode(self, address):  # noqa: ANN001
        return None  # ① PNU 미확보 경로의 1단계 실패

    async def _fake_parcel_by_point(self, lat, lon):  # noqa: ANN001
        return None  # ① 의 2단계(좌표 폴백)도 실패 → `return None`

    async def _fake_title(self, pnu):  # noqa: ANN001
        return None, "no_data"

    async def _fake_districts(self, pnu):  # noqa: ANN001
        return []

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}

    monkeypatch.setattr(VWorldService, "get_land_info", _fake_land_info, raising=True)
    monkeypatch.setattr(
        VWorldService, "get_land_characteristics", _fake_land_characteristics, raising=True,
    )
    monkeypatch.setattr(VWorldService, "geocode_address", _fake_geocode, raising=True)
    monkeypatch.setattr(VWorldService, "get_parcel_by_point", _fake_parcel_by_point, raising=True)
    monkeypatch.setattr(VWorldService, "get_land_use_districts", _fake_districts, raising=True)
    monkeypatch.setattr(
        BuildingRegistryService, "get_title_with_status_by_pnu", _fake_title, raising=True,
    )
    monkeypatch.setattr(OrdinanceService, "get_ordinance_limits", _fake_ordinance, raising=True)
    return az


async def test_dropped_parcels_are_reported_with_split_reasons(monkeypatch):
    """3필지 요청 → 1건만 해석. **두 탈락 사유가 갈려서** 나와야 한다."""
    az = _stub(monkeypatch)

    req = az.ParcelBoundariesRequest(parcels=[
        {"pnu": _OK_PNU},                                   # 성공
        {"address": "경기도 어딘가 없는동 999-999"},          # ① pnu_unresolved
        {"pnu": _ERR_PNU},                                  # ② lookup_error
    ])
    result = await az.parcel_boundaries(req)

    # ── 공허 진리 가드: 성공 1건이 실제로 있어야 "탈락 2건"이 의미를 가진다 ──
    assert len(result["features"]) == 1, "성공 필지가 없으면 이 테스트는 공허하다"

    assert result["requested_count"] == 3
    assert result["resolved_count"] == 1
    dropped = result["dropped"]
    assert len(dropped) == 2, f"탈락 2건이 보고돼야 한다: {dropped}"

    by_reason = {d["reason"]: d for d in dropped}
    # ★두 모집단을 가른다 — 사유를 하나로 뭉뚱그리면 분기를 지워도 이 단언이 통과한다.
    assert set(by_reason) == {"pnu_unresolved", "lookup_error"}, (
        f"두 탈락 경로가 갈려야 한다(하나로 뭉치면 사유 분기가 무잠금): {by_reason}"
    )
    # 사용자가 '어느 필지가' 빠졌는지 알아야 고칠 수 있다.
    assert by_reason["pnu_unresolved"]["address"] == "경기도 어딘가 없는동 999-999"
    assert by_reason["lookup_error"]["pnu"] == _ERR_PNU
    assert by_reason["lookup_error"]["detail"] == "ValueError"


async def test_no_drop_reports_empty_list_not_missing_key(monkeypatch):
    """★정상이면 `dropped` 는 **빈 배열**이다 — 키 부재가 아니다(빈 배열은 '탈락 없음'이라는 양성 정보)."""
    az = _stub(monkeypatch)

    req = az.ParcelBoundariesRequest(parcels=[{"pnu": _OK_PNU}])
    result = await az.parcel_boundaries(req)

    assert result["dropped"] == []
    assert result["requested_count"] == 1
    assert result["resolved_count"] == 1
    # 무회귀 — 기존 계약(features·parcel_count)의 의미는 바뀌지 않는다.
    assert result["parcel_count"] == 1
    assert len(result["features"]) == 1


async def test_counts_track_input_order_not_completion_order(monkeypatch):
    """★탈락 필지 특정은 `zip(items, results)` 에 의존한다 — gather 가 **입력 순서**를 보존해야 성립.

    이 단언이 없으면 "탈락은 셌는데 **엉뚱한 주소**를 지목"하는 형태로 조용히 틀릴 수 있다.
    """
    az = _stub(monkeypatch)

    req = az.ParcelBoundariesRequest(parcels=[
        {"address": "경기도 어딘가 없는동 111-111"},
        {"pnu": _OK_PNU},
        {"address": "경기도 어딘가 없는동 222-222"},
    ])
    result = await az.parcel_boundaries(req)

    assert result["resolved_count"] == 1
    addrs = [d["address"] for d in result["dropped"]]
    # 순서까지 보존돼야 입력 i ↔ 결과 i 의 대응이 성립한다.
    assert addrs == ["경기도 어딘가 없는동 111-111", "경기도 어딘가 없는동 222-222"], (
        f"입력 순서 대응이 깨졌다 — 탈락 주소 지목이 틀어진다: {addrs}"
    )
