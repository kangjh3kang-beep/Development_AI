"""BaseAPIClient SourceSnapshot 훅 테스트 (W2-1) — opt-in 플래그·예외흡수·소스 메타 전달.

_request 전체(httpx 왕복)를 다시 목킹하지 않고, 실제 훅 단위인
_record_snapshot_ok/_record_snapshot_dead_letter를 직접 검증한다(기존 base_client 캐시·
Circuit Breaker 테스트와 중복 없이 W2-1 훅만 국소적으로 검증).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.integrations.base_client import BaseAPIClient


class _DummyClient(BaseAPIClient):
    service_name = "dummy"
    base_url = "https://dummy.example"


async def test_record_snapshot_ok_noop_when_disabled(monkeypatch):
    client = _DummyClient()
    assert client.snapshot_enabled is False  # 기본 OFF(W2-1 계약)

    called = []

    async def _fake_safe_record_success(**kwargs):
        called.append(kwargs)

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_success", _fake_safe_record_success)

    await client._record_snapshot_ok(
        method="GET", path="/x", params={"key": "1"}, payload_bytes=b"{}", http_status=200,
    )
    assert called == []


async def test_record_snapshot_ok_calls_when_enabled(monkeypatch):
    client = _DummyClient()
    client.snapshot_enabled = True
    client.source_name = "더미소스"
    client.authority_grade = "OFFICIAL"

    called = []

    async def _fake_safe_record_success(**kwargs):
        called.append(kwargs)

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_success", _fake_safe_record_success)

    await client._record_snapshot_ok(
        method="GET", path="/x", params={"key": "1"}, payload_bytes=b"{}", http_status=200,
    )
    assert len(called) == 1
    kw = called[0]
    assert kw["source_id"] == "dummy"
    assert kw["url"] == "https://dummy.example/x"
    assert kw["http_status"] == 200
    assert kw["source_name"] == "더미소스"
    assert kw["authority_grade"] == "OFFICIAL"


async def test_record_snapshot_ok_swallows_exception(monkeypatch):
    client = _DummyClient()
    client.snapshot_enabled = True

    async def _boom(**kwargs):
        raise RuntimeError("boom")

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_success", _boom)

    # ★계약 핵심: 기록 훅이 터져도 예외가 밖으로 전파되지 않는다(수집 호출경로 무영향).
    await client._record_snapshot_ok(
        method="GET", path="/x", params=None, payload_bytes=b"{}", http_status=200,
    )


async def test_record_snapshot_dead_letter_calls_when_enabled(monkeypatch):
    client = _DummyClient()
    client.snapshot_enabled = True

    called = []

    async def _fake_safe_record_dead_letter(**kwargs):
        called.append(kwargs)

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_dead_letter", _fake_safe_record_dead_letter)

    await client._record_snapshot_dead_letter(
        method="GET", path="/x", params=None, payload_bytes=None,
        http_status=None, error_message="net error",
    )
    assert len(called) == 1
    assert called[0]["error_message"] == "net error"
    assert called[0]["source_id"] == "dummy"


async def test_record_snapshot_dead_letter_noop_when_disabled(monkeypatch):
    client = _DummyClient()
    assert client.snapshot_enabled is False

    called = []

    async def _fake(**kwargs):
        called.append(kwargs)

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_dead_letter", _fake)

    await client._record_snapshot_dead_letter(
        method="GET", path="/x", params=None, payload_bytes=None,
        http_status=None, error_message="x",
    )
    assert called == []


async def test_record_snapshot_dead_letter_swallows_exception(monkeypatch):
    client = _DummyClient()
    client.snapshot_enabled = True

    async def _boom(**kwargs):
        raise RuntimeError("boom")

    import app.services.provenance.source_snapshot as ss
    monkeypatch.setattr(ss, "safe_record_dead_letter", _boom)

    await client._record_snapshot_dead_letter(
        method="GET", path="/x", params=None, payload_bytes=None,
        http_status=None, error_message="x",
    )


def test_base_client_default_snapshot_flags():
    # 기본값 회귀 가드 — BaseAPIClient 자체는 항상 opt-in(OFF)이어야 한다.
    assert BaseAPIClient.snapshot_enabled is False
    assert BaseAPIClient.source_name is None
    assert BaseAPIClient.authority_grade is None
