"""031 원장 마이그레이션 — 체인 연결 + (DB 있으면) 세션 간 영속 검증."""
import importlib.util
import os

MIG = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "database", "migrations", "versions", "031_analysis_ledger.py",
)


def _load():
    spec = importlib.util.spec_from_file_location("mig031", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain_links_to_030():
    assert os.path.exists(MIG), f"마이그레이션 부재: {MIG}"
    mod = _load()
    assert mod.revision == "031_analysis_ledger"
    assert mod.down_revision == "030_livekit_recordings"
    assert callable(mod.upgrade) and callable(mod.downgrade)


async def test_append_persists_across_sessions(tnt):
    """원장 append는 별도(=재오픈) 세션에서도 읽힌다 = 영속(재시작 후 소실 0)."""
    from app.services.ledger import analysis_ledger_service as ledger

    res = await ledger.append_analysis(
        analysis_type="site_analysis",
        payload={"gfa": 75000, "note": "persist-check"},
        tenant_id=tnt, pnu="1111010100100010000",
        source="quick", created_by="tester",
    )
    assert res["ok"] is True and res["version"] == 1

    # get_latest 는 새로운 async_session_factory() 세션을 연다 → 영속이면 읽혀야 함.
    latest = await ledger.get_latest(
        analysis_type="site_analysis", tenant_id=tnt, pnu="1111010100100010000",
    )
    assert latest is not None
    assert latest["payload"]["gfa"] == 75000
    assert latest["version"] == 1
