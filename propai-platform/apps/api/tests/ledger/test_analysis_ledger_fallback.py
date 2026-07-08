"""C3 producer — analysis_ledger_service.verify_chain이 변조탐지 시 record_fallback을 발화하는지.

실 Postgres 필요(tests/ledger/conftest.py::ledger_db가 DB 미가용이면 정직 skip — 거짓 통과 금지).
CI(postgres 서비스 컨테이너)에서는 실행된다. append_analysis로 2버전을 쌓고 1버전 content_hash를
직접 변조(raw SQL)해 verify_chain이 broken을 탐지하게 만든 뒤, record_fallback이
(service='analysis_ledger', kind='ledger_broken', severity='critical')로 호출됐는지 검증한다.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_verify_chain_broken_records_fallback(monkeypatch, ledger_db, tnt):
    import app.services.growth.capture_service as capture_service
    from app.services.ledger import analysis_ledger_service as als

    pnu = f"P{uuid.uuid4().hex[:10]}"
    r1 = await als.append_analysis(analysis_type="site_analysis", payload={"v": 1},
                                   tenant_id=tnt, pnu=pnu)
    r2 = await als.append_analysis(analysis_type="site_analysis", payload={"v": 2},
                                   tenant_id=tnt, pnu=pnu)
    assert r1["ok"] and r2["ok"]

    # 변조: version 1의 content_hash를 직접 훼손(payload_tampered 유발).
    await ledger_db.execute(text(
        "UPDATE analysis_ledger SET content_hash = 'tampered' "
        "WHERE tenant_id = :tid AND pnu = :pnu AND analysis_type = 'site_analysis' AND version = 1"),
        {"tid": tnt, "pnu": pnu})
    await ledger_db.commit()

    seen: dict = {}

    def _fake_record_fallback(service, kind, **meta):
        seen.update({"service": service, "kind": kind, **meta})

    monkeypatch.setattr(capture_service, "record_fallback", _fake_record_fallback)

    result = await als.verify_chain(analysis_type="site_analysis", tenant_id=tnt, pnu=pnu)
    assert result["verified"] is False
    assert result["broken"], "변조된 체인은 broken 목록이 채워져야 한다"

    assert seen["service"] == "analysis_ledger"
    assert seen["kind"] == "ledger_broken"
    assert seen["severity"] == "critical"
    assert seen["analysis_type"] == "site_analysis"
    assert seen["broken_count"] == len(result["broken"])


@pytest.mark.asyncio
async def test_verify_chain_intact_does_not_record_fallback(monkeypatch, ledger_db, tnt):
    """무결 체인은 record_fallback을 부르지 않는다(과다 신호 방지)."""
    import app.services.growth.capture_service as capture_service
    from app.services.ledger import analysis_ledger_service as als

    pnu = f"P{uuid.uuid4().hex[:10]}"
    await als.append_analysis(analysis_type="site_analysis", payload={"v": 1}, tenant_id=tnt, pnu=pnu)

    called = []
    monkeypatch.setattr(capture_service, "record_fallback",
                        lambda *a, **k: called.append((a, k)))

    result = await als.verify_chain(analysis_type="site_analysis", tenant_id=tnt, pnu=pnu)
    assert result["verified"] is True
    assert called == []
