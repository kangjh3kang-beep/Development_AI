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
    out = network.LiveNetwork().get("https://example.test/x")
    assert out == b"LIVE-BODY"
    assert seen["url"] == "https://example.test/x"


def test_live_network_enabled_wraps_httpx_failure(monkeypatch):
    # 라이브 실패도 NetworkError로 통일(호출자=공급측이 fallback) — 무음 단정 금지(예외 표면화).
    monkeypatch.setattr(settings, "LIVE_NETWORK", True, raising=False)

    def boom(url, **kw):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(httpx, "get", boom)
    with pytest.raises(network.NetworkError):
        network.LiveNetwork().get("https://example.test/x")
