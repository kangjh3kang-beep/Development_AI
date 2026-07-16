"""PublicPriceClient(조달청 가격정보현황서비스) 단위 테스트 — httpx.MockTransport(ecos 패턴)."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.public_price_client import (
    PRICE_OPERATIONS,
    PRICE_SERVICE_BASE,
    PublicPriceClient,
)


def _mock_client_ctor(handler):
    """httpx.AsyncClient 생성을 MockTransport로 가로채는 monkeypatch 헬퍼."""
    orig = httpx.AsyncClient

    def _ctor(**kwargs):
        kwargs.pop("timeout", None)
        return orig(transport=httpx.MockTransport(handler))

    return _ctor


async def test_no_service_key_returns_empty():
    client = PublicPriceClient(service_key="")
    items = await client.fetch_facility_material_prices()
    assert items == []


async def test_fetch_success_parses_items(monkeypatch):
    payload = {
        "response": {
            "body": {
                "items": {"item": [{"prdctClsfcNoNm": "레미콘 25-24-15", "prce": "85000"}]},
                "totalCount": 1,
            }
        }
    }

    def handler(req: httpx.Request) -> httpx.Response:
        assert PRICE_OPERATIONS["토목"] in str(req.url)  # 분야 미지정 → 토목(기존 동작 유지)
        assert "serviceKey=TESTKEY" in str(req.url)
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client_ctor(handler))
    client = PublicPriceClient(service_key="TESTKEY")
    items = await client.fetch_facility_material_prices()
    assert items == [{"prdctClsfcNoNm": "레미콘 25-24-15", "prce": "85000"}]


async def test_fetch_single_item_dict_wrapped_in_list(monkeypatch):
    payload = {"response": {"body": {"items": {"item": {"prdctNm": "철근"}}}}}
    monkeypatch.setattr(
        httpx, "AsyncClient", _mock_client_ctor(lambda req: httpx.Response(200, json=payload))
    )
    client = PublicPriceClient(service_key="K")
    items = await client.fetch_facility_material_prices()
    assert items == [{"prdctNm": "철근"}]


async def test_fetch_empty_items(monkeypatch):
    payload = {"response": {"body": {"items": [], "totalCount": 0}}}
    monkeypatch.setattr(
        httpx, "AsyncClient", _mock_client_ctor(lambda req: httpx.Response(200, json=payload))
    )
    client = PublicPriceClient(service_key="K")
    assert await client.fetch_facility_material_prices() == []


async def test_http_error_graceful(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient",
        _mock_client_ctor(lambda req: httpx.Response(500, text="internal error")),
    )
    client = PublicPriceClient(service_key="K")
    assert await client.fetch_facility_material_prices() == []


async def test_malformed_response_graceful(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient",
        _mock_client_ctor(lambda req: httpx.Response(200, text="not-json")),
    )
    client = PublicPriceClient(service_key="K")
    assert await client.fetch_facility_material_prices() == []


async def test_rate_limiter_exhausted_returns_empty():
    client = PublicPriceClient(service_key="K")
    client._limiter._max = 1
    client._limiter._count = 1  # 이미 한도 도달
    items = await client.fetch_facility_material_prices()
    assert items == []


def test_service_base_url():
    assert PRICE_SERVICE_BASE.endswith("PriceInfoService")


# ── 분야(category) 확장 — 2026-07-17 실키 라이브 검증(resultCode 00) 4개 분야 ──


def test_registered_categories_are_the_four_verified():
    """등록 분야는 라이브 검증된 4개뿐이어야 한다(무날조 — '종합'은 404라 미등록)."""
    assert sorted(PRICE_OPERATIONS) == ["건축", "기계설비", "전기통신", "토목"]
    assert PRICE_OPERATIONS["건축"] == "getPriceInfoListFcltyCmmnMtrilBildng"
    assert "Total" not in "".join(PRICE_OPERATIONS.values())


async def test_fetch_category_routes_to_matching_operation(monkeypatch):
    payload = {"response": {"body": {"items": {"item": [{"prdctClsfcNoNm": "보통합판", "prce": "51954"}]}}}}

    def handler(req: httpx.Request) -> httpx.Response:
        assert PRICE_OPERATIONS["건축"] in str(req.url)
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client_ctor(handler))
    client = PublicPriceClient(service_key="TESTKEY")
    items = await client.fetch_facility_material_prices(category="건축")
    assert items == [{"prdctClsfcNoNm": "보통합판", "prce": "51954"}]


async def test_fetch_unknown_category_raises_value_error():
    client = PublicPriceClient(service_key="TESTKEY")
    with pytest.raises(ValueError, match="미등록 가격정보 분야"):
        await client.fetch_facility_material_prices(category="종합")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
