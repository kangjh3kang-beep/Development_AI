"""verify_all_chains — 다중 체인 일괄검증 + 변조탐지 + 단건 verify 일치 회귀."""
from sqlalchemy import text


async def _seed(tnt):
    from app.services.ledger import analysis_ledger_service as ledger

    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"gfa": 1000},
        tenant_id=tnt, pnu="PNU-A", source="quick",
    )
    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"gfa": 1200},
        tenant_id=tnt, pnu="PNU-A", source="quick",
    )
    await ledger.append_analysis(
        analysis_type="feasibility", payload={"npv": 50},
        tenant_id=tnt, project_id="PRJ-1", source="project",
    )


async def test_all_clean_chains_verified(tnt):
    from app.services.ledger import analysis_ledger_service as ledger

    await _seed(tnt)
    res = await ledger.verify_all_chains(tenant_id=tnt)
    assert res["ok"] is True
    assert res["verified"] is True
    assert res["chains_checked"] == 2          # site_analysis(PNU-A) + feasibility(PRJ-1)
    assert res["broken_chains"] == []


async def test_tampered_payload_detected(tnt, ledger_db):
    from app.services.ledger import analysis_ledger_service as ledger

    await _seed(tnt)
    # payload 직접 변조(content_hash 불일치 유발).
    await ledger_db.execute(
        text(
            "UPDATE analysis_ledger SET payload = CAST(:p AS jsonb) "
            "WHERE tenant_id = :t AND pnu = 'PNU-A' AND version = 1"
        ),
        {"p": '{"gfa": 999999}', "t": tnt},
    )
    await ledger_db.commit()

    res = await ledger.verify_all_chains(tenant_id=tnt)
    assert res["verified"] is False
    assert any(c["analysis_type"] == "site_analysis" for c in res["broken_chains"])


async def test_project_filter_and_agreement_with_single_verify(tnt):
    from app.services.ledger import analysis_ledger_service as ledger

    await _seed(tnt)
    # project 필터: feasibility 체인만.
    res = await ledger.verify_all_chains(tenant_id=tnt, project_id="PRJ-1")
    assert res["chains_checked"] == 1
    assert res["verified"] is True
    # 단건 verify_chain 과 일치(회귀): 동일 체인은 동일 판정.
    single = await ledger.verify_chain(
        analysis_type="feasibility", tenant_id=tnt, project_id="PRJ-1"
    )
    assert single["verified"] is True


async def test_pnu_chain_with_mixed_address_is_single_chain(tnt):
    """같은 pnu에 address 유/무가 섞여도 _chain_where(pnu 우선)와 동일하게 한 체인으로 검증(G5 회귀)."""
    from app.services.ledger import analysis_ledger_service as ledger

    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"v": 1},
        tenant_id=tnt, pnu="PNU-MIX", address="서울 어딘가", source="quick",
    )
    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"v": 2},
        tenant_id=tnt, pnu="PNU-MIX", source="quick",        # address 미지정
    )
    res = await ledger.verify_all_chains(tenant_id=tnt)
    mix = [c for c in res["broken_chains"] if c["pnu"] == "PNU-MIX"]
    assert mix == []                                          # pnu 우선 → 끊김 오탐 없음
    single = await ledger.verify_chain(
        analysis_type="site_analysis", tenant_id=tnt, pnu="PNU-MIX"
    )
    assert single["verified"] is True and single["length"] == 2


async def test_duplicate_version_detected(tnt, ledger_db):
    """동시 append 경쟁조건 사후탐지 — 같은 version 2행이면 duplicate_version 보고."""
    from sqlalchemy import text

    from app.services.ledger import analysis_ledger_service as ledger

    await ledger.append_analysis(
        analysis_type="permit", payload={"x": 1},
        tenant_id=tnt, pnu="PNU-DUP", source="quick",
    )
    # version=1 행을 복제(잠금 부재 경쟁조건 시뮬레이션).
    await ledger_db.execute(text(
        "INSERT INTO analysis_ledger(tenant_id, pnu, analysis_type, version, payload, content_hash) "
        "SELECT tenant_id, pnu, analysis_type, version, payload, content_hash FROM analysis_ledger "
        "WHERE tenant_id = :t AND pnu = 'PNU-DUP'"), {"t": tnt})
    await ledger_db.commit()

    res = await ledger.verify_all_chains(tenant_id=tnt)
    dup = [c for c in res["broken_chains"]
           if c["pnu"] == "PNU-DUP" and any(b["issue"] == "duplicate_version" for b in c["broken"])]
    assert dup, "동일 version 중복이 duplicate_version으로 탐지돼야 함"
