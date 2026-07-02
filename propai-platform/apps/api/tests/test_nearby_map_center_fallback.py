"""주변 실거래 지도 center 폴백 · 지오코딩 캐시 TTL 단위 테스트.

검증 범위(★외부 실호출 없음 — 지오코딩·MOLIT을 모두 스텁으로 대체):
  1) center_hint 폴백: 서비스 자체 주소 지오코딩이 실패(None)해도, 라우터가 넘긴
     center_hint 좌표로 center가 채워진다(백엔드 지오코딩 실패 시 서울 폴백 제거의 핵심).
  2) center_hint 없이 지오코딩 실패 → center={lat:None,lon:None}(가짜 좌표 날조 금지).
  3) 지오코딩 캐시 TTL: 성공은 7일(_GEOCODE_CACHE_TTL_OK), 실패/미해결(빈 좌표)은
     5분(_GEOCODE_CACHE_TTL_MISS)만 캐시 — 일시 실패가 7일 고착되지 않음.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.app.services.land_intelligence import nearby_map_service as nm


class _StubMolit:
    """MOLIT 클라이언트 스텁 — 실호출 없이 빈 거래를 반환."""

    async def get_transactions(self, *_a, **_k):
        return []

    async def get_rent_transactions(self, *_a, **_k):
        return []


def _make_service_geocode_fail() -> "nm.NearbyMapService":
    """지오코딩·MOLIT을 모두 무력화한 서비스(주소 지오코딩 항상 실패)."""
    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc.molit = _StubMolit()
    svc._geo_key = ""  # 키 없음 → _geocode_one 은 None 반환

    async def _empty_geocode_many(_queries):
        return {}

    svc._geocode_many = _empty_geocode_many  # type: ignore[assignment]
    return svc


@pytest.mark.asyncio
async def test_center_hint_fills_center_when_geocode_fails():
    """자체 지오코딩 실패 + center_hint 존재 → center가 힌트 좌표로 채워진다."""
    nm._BUILD_CACHE.clear()
    svc = _make_service_geocode_fail()
    hint = {"lat": 37.3219, "lon": 127.0955}  # 용인 수지 근방
    result = await svc.build(
        address="용인시 수지구 신봉동 56-1",
        lawd_cd="41465",
        months=1,
        radius_m=1000,
        center_hint=hint,
    )
    assert result["center"] is not None
    assert result["center"]["lat"] == pytest.approx(37.3219)
    assert result["center"]["lon"] == pytest.approx(127.0955)
    # ★서울시청(37.5665) 로 폴백되지 않는다.
    assert result["center"]["lat"] != pytest.approx(37.5665, abs=1e-3)


@pytest.mark.asyncio
async def test_no_hint_no_geocode_yields_null_center_not_fabricated():
    """center_hint 없이 지오코딩도 실패 → center 좌표는 None(가짜 날조 금지)."""
    nm._BUILD_CACHE.clear()
    svc = _make_service_geocode_fail()
    result = await svc.build(
        address="어딘가 주소",
        lawd_cd="41465",
        months=1,
        radius_m=1000,
        center_hint=None,
    )
    assert result["center"] == {"lat": None, "lon": None, "address": "어딘가 주소"}


@pytest.mark.asyncio
async def test_geocode_cache_ttl_success_is_long_failure_is_short():
    """지오코딩 캐시: 성공=7일, 실패(빈 좌표)=5분. 일시 실패 장기 고착 방지."""
    captured: list[tuple[str, int]] = []

    class _FakeRedis:
        async def get(self, _key):
            return None  # 캐시 미스 → 실제 지오코딩 경로 진입

        async def setex(self, key, ttl, _val):
            captured.append((key, ttl))

        async def aclose(self):
            return None

    svc = nm.NearbyMapService.__new__(nm.NearbyMapService)
    svc.settings = None
    svc._geo_key = "dummy-key"  # 키 있음 → 실제 HTTP 시도(성공/실패는 _do_geo로 강제)

    async def _fake_redis():
        return _FakeRedis()

    svc._redis = _fake_redis  # type: ignore[assignment]

    # 성공 좌표를 돌려주는 지오코딩 경로 강제(HTTP 대신) — _geocode_one 내부 로직을 우회하지 않고
    #   실제 setex TTL 선택을 검증하기 위해 얇은 래퍼로 성공/실패를 주입한다.
    import httpx

    class _FakeResp:
        status_code = 200

        def __init__(self, ok: bool):
            self._ok = ok

        def json(self):
            if self._ok:
                return {"response": {"status": "OK", "result": {"point": {"x": 127.1, "y": 37.3}}}}
            return {"response": {"status": "NOT_FOUND"}}

    class _FakeClient:
        def __init__(self, ok: bool):
            self._ok = ok

        async def get(self, *_a, **_k):
            return _FakeResp(self._ok)

        async def aclose(self):
            return None

    # 성공 케이스 → TTL 7일
    await svc._geocode_one("성공주소", client=_FakeClient(True))  # type: ignore[arg-type]
    # 실패 케이스 → TTL 5분
    await svc._geocode_one("실패주소", client=_FakeClient(False))  # type: ignore[arg-type]

    ttls = {key.split(":")[-1]: ttl for key, ttl in captured}
    assert ttls["성공주소"] == nm._GEOCODE_CACHE_TTL_OK == 604800
    assert ttls["실패주소"] == nm._GEOCODE_CACHE_TTL_MISS == 300
    # 실패가 7일로 고착되지 않는다.
    assert ttls["실패주소"] < ttls["성공주소"]
    _ = httpx  # noqa: F841 (import 유지 — 향후 실 client 교체 대비)
