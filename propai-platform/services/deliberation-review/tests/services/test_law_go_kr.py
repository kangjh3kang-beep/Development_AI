"""국가법령정보센터(law.go.kr) 어댑터 — 검색/존재여부·키없음 graceful·OC 전달(httpx 모킹)."""
from app.adapters.legal.law_go_kr import LawGoKrSource


class _Resp:
    def __init__(self, data):
        self._d = data

    def raise_for_status(self):  # noqa: D102
        ...

    def json(self):
        return self._d


def test_no_key_returns_none(monkeypatch):
    monkeypatch.setenv("MOLEG_API_KEY", "")
    s = LawGoKrSource()
    assert not s.available
    assert s.search_law("건축법") is None
    assert s.law_exists("건축법") is None  # 결손(무음 단정 금지)


def test_law_exists_true(monkeypatch):
    monkeypatch.setenv("MOLEG_API_KEY", "test-oc")
    captured = {}

    def _get(url, params=None, timeout=None):
        captured.update(url=url, params=params)
        return _Resp({"LawSearch": {"totalCnt": "3", "law": [{"법령명한글": "건축법"}]}})

    import httpx
    monkeypatch.setattr(httpx, "get", _get)
    s = LawGoKrSource()
    assert s.available
    assert s.law_exists("건축법") is True
    assert captured["params"]["OC"] == "test-oc"  # OC=MOLEG_API_KEY 전달
    assert "lawSearch.do" in captured["url"]


def test_law_exists_false(monkeypatch):
    monkeypatch.setenv("MOLEG_API_KEY", "test-oc")
    import httpx
    monkeypatch.setattr(httpx, "get", lambda url, params=None, timeout=None: _Resp({"LawSearch": {"totalCnt": "0"}}))
    assert LawGoKrSource().law_exists("존재하지않는법") is False


def test_live_failure_graceful(monkeypatch):
    monkeypatch.setenv("MOLEG_API_KEY", "test-oc")

    def _boom(url, params=None, timeout=None):
        raise RuntimeError("network")

    import httpx
    monkeypatch.setattr(httpx, "get", _boom)
    assert LawGoKrSource().search_law("건축법") is None  # 실패 → None(폴백)
