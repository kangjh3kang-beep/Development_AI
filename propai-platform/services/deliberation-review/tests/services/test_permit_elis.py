"""INC-PD6 — 자치법규(elis) 어댑터: graceful degrade(라이브 off/실패→None), allowlist 호스트, 성공 페이로드."""
from app.adapters.legal.elis import ElisOrdinanceSource
from app.adapters.network import NetworkError


class _FakeNet:
    def __init__(self, *, raise_: bool = False, content: bytes = b"") -> None:
        self._raise = raise_
        self._content = content

    def get(self, url: str) -> bytes:
        if self._raise:
            raise NetworkError("disabled")
        return self._content


def test_elis_graceful_when_network_unavailable():
    # 라이브 off/실패 → None(예외 비전파, 무음 단정 아님: 호출측이 미상 표면화)
    src = ElisOrdinanceSource(net=_FakeNet(raise_=True))
    assert src.fetch_ordinance(jurisdiction="1111000000", keyword="경관") is None


def test_elis_empty_body_returns_none():
    src = ElisOrdinanceSource(net=_FakeNet(content=b""))
    assert src.fetch_ordinance(jurisdiction="1111000000", keyword="경관") is None


def test_elis_success_returns_payload_with_source():
    body = "<html>조례 본문</html>".encode()   # bytes 리터럴은 ASCII만 — 한글은 encode()
    src = ElisOrdinanceSource(net=_FakeNet(content=body))
    res = src.fetch_ordinance(jurisdiction="1111000000", keyword="경관")
    assert res is not None
    assert res["source"] == "elis.go.kr"
    assert res["jurisdiction"] == "1111000000"
    assert res["keyword"] == "경관"
    assert res["raw"] == body


def test_elis_uses_allowlisted_host():
    # SSRF allowlist 호스트(elis.go.kr)만 — network.host_allowed가 통과시키는 도메인
    assert "elis.go.kr" in ElisOrdinanceSource().base_url


def test_elis_real_network_off_returns_none():
    # 실 LiveNetwork(기본 LIVE_NETWORK off) → NetworkError → None(end-to-end graceful)
    assert ElisOrdinanceSource().fetch_ordinance(jurisdiction="1111000000", keyword="경관") is None
