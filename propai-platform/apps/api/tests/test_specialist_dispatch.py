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
    # 컨텍스트(tenant/project/address/pnu/allow_llm) 전파 확인.
    assert seen["zoning"] == {"tenant_id": "t", "project_id": "p", "address": "a", "pnu": "123",
                              "allow_llm": True}


@pytest.mark.asyncio
async def test_allow_llm_false_propagates_to_ctx(monkeypatch):
    """★A5: allow_llm=False가 coordinator.dispatch → SpecialistAgent.run까지 전파(무과금 게이트)."""
    seen: dict = {}

    async def _ok(self, domain, data, **ctx):
        seen[domain] = ctx
        return {"ok": True, "domain": domain, "summary": {}, "findings": [],
                "contradictions": None, "ledger": None}

    _patch_dispatch(monkeypatch, _ok)
    await run_specialist_domains({"zoning": {"zone_type": "z"}}, allow_llm=False)
    assert seen["zoning"]["allow_llm"] is False


@pytest.mark.asyncio
async def test_ok_entry_propagates_claims_and_recalled_count(monkeypatch):
    """★A4: LLM claims(citation_gate grounded)와 회상 provenance(recalled_count)가 ok 엔트리에 표면화."""
    async def _ok(self, domain, data, **ctx):
        return {"ok": True, "domain": domain, "summary": {}, "findings": [],
                "claims": [{"claim": "실효용적률 250% 적용", "basis": "FAR"}],
                "contradictions": None, "ledger": None,
                "rag_memories": [{"id": "1", "summary": "x"}, {"id": "2", "summary": "y"}]}

    _patch_dispatch(monkeypatch, _ok)
    out = await run_specialist_domains({"설계": {"use_zone": "z"}})
    assert out[0]["claims"] == [{"claim": "실효용적률 250% 적용", "basis": "FAR"}]
    assert out[0]["recalled_count"] == 2


@pytest.mark.asyncio
async def test_ok_entry_claims_defaults_empty_when_absent(monkeypatch):
    """claims/rag_memories 미제공(도구 응답에 없음)이면 빈 목록으로 정직 기본값(가짜 생성 X)."""
    async def _ok(self, domain, data, **ctx):
        return {"ok": True, "domain": domain, "summary": {}, "findings": [],
                "contradictions": None, "ledger": None}

    _patch_dispatch(monkeypatch, _ok)
    out = await run_specialist_domains({"zoning": {"zone_type": "z"}})
    assert out[0]["claims"] == [] and out[0]["recalled_count"] == 0


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


# ── 동기 교차검증 도메인 빌더(게이트 분기) — 전수감사 #2 회귀가드(경량·무거운 import 무관) ──
from app.services.agents.specialist_dispatch import build_sync_specialist_domains  # noqa: E402


def test_sync_domains_gate_off_zoning_far_only():
    """엔진 미설정(engine_set=False) → 결정론 zoning/far만(심의/설계 제외·불필요 지연 회피)."""
    d = build_sync_specialist_domains(
        zone_type="제2종일반주거지역", base={"k": 1}, land_area=500.0,
        address="서울 강남구", engine_set=False,
    )
    assert set(d.keys()) == {"zoning", "far"}
    assert d["zoning"]["zone_type"] == "제2종일반주거지역"
    assert d["far"]["land_area"] == 500.0


def test_sync_domains_gate_on_includes_deliberation_design():
    """엔진 설정(engine_set=True) → 심의/설계 추가(registry 고아 실호출 해소).

    ★A2 회귀가드: 엔진 계약키는 zone_type이 아니라 use_zone이다(permit_routes.py:39/
    design_routes.py:39 실측 — 본문 최상위 use_zone만 읽는다). zone_type을 보내면 두 도메인
    모두 use_zone=None → 항상 NEEDS_INPUT이었다(이 테스트가 그 회귀를 잠근다)."""
    d = build_sync_specialist_domains(
        zone_type="일반상업지역", base={}, land_area=0.0,
        address="서울 중구", engine_set=True,
    )
    assert set(d.keys()) == {"zoning", "far", "심의", "설계"}
    assert "zone_type" not in d["심의"] and "zone_type" not in d["설계"]
    assert d["심의"]["use_zone"] == "일반상업지역"
    assert d["심의"]["address"] == "서울 중구"
    assert d["설계"]["use_zone"] == "일반상업지역"
    # land_area=0.0(양수 아님) → calc_targets 생략(가짜 0㎡ 미공급).
    assert "calc_targets" not in d["설계"]
    assert d["설계"]["provided"] == {"program": True}


def test_sync_domains_gate_on_design_gets_calc_targets_when_land_area_positive():
    """land_area가 양수면 설계 입력에 calc_targets(plot_area)가 실전달된다(대지면적 종단배선)."""
    d = build_sync_specialist_domains(
        zone_type="제2종일반주거지역", base={}, land_area=500.0,
        address="서울 강남구", engine_set=True, pnu="1168010100101230000",
    )
    assert d["설계"]["calc_targets"] == [{"target": "plot_area", "payload": {"parcel_area": 500.0}}]
    assert d["설계"]["pnu"] == "1168010100101230000"
    assert d["심의"]["pnu"] == "1168010100101230000"
