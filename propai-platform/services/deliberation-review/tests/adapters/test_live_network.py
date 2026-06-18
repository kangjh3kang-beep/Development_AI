"""INC-14 — LiveNetwork 공급측 실 httpx 주입(env 게이트). 기본 mock(NetworkError),
LIVE_NETWORK=on 시 실 httpx GET → bytes. 실패는 NetworkError로 흡수(공급측 fallback). INV-13: 소비경로 무관.
"""
import httpx
import pytest

from app.adapters import network
from app.settings import settings


def test_live_network_disabled_by_default_raises(monkeypatch):
    # 기본(mock): 라이브 호출 비활성 → NetworkError(공급측이 fallback으로 흡수).
    monkeypatch.setattr(settings, "LIVE_NETWORK", False, raising=False)
    with pytest.raises(network.NetworkError):
        network.LiveNetwork().get("https://example.test/x")


def test_live_network_enabled_uses_httpx(monkeypatch):
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    seen = {}

    class _Resp:
        content = b"LIVE-BODY"

        def raise_for_status(self):
            return None

    def fake_get(url, **kw):
        seen["url"] = url
        return _Resp()

    monkeypatch.setattr(httpx, "get", fake_get)
    out = network.LiveNetwork().get("https://www.law.go.kr/x")  # 화이트리스트 1차출처
    assert out == b"LIVE-BODY"
    assert seen["url"] == "https://www.law.go.kr/x"


def test_live_network_allows_allowlisted_subdomain(monkeypatch):
    # 1차출처 등록도메인의 서브도메인 허용(api.elis.go.kr 등).
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)

    class _Resp:
        content = b"OK"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(httpx, "get", lambda url, **kw: _Resp())
    assert network.LiveNetwork().get("https://api.elis.go.kr/diff") == b"OK"


def test_live_network_rejects_non_allowlisted_host(monkeypatch):
    # 화이트리스트 외 호스트(잔여 SSRF 표면) 차단 — httpx 미호출.
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    called = {"n": 0}
    monkeypatch.setattr(httpx, "get", lambda url, **kw: called.__setitem__("n", called["n"] + 1))
    with pytest.raises(network.NetworkError):
        network.LiveNetwork().get("https://evil.example.com/x")
    assert called["n"] == 0


def test_live_network_rejects_substring_spoof_host(monkeypatch):
    # law.go.kr.evil.com 류(substring 매칭 우회) 차단 — hostname 정확/접미사 매칭.
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    monkeypatch.setattr(httpx, "get", lambda url, **kw: pytest.fail("must not fetch"))
    with pytest.raises(network.NetworkError):
        network.LiveNetwork().get("https://law.go.kr.evil.com/x")


def test_live_network_rejects_non_https_scheme(monkeypatch):
    # https 외 스킴(file://·http 사설IP 등) 차단.
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)
    monkeypatch.setattr(httpx, "get", lambda url, **kw: pytest.fail("must not fetch"))
    with pytest.raises(network.NetworkError):
        network.LiveNetwork().get("http://www.law.go.kr/x")


def test_live_network_enabled_wraps_httpx_failure(monkeypatch):
    # 라이브 실패도 NetworkError로 통일(호출자=공급측이 fallback) — 무음 단정 금지(예외 표면화).
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)

    def boom(url, **kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(network.NetworkError):
        network.LiveNetwork().get("https://www.law.go.kr/x")


def test_tier2_harvester_rejects_substring_spoof():
    # Tier2 화이트리스트가 hostname 정확/접미사 매칭이어야 law.go.kr.evil.com을 거부(substring 우회 차단).
    # 성공하는 network 스텁 주입 → 거부 사유는 오직 화이트리스트(통과 시 fetch되어 실패해야 함).
    from app.supply.harvester.tier2_site_harvester import Tier2SiteHarvester

    class _OkNet:
        def get(self, url):
            return b"BODY"

    h = Tier2SiteHarvester(network=_OkNet())
    with pytest.raises(network.NetworkError):
        h.harvest("https://law.go.kr.evil.com/doc")
    # 정상 화이트리스트 호스트는 통과(fetch 성공).
    assert h.harvest("https://www.law.go.kr/doc", jurisdiction="J")
