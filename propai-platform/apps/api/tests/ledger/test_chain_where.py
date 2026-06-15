"""_chain_where NULL-safe 버그픽스 회귀.

순수 함수 테스트(무DB)로 SQL 분기를 박제 + (DB 있으면) project_id-only 체인 연결 통합 검증.
"""


def test_chain_where_empty_address_uses_is_null():
    """pnu·address 모두 없으면 address_norm IS NULL로 조회(=INSERT의 NULL 저장행과 정합)."""
    from app.services.ledger.analysis_ledger_service import _chain_where

    # 빈 주소(저장 시 NULL) → IS NULL 분기여야 함(버그픽스 핵심)
    sql_empty, params_empty = _chain_where(None, "", "PRJ-1")
    assert "address_norm IS NULL" in sql_empty
    assert "addr" not in params_empty            # 빈 주소엔 addr 바인딩 없음
    assert "project_id = :pid" in sql_empty

    # 비어있지 않은 주소 → 동등 비교 유지(기존 동작 불변)
    sql_addr, params_addr = _chain_where(None, "서울 강남", None)
    assert "address_norm = :addr" in sql_addr
    assert params_addr["addr"] == "서울 강남"

    # pnu 있으면 pnu 우선(기존 동작 불변)
    sql_pnu, _ = _chain_where("PNU-1", "", None)
    assert "pnu = :pnu" in sql_pnu


async def test_project_only_chain_links_versions(tnt):
    """project_id-only 체인이 NULL-safe로 버전 연결되는지(통합, DB 있을 때)."""
    from app.services.ledger import analysis_ledger_service as ledger

    r1 = await ledger.append_analysis(
        analysis_type="feasibility", payload={"npv": 10},
        tenant_id=tnt, project_id="PRJ-NULLSAFE", source="project",
    )
    r2 = await ledger.append_analysis(
        analysis_type="feasibility", payload={"npv": 20},
        tenant_id=tnt, project_id="PRJ-NULLSAFE", source="project",
    )
    assert r1["version"] == 1
    assert r2["version"] == 2 and r2["unchanged"] is False     # 버그 시엔 1,1로 평탄화

    latest = await ledger.get_latest(
        analysis_type="feasibility", tenant_id=tnt, project_id="PRJ-NULLSAFE",
    )
    assert latest is not None and latest["version"] == 2

    v = await ledger.verify_chain(
        analysis_type="feasibility", tenant_id=tnt, project_id="PRJ-NULLSAFE",
    )
    assert v["verified"] is True and v["length"] == 2          # 버그 시엔 chain_broken 오탐
