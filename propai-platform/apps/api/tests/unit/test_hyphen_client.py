"""하이픈(Hyphen) 등기부 클라이언트 단위 테스트."""

import pytest

from app.services.registry import hyphen_client


def test_hyphen_ready(monkeypatch):
    monkeypatch.delenv("HYPHEN_HKEY", raising=False)
    monkeypatch.delenv("HYPHEN_USER_ID", raising=False)
    assert hyphen_client.hyphen_ready() is False

    monkeypatch.setenv("HYPHEN_HKEY", "dummy_hkey")
    monkeypatch.setenv("HYPHEN_USER_ID", "dummy_user")
    assert hyphen_client.hyphen_ready() is True


@pytest.mark.asyncio
async def test_search_by_simple_address_not_configured(monkeypatch):
    monkeypatch.delenv("HYPHEN_HKEY", raising=False)
    monkeypatch.delenv("HYPHEN_USER_ID", raising=False)
    res = await hyphen_client.search_by_simple_address("서울시 서초구 서초동 100")
    assert res["status"] == "not_configured"
    assert res["ok"] is False


@pytest.mark.asyncio
async def test_fetch_realty_registry_mock(monkeypatch):
    monkeypatch.setenv("HYPHEN_HKEY", "test_hkey")
    monkeypatch.setenv("HYPHEN_USER_ID", "test_user")

    async def mock_post(*args, **kwargs):
        class MockResp:
            status_code = 200

            def json(self):
                return {
                    "common": {"errYn": "N"},
                    "data": {
                        "pdfHex": "255044462d312e34",  # '%PDF-1.4' in hex
                        "outList": {
                            "get소유자": "홍길동",
                            "get고유번호": "11012023123456",
                        },
                    },
                }

        return MockResp()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    res = await hyphen_client.fetch_realty_registry(unique_no="1101-2023-123456")
    assert res["ok"] is True
    assert res["status"] == "ok"
    assert res["owner"] == "홍길동"
    assert res["has_pdf"] is True
    assert res["pdf_base64"] == "JVBERi0xLjQ="


def test_normalize_address_candidates():
    c1 = hyphen_client.normalize_address_candidates("경상북도 포항시 남구 호미곶면 대보리 산 1-1")
    assert "경상북도 포항시 남구 호미곶면 대보리 산 1-1" in c1
    assert "경상북도 포항시 남구 호미곶면 대보리 산1-1" in c1
    assert "포항시 남구 호미곶면 대보리 산 1-1" in c1
    assert "대보리 산 1-1" in c1
    assert "대보리 산1-1" in c1


@pytest.mark.asyncio
async def test_search_by_simple_address_auto_correction(monkeypatch):
    monkeypatch.setenv("HYPHEN_HKEY", "test_hkey")
    monkeypatch.setenv("HYPHEN_USER_ID", "test_user")

    searched_addrs = []

    async def mock_post(self, url, headers=None, json=None, **kwargs):
        payload = json or {}
        addr = payload.get("simple_address", "")
        searched_addrs.append(addr)

        class MockResp:
            status_code = 200

            def json(self):
                # 1차 "산 1-1"은 빈 결과, 2차 보정 "산1-1"은 결과 반환
                if "산1-1" in addr:
                    return {
                        "common": {"errYn": "N"},
                        "data": {
                            "list": [
                                {
                                    "get부동산고유번호": "16412026000001",
                                    "get구분": "토지",
                                    "get소유자": "김*수",
                                    "get부동산소재지번": "경상북도 포항시 남구 호미곶면 대보리 산1-1",
                                }
                            ]
                        },
                    }
                return {"common": {"errYn": "N"}, "data": {"list": []}}

        return MockResp()

    import httpx
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    res = await hyphen_client.search_by_simple_address("경상북도 포항시 남구 호미곶면 대보리 산 1-1")
    assert res["ok"] is True
    assert len(res["items"]) == 1
    assert res["items"][0]["unique_no"] == "16412026000001"
    assert "경상북도 포항시 남구 호미곶면 대보리 산 1-1" in searched_addrs
    assert "경상북도 포항시 남구 호미곶면 대보리 산1-1" in searched_addrs
