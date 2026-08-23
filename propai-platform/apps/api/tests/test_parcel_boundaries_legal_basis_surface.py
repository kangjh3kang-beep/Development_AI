"""★/zoning/parcel-boundaries — 실효 한도의 **법정값·근거 계층**을 공개 필드로 낸다(2026-08-23).

배경(사용자 신고): 보전관리지역 필지 팝오버에 `실효 용적률 60.0%` 만 떴다. 사용자는 값이
틀렸다고 신고했는데 **값은 정확했다** — 법정 80% 를 제천시 도시계획조례가 60% 로 깎은 값이다
(라이브 실측 `far_basis="조례 적용값(지자체 도시계획조례 적용값(법제처API))"`).

**없던 것은 값이 아니라 근거다.** 종전에는 `_far_legal`·`_far_basis` 가 내부 키(`_` 접두)라
응답 직전에 스트립돼 화면이 "왜 60% 인지"를 말할 재료 자체가 없었다.

★이 스위트가 잠그는 것:
  · 법정값·근거가 **공개 필드로 나온다**(`legal_far_pct`·`legal_bcr_pct`·`far_basis`)
  · **값은 바뀌지 않는다** — 실효값 자체는 종전과 동일(근거만 추가)
  · 내부 키 스트립 규약(`_` 접두)은 **깨지지 않는다**(승격은 스트립 전에 일어나야 한다)

hermetic: 외부 I/O 만 대역. `calc_effective_far` 등 산출은 실물을 태운다.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

_PNU = "4146025021100010000"
_GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[127.1, 37.3], [127.1001, 37.3], [127.1001, 37.3001],
                      [127.1, 37.3001], [127.1, 37.3]]],
}


def _stub(monkeypatch, zone: str):
    import apps.api.routers.auto_zoning as az
    from apps.api.app.services.external_api.building_registry_service import (
        BuildingRegistryService,
    )
    from apps.api.app.services.external_api.vworld_service import VWorldService
    from apps.api.app.services.land_intelligence.ordinance_service import OrdinanceService

    async def _fake_land_info(self, pnu):  # noqa: ANN001
        return {"geometry": _GEOMETRY, "properties": {"area": 1000.0}}

    async def _fake_lc(self, pnu):  # noqa: ANN001
        return {
            "area_sqm": 1000.0, "zone_type": zone, "zone_type_2": None,
            "official_price_per_sqm": 500_000, "land_category": "대",
            "land_use_situation": None, "terrain_form": None,
        }

    async def _fake_title(self, pnu):  # noqa: ANN001
        return None, "no_data"

    async def _fake_districts(self, pnu):  # noqa: ANN001
        return []

    async def _fake_ordinance(self, address, zone_type, force_refresh=False):  # noqa: ANN001
        return {}

    monkeypatch.setattr(VWorldService, "get_land_info", _fake_land_info, raising=True)
    monkeypatch.setattr(VWorldService, "get_land_characteristics", _fake_lc, raising=True)
    monkeypatch.setattr(VWorldService, "get_land_use_districts", _fake_districts, raising=True)
    monkeypatch.setattr(
        BuildingRegistryService, "get_title_with_status_by_pnu", _fake_title, raising=True,
    )
    monkeypatch.setattr(OrdinanceService, "get_ordinance_limits", _fake_ordinance, raising=True)
    return az


async def test_legal_limit_and_basis_are_public_fields(monkeypatch):
    """자연녹지 — 실효 80%(구조상한)인데 **법정은 100%**. 그 차이와 근거가 화면에 갈 수 있어야 한다."""
    az = _stub(monkeypatch, "자연녹지지역")

    result = await az.parcel_boundaries(az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}]))
    feat = result["features"][0]

    # ── 공허 진리 가드: 실효값이 실제로 산출됐어야 "근거"가 의미를 가진다 ──
    assert feat["effective_far_pct"] == 80.0, "실효값 자체가 없으면 이 테스트는 공허하다"

    # ★두 모집단이 갈린다: 법정(100) ≠ 실효(80). 같은 값이면 이 단언은 잠금이 아니다.
    assert feat["legal_far_pct"] == 100, f"법정 용적률이 공개돼야 한다: {feat.get('legal_far_pct')}"
    assert feat["legal_far_pct"] != feat["effective_far_pct"], (
        "법정과 실효가 같으면 '근거 병기'가 무의미하다 — 픽스처가 두 값을 갈라야 한다"
    )
    assert feat["legal_bcr_pct"] == 20
    # 어느 계층이 물렸는지 — 사용자가 "왜 80%인가"에 답할 수 있어야 한다.
    assert isinstance(feat.get("far_basis"), str) and feat["far_basis"], (
        f"근거 계층 문자열이 있어야 한다: {feat.get('far_basis')!r}"
    )

    # ★내부 키 스트립 규약 무회귀 — 승격은 스트립 **전에** 일어나야 하고, 내부 키는 안 새야 한다.
    assert not any(k.startswith("_") for k in feat), (
        f"밑줄 접두 내부키 누출: {sorted(k for k in feat if k.startswith('_'))}"
    )


async def test_effective_values_unchanged_by_the_promotion(monkeypatch):
    """★무회귀 — 근거를 붙였을 뿐 **값은 그대로**다(2종일반: 실효=법정=250)."""
    az = _stub(monkeypatch, "제2종일반주거지역")

    result = await az.parcel_boundaries(az.ParcelBoundariesRequest(parcels=[{"pnu": _PNU}]))
    feat = result["features"][0]

    assert feat["effective_far_pct"] == 250.0
    assert feat["legal_far_pct"] == 250
    # 실효==법정이면 화면은 병기하지 않는다(같은 수를 두 번 보여 주지 않는다) — 그 판정의 재료.
    assert feat["legal_far_pct"] == feat["effective_far_pct"]
