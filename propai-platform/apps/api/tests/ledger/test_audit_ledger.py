"""감사 흡수 — 순수 payload/키 함수(무DB) + 원장 누적·검증(DB)."""


def test_audit_stream_address_stable_and_nonempty():
    from app.services.ledger.audit_ledger import audit_stream_address

    assert audit_stream_address("t1") == "__audit__/t1"
    assert audit_stream_address(None) == "__audit__/global"
    # 같은 입력 = 같은 키(안정).
    assert audit_stream_address("t1") == audit_stream_address("t1")


def test_build_audit_payload_is_deterministic():
    from app.services.ledger.audit_ledger import build_audit_payload

    p = build_audit_payload(
        action="EXPORT", resource_type="project", resource_id="p1",
        user_id="u1", event_id="e1", event_ts=123.0,
        changes={"k": "v"}, metadata={"ip": "1.2.3.4"},
    )
    assert p == {
        "kind": "audit", "action": "EXPORT", "resource_type": "project",
        "resource_id": "p1", "user_id": "u1", "event_id": "e1", "event_ts": 123.0,
        "changes": {"k": "v"}, "metadata": {"ip": "1.2.3.4"},
    }
    # None → 빈 dict 정규화.
    p2 = build_audit_payload(
        action="LOGIN", resource_type="user", resource_id="u1",
        user_id="u1", event_id="e2", event_ts=1.0,
    )
    assert p2["changes"] == {} and p2["metadata"] == {}


async def test_append_audit_persists_and_verifies(tnt):
    from app.services.ledger import audit_ledger

    r1 = await audit_ledger.append_audit(
        action="CREATE", user_id="u1", resource_type="project", resource_id="p1",
        tenant_id=tnt, changes={"name": "n1"},
    )
    r2 = await audit_ledger.append_audit(
        action="UPDATE", user_id="u1", resource_type="project", resource_id="p1",
        tenant_id=tnt, changes={"name": "n2"},
    )
    assert r1["ok"] and r2["ok"]
    # 서로 다른 이벤트 → 멱등 dedup에 삼켜지지 않고 버전 증가.
    assert r1["version"] == 1 and r2["version"] == 2 and r2["unchanged"] is False

    v = await audit_ledger.verify_audit_chain(tenant_id=tnt)
    assert v["verified"] is True and v["length"] == 2
