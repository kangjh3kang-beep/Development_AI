"""G2BClient SourceSnapshot 훅 테스트 (W2-1).

G2BClient는 BaseAPIClient를 상속하지 않는 별도 httpx 클라이언트라(스파이크 확인),
성공/실패 두 진입점(fetch_bid_notices)에 직접 배선한 _snapshot_success/_snapshot_dead_letter
훅을 검증한다. 실 네트워크 없이 _get_client()를 가짜 httpx 클라이언트로 대체한다.
"""
from __future__ import annotations

import json

import httpx

from app.integrations import g2b_client as gm


class _FakeResp:
    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = json.dumps(self._json).encode("utf-8")

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _FakeHttpClient:
    def __init__(self, resp):
        self._resp = resp

    async def get(self, url, params=None):
        return self._resp


class _BoomHttpClient:
    """네트워크 자체가 실패하는 상황(응답 객체 없음) 모사."""

    def __init__(self, exc: Exception):
        self._exc = exc

    async def get(self, url, params=None):
        raise self._exc


def _install_fake_client(monkeypatch, client: gm.G2BClient, fake_http):
    async def _fake_get_client():
        return fake_http

    monkeypatch.setattr(client, "_get_client", _fake_get_client)


# ══════════════════════════════════════════════════════════════════════════
# 1) 훅 단위 — _snapshot_success/_snapshot_dead_letter 직접 검증(opt-in·예외흡수)
# ══════════════════════════════════════════════════════════════════════════


async def test_snapshot_success_calls_source_snapshot(monkeypatch):
    called = []

    async def _fake_safe_record_success(**kwargs):
        called.append(kwargs)

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_success", _fake_safe_record_success)

    await gm._snapshot_success("http://apis.data.go.kr/x", {"serviceKey": "SECRET"}, b"{}", 200)
    assert len(called) == 1
    assert called[0]["source_id"] == "g2b"
    assert called[0]["http_status"] == 200


async def test_snapshot_success_swallows_exceptions(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("boom")

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_success", _boom)

    # 예외가 전파되지 않아야 한다(수집 무영향).
    await gm._snapshot_success("url", {"serviceKey": "x"}, b"{}", 200)


async def test_snapshot_dead_letter_calls_source_snapshot(monkeypatch):
    called = []

    async def _fake_safe_record_dead_letter(**kwargs):
        called.append(kwargs)

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_dead_letter", _fake_safe_record_dead_letter)

    await gm._snapshot_dead_letter("url", {"serviceKey": "x"}, "err", http_status=500)
    assert len(called) == 1
    assert called[0]["error_message"] == "err"
    assert called[0]["http_status"] == 500


async def test_snapshot_dead_letter_swallows_exceptions(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("boom")

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_dead_letter", _boom)

    await gm._snapshot_dead_letter("url", {"serviceKey": "x"}, "err")


class _CapturingLogger:
    def __init__(self):
        self.warnings: list[tuple] = []

    def warning(self, *a, **k):
        self.warnings.append((a, k))

    def __getattr__(self, _name):
        return lambda *a, **k: None


async def test_snapshot_success_outer_exception_logs_warning(monkeypatch):
    # ★R1 MEDIUM-1: 무음 skip 금지 — 이중 except: pass에도 로그가 남아야 한다.
    async def _boom(**kwargs):
        raise RuntimeError("boom")

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_success", _boom)

    fake_logger = _CapturingLogger()
    monkeypatch.setattr(gm, "logger", fake_logger)

    await gm._snapshot_success("url", {"serviceKey": "x"}, b"{}", 200)
    assert len(fake_logger.warnings) == 1


async def test_snapshot_dead_letter_outer_exception_logs_warning(monkeypatch):
    async def _boom(**kwargs):
        raise RuntimeError("boom")

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_dead_letter", _boom)

    fake_logger = _CapturingLogger()
    monkeypatch.setattr(gm, "logger", fake_logger)

    await gm._snapshot_dead_letter("url", {"serviceKey": "x"}, "err")
    assert len(fake_logger.warnings) == 1


# ══════════════════════════════════════════════════════════════════════════
# 2) fetch_bid_notices 배선 — 성공/HTTP오류/네트워크오류 3경로에서 훅이 정확히 발화하는지
# ══════════════════════════════════════════════════════════════════════════


async def test_fetch_bid_notices_records_snapshot_on_success(monkeypatch):
    called = []

    async def _fake_success(url, params, payload_bytes, http_status):
        called.append((url, params, payload_bytes, http_status))

    monkeypatch.setattr(gm, "_snapshot_success", _fake_success)

    resp = _FakeResp(status_code=200, json_data={"response": {"body": {"items": []}}})
    client = gm.G2BClient(service_key="svc-key-123")
    _install_fake_client(monkeypatch, client, _FakeHttpClient(resp))

    result = await client.fetch_bid_notices(
        bid_type="공사", start_date="202601010000", end_date="202601020000",
    )
    assert result == []
    assert len(called) == 1
    url, params, payload_bytes, http_status = called[0]
    assert http_status == 200
    assert params["serviceKey"] == "svc-key-123"  # 원문 그대로 넘어감(마스킹은 source_snapshot 책임)


async def test_fetch_bid_notices_records_dead_letter_on_http_status_error(monkeypatch):
    called = []

    async def _fake_dead_letter(url, params, error_message, http_status=None, payload_bytes=None):
        called.append((url, params, error_message, http_status, payload_bytes))

    monkeypatch.setattr(gm, "_snapshot_dead_letter", _fake_dead_letter)

    fake_request = httpx.Request("GET", "http://apis.data.go.kr/x")
    fake_response = httpx.Response(500, request=fake_request, content=b"error body")

    class _ErrClient:
        async def get(self, url, params=None):
            return fake_response

    client = gm.G2BClient(service_key="svc-key-123")
    _install_fake_client(monkeypatch, client, _ErrClient())

    result = await client.fetch_bid_notices(bid_type="공사")
    assert result == []
    assert len(called) == 1
    _url, _params, _err, http_status, payload_bytes = called[0]
    assert http_status == 500
    assert payload_bytes == b"error body"


async def test_fetch_bid_notices_records_dead_letter_on_generic_exception(monkeypatch):
    called = []

    async def _fake_dead_letter(url, params, error_message, http_status=None, payload_bytes=None):
        called.append((url, params, error_message, http_status, payload_bytes))

    monkeypatch.setattr(gm, "_snapshot_dead_letter", _fake_dead_letter)

    client = gm.G2BClient(service_key="svc-key-123")
    _install_fake_client(monkeypatch, client, _BoomHttpClient(RuntimeError("network down")))

    result = await client.fetch_bid_notices(bid_type="공사")
    assert result == []
    assert len(called) == 1
    _url, _params, err, http_status, payload_bytes = called[0]
    assert http_status is None
    assert payload_bytes is None
    assert "network down" in err


async def test_fetch_award_results_records_snapshot_on_success(monkeypatch):
    called = []

    async def _fake_success(url, params, payload_bytes, http_status):
        called.append((url, params, payload_bytes, http_status))

    monkeypatch.setattr(gm, "_snapshot_success", _fake_success)

    resp = _FakeResp(status_code=200, json_data={"response": {"body": {"items": []}}})
    client = gm.G2BClient(service_key="svc-key-123")
    _install_fake_client(monkeypatch, client, _FakeHttpClient(resp))

    result = await client.fetch_award_results(bid_type="용역")
    assert result == []
    assert len(called) == 1
    assert called[0][3] == 200
