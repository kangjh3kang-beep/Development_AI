"""SpecialistAgent 결정론 디스패치 공용 헬퍼(run_specialist_domains) 단위테스트.

comprehensive 부지분석·decision_brief 통합브리프가 공유하는 SSOT 경로 — dispatch·graceful·
status 표준화를 DB·실엔진 없이 검증한다. AgentCoordinator.dispatch를 monkeypatch로 대체.
"""

from __future__ import annotations

import pytest

from app.services.agents.specialist_dispatch import run_specialist_domains


def _patch_dispatch(monkeypatch, fn):
    import apps.api.core.coordinator as coord_mod
    monkeypatch.setattr(coord_mod.AgentCoordinator, "dispatch", fn)


@pytest.mark.asyncio
async def test_empty_domains_returns_empty():
    assert await run_specialist_domains({}) == []


@pytest.mark.asyncio
async def test_ok_dispatch_maps_status_ok_and_propagates_ctx(monkeypatch):
    seen: dict = {}

    async def _ok(self, domain, data, **ctx):
        seen[domain] = ctx
        return {"ok": True, "domain": domain, "task_type": f"{domain}_t",
                "summary": {"s": 1}, "findings": [{"claim": "c"}],
                "contradictions": None, "ledger": {"ok": True, "version": 2}}

    _patch_dispatch(monkeypatch, _ok)
    out = await run_specialist_domains(
        {"zoning": {"zone_type": "일반상업지역"}},
        tenant_id="t", project_id="p", address="a", pnu="123",
    )
    assert len(out) == 1
    assert out[0]["domain"] == "zoning" and out[0]["status"] == "ok"
    assert out[0]["findings"] == [{"claim": "c"}]
    assert out[0]["ledger"] == {"ok": True, "version": 2}
    # 컨텍스트(tenant/project/address/pnu) 전파 확인.
    assert seen["zoning"] == {"tenant_id": "t", "project_id": "p", "address": "a", "pnu": "123"}


@pytest.mark.asyncio
async def test_raise_becomes_unavailable_entry(monkeypatch):
    async def _boom(self, domain, data, **ctx):
        raise RuntimeError("ledger down")

    _patch_dispatch(monkeypatch, _boom)
    out = await run_specialist_domains(
        {"zoning": {"zone_type": "z"}, "permit": {"zone_type": "z", "dev_type": "M06"}},
    )
    assert {d["domain"] for d in out} == {"zoning", "permit"}
    assert all(d["status"] == "unavailable" for d in out)
    assert all(d.get("reason") for d in out)


@pytest.mark.asyncio
async def test_not_ok_dict_uses_message_reason(monkeypatch):
    async def _notok(self, domain, data, **ctx):
        return {"ok": False, "message": "unknown domain: zzz"}

    _patch_dispatch(monkeypatch, _notok)
    out = await run_specialist_domains({"zzz": {}})
    assert out[0]["status"] == "unavailable"
    assert "unknown domain" in out[0]["reason"]


@pytest.mark.asyncio
async def test_available_false_downgraded_to_unavailable(monkeypatch):
    """ok=True여도 도구가 summary.available=False(외부엔진 미설정/처리불가)면 정직하게 unavailable로 강등.
    '빈 findings + status:ok'가 '교차검증 통과'로 오인되는 반쪽출하 방지."""
    async def _degraded(self, domain, data, **ctx):
        return {"ok": True, "domain": domain, "findings": [],
                "summary": {"available": False, "reason": "engine_url_unset"}}

    _patch_dispatch(monkeypatch, _degraded)
    out = await run_specialist_domains({"심의": {"pnu": "", "address": "a"}})
    assert out[0]["status"] == "unavailable"
    assert out[0]["reason"] == "engine_url_unset"


@pytest.mark.asyncio
async def test_available_true_stays_ok(monkeypatch):
    """summary.available=True(엔진 정상 처리)는 status:ok 유지."""
    async def _live(self, domain, data, **ctx):
        return {"ok": True, "domain": domain, "findings": [{"check_id": "S1", "status": "pass"}],
                "summary": {"available": True, "overall_outcome": "likely"}}

    _patch_dispatch(monkeypatch, _live)
    out = await run_specialist_domains({"심의": {"pnu": "1168010100101230000"}})
    assert out[0]["status"] == "ok"
    assert out[0]["findings"]


@pytest.mark.asyncio
async def test_mixed_ok_and_fail(monkeypatch):
    async def _mixed(self, domain, data, **ctx):
        if domain == "permit":
            raise RuntimeError("x")
        return {"ok": True, "domain": domain, "task_type": "t", "summary": {},
                "findings": [], "contradictions": None, "ledger": None}

    _patch_dispatch(monkeypatch, _mixed)
    out = await run_specialist_domains(
        {"zoning": {"zone_type": "z"}, "permit": {"zone_type": "z", "dev_type": "M06"}},
    )
    by = {d["domain"]: d for d in out}
    assert by["zoning"]["status"] == "ok"
    assert by["permit"]["status"] == "unavailable"
