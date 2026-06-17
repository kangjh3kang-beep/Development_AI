"""Phase 1: design_audit가 prior_context를 받아 sections.prior_comparison을 가산하되 verdict는 불변."""
import pytest

pytestmark = pytest.mark.asyncio


def _params():
    return {"zone_type": "제2종일반주거지역", "site_area": 300.0, "gfa": 600.0}


async def test_prior_comparison_added_without_changing_verdict():
    from app.services.design_audit.design_audit_orchestrator import DesignAuditOrchestrator
    orch = DesignAuditOrchestrator()

    base = await orch.audit(_params(), zone_type="제2종일반주거지역")
    prior = {"version": 2, "payload": {"verdict": "부적합", "findings_brief": [
        {"check_id": "FAR-01", "status": "fail", "current": 999.0, "limit": 200.0}]}}
    withp = await orch.audit(_params(), zone_type="제2종일반주거지역", prior_context=prior)

    # verdict·counts 결정론 불변(read는 비교표면화 전용)
    assert withp["overall"]["verdict"] == base["overall"]["verdict"]
    assert withp["overall"].get("counts") == base["overall"].get("counts")
    # prior_comparison 섹션만 additive 가산
    assert "prior_comparison" in withp.get("sections", {})
    assert "prior_comparison" not in base.get("sections", {})
    assert withp["sections"]["prior_comparison"]["prior_verdict"] == "부적합"


async def test_audit_without_prior_unchanged():
    from app.services.design_audit.design_audit_orchestrator import DesignAuditOrchestrator
    orch = DesignAuditOrchestrator()
    a = await orch.audit(_params(), zone_type="제2종일반주거지역")
    assert "prior_comparison" not in a.get("sections", {})  # 미제공 시 무변동
