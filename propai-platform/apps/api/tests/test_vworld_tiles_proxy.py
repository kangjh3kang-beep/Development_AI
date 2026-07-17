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
    SUPPORTED_WMTS_LAYERS,
    classify_vworld_xml,
    extract_vworld_code,
    extract_vworld_locator,
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
    # slowapi @limiter.limit 데코레이터는 app.state.limiter를 요구한다(미들웨어 불요 —
    # 테스트 상한 1200/min은 시나리오 요청 수로는 미도달).
    from apps.api.rate_limit import limiter

    app.state.limiter = limiter
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
    "service=WMS&request=GetMap&layers=lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun"
    "&styles=lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun&format=image/png&transparent=true"
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
    assert client.get("/api/v1/tiles/vworld/wms?layers=LT_C_EVIL_LAYER").status_code == 400
    # 중복 키 스머글링(허용+차단 혼합)도 400 — 상류 요청 자체가 없어야 한다.
    assert (
        client.get("/api/v1/tiles/vworld/wms?LAYERS=lp_pa_cbnd_bubun&LAYERS=LT_C_EVIL_LAYER").status_code
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


def test_wms_allows_zoning_layer_lt_c_uq111(monkeypatch):
    """★web 화이트리스트와 동기 계약(R1 #1): lt_c_uq111(용도지역·전국 지적편집도) 허용 —
    api측에서 실수로 제거되면 web 키부재 폴백 경로만 용도지역을 거부하는 발산이 생긴다."""
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    captured = _mock_async_client(monkeypatch, _png_response)
    client = TestClient(_app())
    resp = client.get("/api/v1/tiles/vworld/wms?service=WMS&request=GetMap&layers=lt_c_uq111&version=1.3.0&crs=EPSG:3857&bbox=1,2,3,4&width=64&height=64")
    assert resp.status_code == 200
    assert "LAYERS=lt_c_uq111" in str(captured[0].url)


def test_wms_line_style_variant_kept_and_arbitrary_forced_canonical(monkeypatch):
    """★V1(web과 동기): STYLES가 '각 canonical 레이어+_line' 집합이면 선 스타일 유지,
    임의 스타일은 canonical 강제(스머글링 불변)."""
    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    captured = _mock_async_client(monkeypatch, _png_response)
    client = TestClient(_app())
    resp = client.get(
        "/api/v1/tiles/vworld/wms?layers=lp_pa_cbnd_bubun,lp_pa_cbnd_bonbun"
        "&styles=lp_pa_cbnd_bubun_line,lp_pa_cbnd_bonbun_line&version=1.3.0"
        "&crs=EPSG:3857&bbox=1,2,3,4&width=64&height=64"
    )
    assert resp.status_code == 200
    url = str(captured[0].url)
    assert "STYLES=lp_pa_cbnd_bubun_line%2Clp_pa_cbnd_bonbun_line" in url or "STYLES=lp_pa_cbnd_bubun_line,lp_pa_cbnd_bonbun_line" in url
    client.get("/api/v1/tiles/vworld/wms?layers=lp_pa_cbnd_bubun&styles=EVIL&version=1.3.0&crs=EPSG:3857&bbox=1,2,3,4&width=64&height=64")
    assert "STYLES=lp_pa_cbnd_bubun" in str(captured[1].url).replace("%2C", ",")


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


# ── OWS 1.1 ExceptionReport (WMTS 계열) — web lib/vworld-xml-exception.ts와 동기 ──
# ★2026-07-17 라이브 채증 원문. WMS(ServiceException@code)와 스키마가 달라 종전 파서는
#   WMTS의 code 추출에 100% 실패했고, 진짜 원인(tiletype 오기)이 "auth/unknown"으로 은폐됐다.
LIVE_OWS_TILETYPE_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<ExceptionReport xmlns="http://www.opengis.net/ows/1.1"\n'
    '\tversion="1.1.0" xml:lang="kor">\n'
    '\t<Exception exceptionCode="InvalidParameterValue" locator="tiletype">\n'
    "\t\t<ExceptionText>\n"
    "<![CDATA[tiletype 파라미터의 값이 유효한 범위를 넘었습니다."
    " 유효한 파라미터 값의 범위 : [Base, midnight, Hybrid, Satellite, white],"
    " 입력한 파라미터 값 : gray]]>\n"
    "</ExceptionText>\n"
    "\t</Exception>\n"
    "</ExceptionReport>"
)


def test_wms_whitelist_includes_regulation_overlays_in_canonical_order():
    """★규제 오버레이 5종(2026-07-17 GetCapabilities+GetMap 매트릭스 채증) — web과 동기 핀.

    소문자 정본명 고정(#366 대문자·축약 함정 계열). 순서는 canonical LAYERS 조인 순서라
    바꾸면 상류 요청 문자열이 달라진다 — 의도적 변경 시에만 갱신할 것.
    """
    assert mod.ALLOWED_WMS_LAYERS == (
        "lp_pa_cbnd_bubun", "lp_pa_cbnd_bonbun", "lt_c_uq111",
        "lt_c_upisuq171", "lt_c_upisuq161", "lt_c_um710", "lt_c_uo101", "lt_c_uq123",
    )


def test_wmts_layer_whitelist_matches_upstream_canon():
    """★tiletype 정본 — 상류가 유효값을 직접 열거한 그대로여야 한다(web과 동기).

    종전 "gray"는 실존하지 않는 값이라 회색 배경지도가 전역 미표시됐다.
    """
    assert {"Base", "midnight", "Hybrid", "Satellite", "white"} == SUPPORTED_WMTS_LAYERS
    assert "gray" not in SUPPORTED_WMTS_LAYERS


def test_extract_code_and_locator_from_ows_exception_report():
    """OWS(WMTS) 스키마에서도 code·locator를 추출한다 — 원인 은폐 방지."""
    assert extract_vworld_code(LIVE_OWS_TILETYPE_XML) == "InvalidParameterValue"
    assert extract_vworld_locator(LIVE_OWS_TILETYPE_XML) == "tiletype"


def test_wms_schema_still_wins_and_has_no_locator():
    """WMS 경로 무회귀 — OWS 분기 추가가 기존 계약을 퇴행시키지 않는다."""
    assert extract_vworld_code(LIVE_INVALID_RANGE_XML) == "INVALID_RANGE"
    assert extract_vworld_locator(LIVE_INVALID_RANGE_XML) is None


def test_ows_exception_report_tag_is_not_mistaken_for_exception():
    """★<ExceptionReport version="1.1.0">를 <Exception>으로 오탐하지 않는다(접두 동일).

    \\s 경계가 없으면 ExceptionReport@version("1.1.0")을 code로 잡는 사고가 난다.
    """
    assert extract_vworld_code(LIVE_OWS_TILETYPE_XML) != "1.1.0"
    assert extract_vworld_code('<ExceptionReport version="1.1.0"></ExceptionReport>') is None


def test_ows_xml_is_classified_auth_and_surfaces_locator(monkeypatch):
    """200+OWS XML → 503 + (code/locator) 표면화. 투명타일로 무음 흡수 금지."""

    def _ows_response(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/xml;charset=UTF-8"},
            text=LIVE_OWS_TILETYPE_XML,
        )

    monkeypatch.setattr(mod, "_vworld_key", lambda: "SECRET-KEY")
    _mock_async_client(monkeypatch, _ows_response)
    client = TestClient(_app())
    resp = client.get("/api/v1/tiles/vworld/wmts/Base/6/24/54.png")
    assert resp.status_code == 503
    # ★locator 병기 필수 — OWS는 code가 InvalidParameterValue 하나로 뭉뚱그려져
    #   code만으로는 tiletype 오기와 key 무효를 구분할 수 없다.
    assert "InvalidParameterValue/tiletype" in resp.json()["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
