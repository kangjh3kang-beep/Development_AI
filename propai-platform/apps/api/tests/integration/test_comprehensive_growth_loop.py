"""Phase 1: 종합분석 성장루프 — 2회차가 1회차 원장 prior를 읽어 첨부하고, 새 버전을 write한다."""
import pytest

pytestmark = pytest.mark.asyncio


async def _db_available() -> bool:
    try:
        from sqlalchemy import text

        from app.core.database import async_session_factory, engine
        await engine.dispose()  # 교차-이벤트루프 풀 바인딩 초기화(테스트 격리 — 현재 루프에 재바인딩)
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _fake_base():
    return {
        "pnu": "1115010300102240000",
        "zone_type": "제2종일반주거지역",
        "land_register": {"area_sqm": 300.0},
        "effective_far": {"effective_far_pct": 200.0, "effective_bcr_pct": 60.0},
        "warnings": [],
    }


async def test_second_analysis_reads_prior_and_writes_new_version(monkeypatch):
    if not await _db_available():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행(skip≠검증, Task8 게이트)")
    from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService
    from app.services.ledger import analysis_ledger_service as ledger

    addr = "의정부동 224-phase1"
    tid = "t-phase1-comp"
    pnu = "1115010300102240000"
    svc = ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):
        return _fake_base()

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    # 1회차 — 원장에 site_analysis write-back
    r1 = await svc.analyze(addr, tenant_id=tid, project_id=None)
    assert "prior_analysis" in r1
    prior = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                    pnu=pnu, address=addr, project_id=None)
    assert prior is not None and prior["version"] >= 1

    # 2회차 — prior가 read되어 result에 첨부, 새 버전(멱등이면 동일) write
    r2 = await svc.analyze(addr, tenant_id=tid, project_id=None)
    assert r2.get("prior_analysis") is not None  # 1회차가 prior로 읽힘
    assert r2["prior_analysis"]["analysis_type"] == "site_analysis"
    after = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                    pnu=pnu, address=addr, project_id=None)
    assert after["version"] >= prior["version"]


async def test_analyze_appends_signature_parts_to_site_analysis_payload(monkeypatch):
    """히스토리 확산: site_analysis append payload에 signature_parts/input_signature가

    build_signature_parts(단일 소유자) 산식과 동일하게 병합돼야 한다(신규 type 신설 없이
    기존 site_analysis append에 additive로만 실린다 — 이중기록 회피).
    """
    if not await _db_available():
        pytest.skip("DB 미가용 — Postgres 기동 후 실행(skip≠검증, Task8 게이트)")
    from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger.ledger_adapters import build_input_signature, build_signature_parts

    addr = "의정부동 224-sigparts"
    tid = "t-sigparts-comp"
    pnu = "1115010300102240000"
    svc = ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):
        return _fake_base()

    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    await svc.analyze(addr, tenant_id=tid, project_id=None)

    after = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                    pnu=pnu, address=addr, project_id=None)
    assert after is not None
    payload = after["payload"]
    assert "signature_parts" in payload
    assert "input_signature" in payload
    # llm_provider 미전달(None) → use_llm=False, parcels 미전달 → parcel_count=1.
    expected_parts = build_signature_parts(address=addr, pnu=pnu, parcel_count=1, use_llm=False)
    assert payload["signature_parts"] == expected_parts
    assert payload["input_signature"] == build_input_signature(expected_parts)
    # 기존 site_analysis 필드(lineage/contradiction 소비 대상)는 그대로 보존(무회귀).
    assert payload["kind"] == "site_analysis"
    assert payload["zone_type"] == "제2종일반주거지역"
    # ★P3(R1 REVISE): location(입지등급) 사영필드 봉합 — 과거 wb_payload가 location을 적재하지
    # 않아 site_analysis DiffTable의 "입지등급"(location.grade) 행이 항상 "—"였다. 라이브 result
    # (comprehensive_analysis_service.py:610 "location": sec6)와 동일하게 write-back에도 실린다.
    assert "location" in payload
    assert payload["location"] is not None
    assert payload["location"].get("grade") in {"A", "B", "C", "D"}
