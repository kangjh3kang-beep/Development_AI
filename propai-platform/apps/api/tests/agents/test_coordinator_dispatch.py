"""Phase 3 T4 — coordinator.dispatch 실디스패치 단위테스트(무 DB).

기존 request_domain_agent(stub)는 불변. 신규 dispatch가 registry로 SpecialistAgent 실행.
import 경로는 기존 stub 테스트(test_core_modules)와 동일하게 apps.api.core.coordinator.
"""
from apps.api.core.coordinator import AgentCoordinator


async def test_dispatch_runs_specialist_and_returns_ledger(monkeypatch):
    from app.services.agents import registry

    class _FakeAgent:
        domain, task_type, analysis_type = "permit", "feasibility", "domain_agent_permit"

        async def run(self, data, **kw):
            return {"domain": "permit", "findings": [{"check_id": "PERMIT", "status": "pass"}],
                    "ledger": {"ok": True, "content_hash": "h"}}

    monkeypatch.setattr(registry, "get_specialist", lambda d: _FakeAgent(), raising=True)

    coord = AgentCoordinator()
    out = await coord.dispatch("permit", {"dev_type": "M06", "zone_type": "제2종일반주거지역"},
                               tenant_id="t", pnu="P1")
    assert out["ok"] is True and out["domain"] == "permit" and out["ledger"]["ok"] is True


async def test_dispatch_unknown_domain_returns_error():
    coord = AgentCoordinator()
    out = await coord.dispatch("nonexistent", {})
    assert out["ok"] is False and "unknown" in out["message"].lower()
