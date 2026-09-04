"""★/zoning/parcel-boundaries — **우세 용도지역**을 계산해 놓고 안 보내던 것을 보낸다(2026-08-24).

`_aggregate_integrated_zoning` 은 이미 `dominant_zone` 을 **면적합산 max** 로 산출하고,
동률(±5%)이나 규제성격 상이면 `"mixed_review_required"` 로 **임의 단일화를 거부**한다.
그런데 이 엔드포인트의 `integrated_analysis` 블록이 그 값을 응답에 싣지 않았다 —
**계산해 놓고 안 보내는** 형태(`_far_legal` 과 같은 계열).

그 결과 프론트는 `first.zoneType` 을 "dominant" 라 부르고 있었고, 실측 사례에서 그 값은
**면적 우세와 반대**였다(자연녹지 4,576㎡·79% vs 보전관리 1,205㎡·21% 인데 보전관리 표시).

★픽스처는 **면적 우세와 첫 필지가 어긋나게** 만든다 — 같으면 이 테스트는 잠금이 아니다.
★그리고 **두 모집단을 가른다**: 같은 규제성격(녹지 안) 혼재는 면적으로 우세를 뽑고,
  성격이 다른 혼재(관리+녹지)는 **판정을 보류**한다. 하나만 테스트하면 그 분기가 무잠금이다.

★실측 정정: 사용자 신고 케이스(보전관리+자연녹지)의 정답은 "자연녹지"가 **아니라 판정 보류**다.
  두 지역은 규제성격이 달라 서버가 임의 단일화를 거부한다 — 내가 처음 쓴 기대값이 틀렸고
  코드가 맞았다(RED 로 적발). 프론트의 `first.zoneType` 은 **고르지 말아야 할 때 골랐던** 것이다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

_GEOM = {"type": "Polygon", "coordinates": [[[127.1, 37.3], [127.1001, 37.3],
                                             [127.1001, 37.3001], [127.1, 37.3001], [127.1, 37.3]]]}
# ① 같은 성격(녹지) 안의 혼재 — 첫 필지가 작고 둘째가 크다 → **우세는 둘째**.
_G_SMALL, _G_LARGE = "4113510300101000000", "4113510300102000000"
# ② 성격이 다른 혼재(관리+녹지) — 사용자 신고 케이스 그대로 → **판정 보류**.
_M_SMALL, _M_LARGE = "4315031022200070001", "4315011400101230001"
_AREA = {_G_SMALL: 326.0, _G_LARGE: 4576.0, _M_SMALL: 326.0, _M_LARGE: 4576.0}
_ZONE = {_G_SMALL: "생산녹지지역", _G_LARGE: "자연녹지지역",
         _M_SMALL: "보전관리지역", _M_LARGE: "자연녹지지역"}


def _stub(monkeypatch):
    import apps.api.routers.auto_zoning as az
    from apps.api.app.services.external_api.building_registry_service import BuildingRegistryService
    from apps.api.app.services.external_api.vworld_service import VWorldService
    from apps.api.app.services.land_intelligence.ordinance_service import OrdinanceService

    async def _li(self, pnu):  # noqa: ANN001
        return {"geometry": _GEOM, "properties": {"area": _AREA[pnu]}}

    async def _lc(self, pnu):  # noqa: ANN001
        return {"area_sqm": _AREA[pnu], "zone_type": _ZONE[pnu], "zone_type_2": None,
                "official_price_per_sqm": 2410, "land_category": "임야",
                "land_use_situation": None, "terrain_form": None}

    async def _title(self, pnu):  # noqa: ANN001
        return None, "no_data"

    async def _d(self, pnu):  # noqa: ANN001
        return []

    async def _ord(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}

    monkeypatch.setattr(VWorldService, "get_land_info", _li, raising=True)
    monkeypatch.setattr(VWorldService, "get_land_characteristics", _lc, raising=True)
    monkeypatch.setattr(VWorldService, "get_land_use_districts", _d, raising=True)
    monkeypatch.setattr(BuildingRegistryService, "get_title_with_status_by_pnu", _title, raising=True)
    monkeypatch.setattr(OrdinanceService, "get_ordinance_limits", _ord, raising=True)
    return az


async def test_dominant_zone_is_area_weighted_not_first_parcel(monkeypatch):
    """① 같은 성격(녹지) 혼재 — 첫 필지(생산녹지 326㎡) ≠ 면적 우세(자연녹지 4,576㎡)."""
    az = _stub(monkeypatch)
    result = await az.parcel_boundaries(
        az.ParcelBoundariesRequest(parcels=[{"pnu": _G_SMALL}, {"pnu": _G_LARGE}]),
    )
    ia = result["integrated_analysis"]

    # ── 공허 진리 가드: 두 필지가 실제로 해석돼야 "우세"가 의미를 가진다 ──
    assert ia is not None and ia["parcel_count"] == 2
    assert ia["zone_mixed"] is True, "혼재가 아니면 우세 판정이 무의미하다"

    # ★핵심 — 첫 필지가 아니라 **면적 우세**여야 한다.
    assert ia["dominant_zone"] == "자연녹지지역", (
        f"면적 우세(자연녹지 4,576㎡)가 아니라 첫 필지(보전관리 326㎡)를 골랐다: {ia['dominant_zone']}"
    )
    assert ia["dominant_zone"] != _ZONE[_G_SMALL], "첫 필지 값을 그대로 쓰면 회귀"
    assert ia["dominant_basis"] == "area_weighted"

    # 근거(면적 비중)도 함께 온다 — 화면이 "면적 79%" 를 말할 재료.
    mix = {m["zone"]: m for m in (ia.get("zone_mix") or [])}
    assert set(mix) == {"생산녹지지역", "자연녹지지역"}
    assert mix["자연녹지지역"]["share_pct"] > mix["생산녹지지역"]["share_pct"]


async def test_cross_family_mix_refuses_to_pick(monkeypatch):
    """★② 사용자 신고 케이스 — 관리+녹지는 성격이 달라 **임의 단일화를 거부**한다.

    ★이 케이스가 없으면 "면적 max 로 뽑는다" 분기만 잠기고, **보류 분기**가 무잠금이 된다.
    그리고 이것이 실제 사용자 데이터의 정답이다 — 화면은 한 지역을 고르면 **안 된다**.
    """
    az = _stub(monkeypatch)
    result = await az.parcel_boundaries(
        az.ParcelBoundariesRequest(parcels=[{"pnu": _M_SMALL}, {"pnu": _M_LARGE}]),
    )
    ia = result["integrated_analysis"]
    assert ia["zone_mixed"] is True
    assert ia["dominant_zone"] == "mixed_review_required", (
        f"규제성격이 다른 혼재는 보류해야 한다(임의 단일화 금지): {ia['dominant_zone']}"
    )
    # ★면적이 큰 쪽을 고르지 **않았음**도 함께 단언 — 보류가 '큰 쪽 선택'으로 퇴화하면 잡는다.
    assert ia["dominant_zone"] != "자연녹지지역"


async def test_single_zone_has_no_ambiguity(monkeypatch):
    """★무회귀 — 단일 용도지역이면 우세는 그 값이고 혼재 아님."""
    az = _stub(monkeypatch)
    result = await az.parcel_boundaries(
        az.ParcelBoundariesRequest(parcels=[{"pnu": _M_SMALL}]),
    )
    ia = result["integrated_analysis"]
    assert ia["zone_mixed"] is False
    assert ia["dominant_zone"] == "보전관리지역"
