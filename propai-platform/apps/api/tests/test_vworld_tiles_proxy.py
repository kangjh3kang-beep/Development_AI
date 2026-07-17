"""VWorld 타일 프록시(WS-B2) 계약 테스트 — web 프록시(vworld-wms-proxy.test.ts)와 동일 시나리오 고정.

httpx.MockTransport로 상류(VWorld)를 대역 처리(ecos/public_price 테스트 관례).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import vworld_tiles as mod
from app.routers.vworld_tiles import (
    classify_vworld_xml,
    extract_vworld_code,
    router,
)

PNG_MAGIC = b"\x89PNG"

# 2026-07-17 라이브 채증 원문(INVALID_RANGE — WMS VERSION 1.1.1 거부) — code 표면화 회귀 고정.
LIVE_INVALID_RANGE_XML = (
    '<?xml version="1.0" encoding="UTF-8" ?>\n'
    '<ServiceExceptionReport version="1.3.0" xmlns="http://www.opengis.net/ogc">\n'
    '<ServiceException code="INVALID_RANGE">VERSION 파라미터의 값이 유효한 범위를 넘었습니다.'
    " 유효한 파라미터 값의 범위 : [1.3.0], 입력한 파라미터 값 : 1.1.1</ServiceException>\n"
    "</ServiceExceptionReport>"
)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _mock_async_client(monkeypatch, handler):
    """모듈이 여는 httpx.AsyncClient를 MockTransport로 가로챈다(요청 URL 캡처용)."""
    captured: list[httpx.Request] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return handler(req)

    orig = httpx.AsyncClient

    def _ctor(**kwargs):
        kwargs.pop("timeout", None)
        return orig(transport=httpx.MockTransport(_handler))

    monkeypatch.setattr(mod.httpx, "AsyncClient", _ctor)
    return captured


def _png_response(_req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=PNG_MAGIC + b"tile", headers={"content-type": "image/png"})


WMS_QUERY = (
    "service=WMS&request=GetMap&layers=LP_PA_CBND_BUDB,LP_PA_CBND_BONB"
    "&styles=LP_PA_CBND_BUDB,LP_PA_CBND_BONB&format=image/png&transparent=true"
    "&version=1.3.0&width=256&height=256&crs=EPSG:3857&bbox=14135029,4518899,14137474,4521344"
)


# ── 순수 분류/추출 — web vworld-xml-exception 계약 동기 ──


def test_classify_coverage_and_auth():
    assert classify_vworld_xml("<Report>FileNotFound: 서비스 제공영역이 아닙니다</Report>") == "coverage"
    assert classify_vworld_xml(LIVE_INVALID_RANGE_XML) == "auth"
    assert classify_vworld_xml("") == "auth"


def test_extract_code_boundary_guard():
    assert extract_vworld_code(LIVE_INVALID_RANGE_XML) == "INVALID_RANGE"
    # ★<ServiceExceptionReport> 접두 오탐 방지(web 정규식 함정과 동일 경계) — code 없으면 None.
    assert extract_vworld_code("<ServiceExceptionReport>no code</ServiceExceptionReport>") is None


# ── WMS ──


def test_wms_no_key_returns_503(monkeypatch):
    monkeypatch.delenv("VWORLD_API_KEY", raising=False)
    monkeypatch.setattr(mod, "_vworld_key", lambda: "")
    client = TestClient(_app())
    resp = client.get(f"/api/v1/tiles/vworld/wms?{WMS_QUERY}")
    assert resp.status_code == 503
    assert "not configured" in resp.json()["error"]


def test_wms_injects_key_domain_and_canonical_layers(monkeypatch):
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    captured = _mock_async_client(monkeypatch, _png_response)
    client = TestClient(_app())
    resp = client.get(f"/api/v1/tiles/vworld/wms?{WMS_QUERY}")
    assert resp.status_code == 200
    assert resp.content.startswith(PNG_MAGIC)
    url = str(captured[0].url)
    assert url.startswith("https://api.vworld.kr/req/wms?")
    assert "key=SECRET-KEY" in url and "domain=www.4t8t.net" in url
    # canonical LAYERS 정확히 1개(원본 재전달 금지)
    assert url.count("LAYERS=") == 1
    assert captured[0].headers["referer"] == "https://www.4t8t.net"


def test_wms_rejects_unlisted_and_smuggled_layers(monkeypatch):
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    captured = _mock_async_client(monkeypatch, _png_response)
    client = TestClient(_app())
    assert client.get("/api/v1/tiles/vworld/wms?layers=LT_C_UQ111").status_code == 400
    # 중복 키 스머글링(허용+차단 혼합)도 400 — 상류 요청 자체가 없어야 한다.
    assert (
        client.get("/api/v1/tiles/vworld/wms?LAYERS=LP_PA_CBND_BUDB&LAYERS=LT_C_UQ111").status_code
        == 400
    )
    assert client.get("/api/v1/tiles/vworld/wms?layers=").status_code == 400
    assert captured == []


def test_wms_xml_coverage_returns_transparent_png(monkeypatch):
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    _mock_async_client(
        monkeypatch,
        lambda _req: httpx.Response(
            200,
            text="<Report>FileNotFound: 서비스 제공영역이 아닙니다</Report>",
            headers={"content-type": "text/xml;charset=UTF-8"},
        ),
    )
    client = TestClient(_app())
    resp = client.get(f"/api/v1/tiles/vworld/wms?{WMS_QUERY}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content.startswith(b"\x89PNG")


def test_wms_xml_auth_surfaces_code_503(monkeypatch):
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    _mock_async_client(
        monkeypatch,
        lambda _req: httpx.Response(
            200, text=LIVE_INVALID_RANGE_XML, headers={"content-type": "application/xml"}
        ),
    )
    client = TestClient(_app())
    resp = client.get(f"/api/v1/tiles/vworld/wms?{WMS_QUERY}")
    assert resp.status_code == 503
    assert "INVALID_RANGE" in resp.json()["error"]


def test_wms_upstream_4xx_becomes_503(monkeypatch):
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    _mock_async_client(monkeypatch, lambda _req: httpx.Response(403, text="nope"))
    client = TestClient(_app())
    resp = client.get(f"/api/v1/tiles/vworld/wms?{WMS_QUERY}")
    assert resp.status_code == 503
    assert "upstream" in resp.json()["error"]


# ── WMTS ──


def test_wmts_satellite_uses_jpeg_and_key_in_path(monkeypatch):
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    captured = _mock_async_client(monkeypatch, _png_response)
    client = TestClient(_app())
    resp = client.get("/api/v1/tiles/vworld/wmts/Satellite/6/24/54.png")
    assert resp.status_code == 200
    url = str(captured[0].url)
    assert url == "https://api.vworld.kr/req/wmts/1.0.0/SECRET-KEY/Satellite/6/24/54.jpeg"


def test_wmts_unknown_layer_falls_back_to_base_and_bad_coord_400(monkeypatch):
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    captured = _mock_async_client(monkeypatch, _png_response)
    client = TestClient(_app())
    assert client.get("/api/v1/tiles/vworld/wmts/EvilLayer/6/24/54.png").status_code == 200
    assert "/Base/6/24/54.png" in str(captured[0].url)
    # 비숫자 x좌표(경로 주입류)는 400 — 상류 URL 조립 전에 거부.
    assert client.get("/api/v1/tiles/vworld/wmts/Base/6/24/abc.png").status_code == 400
    assert len(captured) == 1  # 400 케이스는 상류 요청 자체가 없다


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
