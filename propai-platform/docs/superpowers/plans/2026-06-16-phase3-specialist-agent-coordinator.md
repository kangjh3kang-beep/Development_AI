# Phase 3 — SpecialistAgent + Coordinator 실구현 (W4 닫기) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 또는 superpowers:executing-plans로 task별 실행. 체크박스(`- [ ]`) 추적.

**Goal:** 계층3 SpecialistAgent가 (prior read)+(계층1 결정론 도구 호출)+(citation_gate grounded 발언)+(Phase 2 원장 cite=contradiction+lineage)를 수행하고, coordinator가 이를 디스패치해 **W4(계층3→원장 cite)를 닫는다.**

**Architecture:** 결정론 우선 — 수치는 계층1 도구에서만 생성(LLM은 해석·서술만, GROUNDING_RULE+citation_gate enforce). 원장 cite는 Phase 2 `_append_with_lineage`(prior 모순+lineage). 의존성 주입(tool·interpreter·recorder)으로 LLM/DB 없이도 코어 단위테스트 가능. 데드 `coordinator.py:9` 스텁을 실디스패치로 격상.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0(async)/asyncpg, Postgres16(실DB), pytest 9(asyncio_mode=auto). LLM 경로는 venv `langchain_core` 부재로 graceful degrade(결정론·원장 테스트 무영향).

**불변규칙(전 Task):** additive·하위호환 · 결정론 코어/수치/verdict 불변(SpecialistAgent는 도구 수치 그대로 cite) · **LLM 수치 비생성**(citation_gate가 미근거 수치/법조문을 '전문가 확인 필요'로 치환) · 정직표기 · alembic 금지(원장은 lazy `_ensure`) · feature 브랜치 커밋·푸시만(머지·배포 보류).

**환경(매 테스트):**
```
export DATABASE_URL='postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db'
export INTERP_REDIS_CACHE=0
cd apps/api && .venv/bin/python -m pytest <파일> -q -rs
```
⚠️ WSL 명령은 **PowerShell 도구**로(Bash=Git Bash 경로변환 깨짐). 실DB 테스트는 `engine.dispose()` 루프격리(conftest 적용됨).

---

## 그라운딩 요약 (file:line — verify-gaps-with-real-code)

| 자산 | 위치 | Phase 3 용도 |
|---|---|---|
| 데드 coordinator | `apps/api/core/coordinator.py:6-17`(`pass`@9, `request_domain_agent(agent_name,payload,retry_count=0)`) | 실디스패치로 격상(T4) |
| 빈 agents 폴더 | `apps/api/app/services/agents/__init__.py`(0B) | SpecialistAgent 신설 위치(T1) |
| Phase2 원장 헬퍼 | `ledger_adapters._append_with_lineage`(prior 모순+lineage) · `record_feasibility_result` 패턴 | cite 경로(T2) |
| prior read | `prior_context.load_prior/build_prior_block`(Phase1) | SpecialistAgent prior 주입 |
| citation_gate | `blindspot_interpreter.py:256` `citation_gate(items, findings, derived_signals, *, prior_evidence=None)` 순수함수 | grounded 발언 강제(T1) |
| 계층1 결정론 도구 | `permit_validator.check_permit_feasibility(dev_type, zone_type)`(permit_validator.py:72, 순수·무DB·무LLM) → `{is_permitted, permit_complexity, type_name, reason}` | T3 구체 specialist 도구 |
| 기존 도메인에이전트 | `apps/api/services/domain_agents_service.py`(`run_domain`/`_score`, 이미 W3 cite하나 prior/lineage/citation_gate 미연동) | T4 coordinator가 보완(additive, 기존 경로 불변) |
| 원장 API | `analysis_ledger_service.append_analysis/get_latest/verify_chain` | cite·검증 |

**결론:** Phase 3 = 위 자산을 조립하는 **additive 신규 SpecialistAgent + coordinator 디스패치**. 기존 `domain_agents_service`/`coordinator` stub tests는 보존(별도 경로). 결정론 코어·기존 동작 불변.

---

## File Structure
- Create `apps/api/app/services/agents/specialist_agent.py` — SpecialistAgent 코어(도구→prior→citation_gate→cite).
- Create `apps/api/app/services/agents/registry.py` — 도메인→SpecialistAgent 등록/조회 + permit 구체 구성.
- Modify `apps/api/app/services/ledger/ledger_adapters.py` — `specialist_to_ledger` 매퍼 + `record_specialist_result` 공개 래퍼(`_append_with_lineage` 사용).
- Modify `apps/api/core/coordinator.py` — `AgentCoordinator.dispatch()` 실구현(registry로 SpecialistAgent 디스패치). 기존 `request_domain_agent` 시그니처/stub 동작 불변.
- Create `apps/api/tests/agents/__init__.py`, `conftest.py`(ledger conftest의 `_db` 패턴 복제), `test_specialist_agent.py`, `test_registry.py`, `test_coordinator_dispatch.py`, `test_phase3_e2e.py`.

---

## Task 1: SpecialistAgent 코어 (의존성 주입 — 무 DB/LLM 단위테스트)

**Files:** Create `apps/api/app/services/agents/specialist_agent.py` · Test `apps/api/tests/agents/test_specialist_agent.py`

- [ ] **Step 1: 실패 테스트**

```python
# apps/api/tests/agents/test_specialist_agent.py
import pytest
from app.services.agents.specialist_agent import SpecialistAgent


def _tool(data):
    # 계층1 결정론 도구 모사 — 수치는 여기서만 생성
    return {"findings": [{"check_id": "PERMIT", "status": "pass" if data.get("ok") else "fail",
                          "current": data.get("far", 200.0), "limit": 250.0}],
            "summary": {"far": data.get("far", 200.0)}}


async def test_run_calls_tool_and_cites_ledger_deterministically():
    captured = {}
    async def _fake_recorder(*, analysis_type, payload, **kw):
        captured["analysis_type"] = analysis_type
        captured["payload"] = payload
        return {"ok": True, "version": 1, "content_hash": "h1",
                "contradictions": {"has_contradiction": False, "counts": {}, "max_severity": None}}
    async def _fake_prior(**kw):
        return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=None, recorder=_fake_recorder, prior_loader=_fake_prior)
    out = await agent.run({"ok": True, "far": 210.0}, tenant_id="t", pnu="P1")
    assert out["domain"] == "permit"
    assert out["findings"][0]["check_id"] == "PERMIT" and out["findings"][0]["current"] == 210.0
    assert out["ledger"]["content_hash"] == "h1"
    # 원장 payload: analysis_type=domain_agent_permit, findings_brief 보존(수치 불변)
    assert captured["analysis_type"] == "domain_agent_permit"
    assert captured["payload"]["findings_brief"][0]["current"] == 210.0
    assert captured["payload"]["claims"] == []   # interpreter 없음 → 발언 없음


async def test_llm_claims_pass_through_citation_gate_grounded_only():
    # interpreter가 미근거 수치를 말해도 citation_gate가 '전문가 확인 필요'로 치환
    class _Interp:
        async def generate_interpretation(self, tool_out, *, prior_context=None):
            return {"items": [{"claim": "용적률 999% 초과 위험", "basis": "PERMIT", "confidence": "high"}]}
    captured = {}
    async def _rec(*, analysis_type, payload, **kw):
        captured["payload"] = payload
        return {"ok": True, "version": 1, "content_hash": "h", "contradictions": {"has_contradiction": False}}
    async def _prior(**kw): return None

    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_Interp(), recorder=_rec, prior_loader=_prior)
    out = await agent.run({"ok": True, "far": 200.0}, tenant_id="t", pnu="P1")
    # 999는 findings(현재 200/limit 250)에 없는 미근거 수치 → 치환됨
    claim_text = out["claims"][0]["claim"]
    assert "999" not in claim_text and "전문가 확인 필요" in claim_text


async def test_interpreter_failure_is_graceful():
    class _Boom:
        async def generate_interpretation(self, *a, **k):
            raise RuntimeError("LLM down")
    async def _rec(*, analysis_type, payload, **kw):
        return {"ok": True, "version": 1, "content_hash": "h", "contradictions": {"has_contradiction": False}}
    async def _prior(**kw): return None
    agent = SpecialistAgent(domain="permit", task_type="feasibility", tool=_tool,
                            interpreter=_Boom(), recorder=_rec, prior_loader=_prior)
    out = await agent.run({"ok": True}, tenant_id="t", pnu="P1")
    assert out["claims"] == []           # LLM 실패 → 발언 없음(결정론 findings는 유지)
    assert out["findings"]               # 결정론 산출은 무중단
```

- [ ] **Step 2: 실패 확인** — `.venv/bin/python -m pytest tests/agents/test_specialist_agent.py -q` → FAIL(모듈 없음).

- [ ] **Step 3: 구현 `specialist_agent.py`**

```python
"""Phase 3 계층3 — SpecialistAgent: 결정론 도구 호출 + citation_gate grounded 발언 + 원장 cite(W4 닫기).

결정론 우선: 수치는 계층1 도구에서만 생성(불변). LLM은 해석·서술만(citation_gate가 미근거 수치/법조문을
'전문가 확인 필요'로 치환). 원장 cite는 Phase 2 모순+lineage(record_specialist_result). 도구/인터프리터/
recorder/prior_loader는 주입(테스트·LLM부재 graceful).
"""
from __future__ import annotations

import inspect
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


def _to_items(raw: Any) -> list[dict[str, Any]]:
    """인터프리터 출력 → citation_gate 입력 items([{claim, basis, confidence}])로 정규화."""
    if isinstance(raw, dict):
        items = raw.get("items")
        if isinstance(items, list):
            return [it for it in items if isinstance(it, dict)]
    if isinstance(raw, list):
        return [it for it in raw if isinstance(it, dict)]
    return []


class SpecialistAgent:
    """단일 도메인 전문가 에이전트. 결정론 도구 → prior → (LLM+citation_gate) → 원장 cite."""

    def __init__(
        self, *, domain: str, task_type: str,
        tool: Callable[[dict[str, Any]], Any],
        interpreter: Any | None = None,
        recorder: Callable[..., Any] | None = None,
        prior_loader: Callable[..., Any] | None = None,
    ) -> None:
        self.domain = domain
        self.task_type = task_type
        self._tool = tool
        self._interpreter = interpreter
        self._recorder = recorder
        self._prior_loader = prior_loader

    @property
    def analysis_type(self) -> str:
        return f"domain_agent_{self.domain}"

    async def run(
        self, data: dict[str, Any], *, tenant_id: str | None = None,
        project_id: str | None = None, pnu: str | None = None,
        address: str | None = None, created_by: str | None = None,
    ) -> dict[str, Any]:
        # 1) 계층1 결정론 도구 — 수치는 여기서만 생성(불변)
        tool_out = self._tool(data)
        if inspect.isawaitable(tool_out):
            tool_out = await tool_out
        tool_out = tool_out if isinstance(tool_out, dict) else {}
        findings = tool_out.get("findings") or []

        # 2) prior read(Phase 1) — best-effort
        prior = None
        loader = self._prior_loader
        if loader is None:
            from app.services.ledger.prior_context import load_prior as loader
        try:
            prior = await loader(analysis_type=self.analysis_type, tenant_id=tenant_id,
                                 pnu=pnu, address=address, project_id=project_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("specialist prior read 실패(graceful)", domain=self.domain, err=str(e)[:160])
            prior = None

        # 3) LLM 해석(선택) + citation_gate grounded만 — 수치 비생성
        claims: list[dict[str, Any]] = []
        if self._interpreter is not None:
            try:
                from app.services.design_audit.blindspot_interpreter import citation_gate
                from app.services.ledger.prior_context import build_prior_block
                raw = await self._interpreter.generate_interpretation(
                    tool_out, prior_context=build_prior_block(prior))
                claims = citation_gate(_to_items(raw), findings, prior_evidence=prior)
            except Exception as e:  # noqa: BLE001
                logger.warning("specialist LLM 해석 스킵(graceful)", domain=self.domain, err=str(e)[:160])
                claims = []

        # 4) 원장 cite(Phase 2: prior 모순 + lineage)
        recorder = self._recorder
        if recorder is None:
            from app.services.ledger.ledger_adapters import record_specialist_result as recorder
        payload = {
            "kind": "domain_agent", "schema_version": "domain_agent/v2",
            "domain": self.domain, "task_type": self.task_type,
            "summary": tool_out.get("summary") or {},
            "findings_brief": findings,
            "claims": claims,
        }
        wb = await recorder(
            analysis_type=self.analysis_type, payload=payload,
            tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
            source=f"specialist_{self.domain}", created_by=created_by)
        wb = wb if isinstance(wb, dict) else {}
        return {
            "domain": self.domain, "task_type": self.task_type,
            "findings": findings, "claims": claims,
            "summary": tool_out.get("summary") or {},
            "contradictions": wb.get("contradictions"),
            "ledger": {"ok": wb.get("ok"), "version": wb.get("version"),
                       "content_hash": wb.get("content_hash")},
        }
```

- [ ] **Step 4: 통과 확인** — `pytest tests/agents/test_specialist_agent.py -q` → 3 passed.
- [ ] **Step 5: 커밋** — `feat(agents): Phase3 T1 SpecialistAgent 코어(결정론 도구+citation_gate+원장 cite, DI)`

---

## Task 2: record_specialist_result 래퍼 (ledger_adapters) — 실 DB cite

**Files:** Modify `apps/api/app/services/ledger/ledger_adapters.py` · Test `apps/api/tests/agents/test_phase3_e2e.py`(신규, conftest `_db` 패턴)

`_append_with_lineage`(Phase 2)를 그대로 쓰는 공개 래퍼 추가. 도메인에이전트 confidence delta 임계 포함.

- [ ] **Step 1: 실패 테스트(실 DB e2e)** — `apps/api/tests/agents/conftest.py`에 ledger conftest와 동일한 `_db()` helper. 테스트:

```python
# tests/agents/test_phase3_e2e.py (발췌 — 전체는 T5에서 확장)
import uuid, pytest
pytestmark = pytest.mark.asyncio

async def _db() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory, engine
        await engine.dispose()
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

async def test_record_specialist_result_writes_findings_and_lineage():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger.ledger_adapters import record_specialist_result
    from app.services.ledger import analysis_ledger_service as ledger, lineage
    tid, pnu = f"t-p3-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    p1 = {"kind": "domain_agent", "schema_version": "domain_agent/v2", "domain": "permit",
          "task_type": "feasibility", "summary": {"far": 200.0},
          "findings_brief": [{"check_id": "PERMIT", "status": "pass", "current": 200.0, "limit": 250.0}], "claims": []}
    r1 = await record_specialist_result(analysis_type="domain_agent_permit", payload=p1,
                                        tenant_id=tid, pnu=pnu, source="specialist_permit")
    assert r1["contradictions"]["has_contradiction"] is False
    p2 = {**p1, "summary": {"far": 260.0},
          "findings_brief": [{"check_id": "PERMIT", "status": "fail", "current": 260.0, "limit": 250.0}]}
    r2 = await record_specialist_result(analysis_type="domain_agent_permit", payload=p2,
                                        tenant_id=tid, pnu=pnu, source="specialist_permit")
    assert r2["contradictions"]["has_contradiction"] is True          # status flip + far 30%
    latest = await ledger.get_latest(analysis_type="domain_agent_permit", tenant_id=tid, pnu=pnu)
    parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tid)
    assert parents and parents[0]["max_severity"] == "high"
    # 정리
    from sqlalchemy import text
    from app.core.database import async_session_factory
    async with async_session_factory() as db:
        await db.execute(text("DELETE FROM analysis_lineage WHERE tenant_id=:t"), {"t": tid})
        await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id=:t"), {"t": tid})
        await db.commit()
```

- [ ] **Step 2: 실패 확인** — FAIL(`record_specialist_result` 없음).
- [ ] **Step 3: 구현(ledger_adapters.py 끝에 추가)**

```python
async def record_specialist_result(
    *, analysis_type: str, payload: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, pnu: str | None = None, address: str | None = None,
    source: str = "specialist", created_by: str | None = None,
) -> dict[str, Any]:
    """Phase 3 계층3 SpecialistAgent 산출 → 원장 cite(prior 모순 + lineage). W4 닫기.

    payload는 SpecialistAgent가 만든 domain_agent/v2(findings_brief 포함). confidence_score 등
    수치 델타 임계는 도메인별로 다를 수 있어 기본 상대임계만 사용(필요 시 abs_thresholds 확장).
    """
    return await _append_with_lineage(
        analysis_type=analysis_type, payload=payload,
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source=source, created_by=created_by)
```

- [ ] **Step 4: 통과 확인** — 실DB 1 passed, skipped==0.
- [ ] **Step 5: 커밋** — `feat(ledger): Phase3 T2 record_specialist_result(_append_with_lineage 공개 래퍼)`

---

## Task 3: permit 구체 specialist + registry

**Files:** Create `apps/api/app/services/agents/registry.py` · Test `apps/api/tests/agents/test_registry.py`

`check_permit_feasibility`(순수·결정론)를 도구 어댑터로 감싸 permit SpecialistAgent 구성. registry로 도메인 조회.

- [ ] **Step 1: 실패 테스트**

```python
# tests/agents/test_registry.py
import pytest
from app.services.agents.registry import get_specialist, AVAILABLE_DOMAINS


def test_permit_domain_registered():
    assert "permit" in AVAILABLE_DOMAINS
    a = get_specialist("permit")
    assert a.domain == "permit" and a.analysis_type == "domain_agent_permit"


def test_unknown_domain_raises():
    with pytest.raises(KeyError):
        get_specialist("nonexistent")


async def test_permit_tool_is_deterministic_no_llm():
    # permit 도구는 check_permit_feasibility 기반 — 동일 입력 동일 findings(LLM 비개입)
    from app.services.agents.registry import _permit_tool
    o1 = _permit_tool({"dev_type": "다세대주택", "zone_type": "제2종일반주거지역"})
    o2 = _permit_tool({"dev_type": "다세대주택", "zone_type": "제2종일반주거지역"})
    assert o1 == o2 and o1["findings"][0]["check_id"] == "PERMIT"
    assert o1["findings"][0]["status"] in ("pass", "fail")
```

- [ ] **Step 2: 실패 확인** — FAIL(모듈 없음).
- [ ] **Step 3: 구현 `registry.py`** (실행 시 `check_permit_feasibility` 반환 키 정밀 확인: permit_validator.py:72 — `{is_permitted, permit_complexity, type_name, reason}`)

```python
"""Phase 3 — 도메인 → SpecialistAgent 레지스트리 + 계층1 결정론 도구 어댑터."""
from __future__ import annotations

from typing import Any

from app.services.agents.specialist_agent import SpecialistAgent


def _permit_tool(data: dict[str, Any]) -> dict[str, Any]:
    """계층1 결정론 인허가 가부 도구(check_permit_feasibility) → findings/summary."""
    from app.services.feasibility.permit_validator import check_permit_feasibility
    res = check_permit_feasibility(data.get("dev_type", ""), data.get("zone_type", ""))
    status = "pass" if res.get("is_permitted") else "fail"
    return {
        "findings": [{"check_id": "PERMIT", "status": status,
                      "current": res.get("type_name"), "limit": None,
                      "note": res.get("reason")}],
        "summary": {"is_permitted": res.get("is_permitted"),
                    "permit_complexity": res.get("permit_complexity"),
                    "type_name": res.get("type_name")},
    }


def _build_permit() -> SpecialistAgent:
    return SpecialistAgent(domain="permit", task_type="feasibility",
                           tool=_permit_tool, interpreter=None)


_FACTORIES = {"permit": _build_permit}
AVAILABLE_DOMAINS = tuple(_FACTORIES.keys())


def get_specialist(domain: str) -> SpecialistAgent:
    if domain not in _FACTORIES:
        raise KeyError(f"unknown specialist domain: {domain}")
    return _FACTORIES[domain]()
```

- [ ] **Step 4: 통과 확인** — `pytest tests/agents/test_registry.py -q` → 3 passed.
- [ ] **Step 5: 커밋** — `feat(agents): Phase3 T3 permit specialist + registry(check_permit_feasibility 도구)`

---

## Task 4: coordinator 실디스패치 (데드 스텁 격상)

**Files:** Modify `apps/api/core/coordinator.py` · Test `apps/api/tests/agents/test_coordinator_dispatch.py`

`coordinator.py:6-17`의 기존 `request_domain_agent`(stub, `pass`)·stub 테스트는 **불변 보존**(하위호환). **신규 `async dispatch(domain, data, **ctx)`** 메서드를 additive로 추가 — registry로 SpecialistAgent 조회·실행.

- [ ] **Step 1: 실패 테스트**

```python
# tests/agents/test_coordinator_dispatch.py
import pytest
from core.coordinator import AgentCoordinator


async def test_dispatch_runs_specialist_and_returns_ledger(monkeypatch):
    # registry/specialist를 가짜로 주입 — coordinator 디스패치 계약만 검증(무 DB)
    from app.services.agents import registry

    class _FakeAgent:
        domain, task_type, analysis_type = "permit", "feasibility", "domain_agent_permit"
        async def run(self, data, **kw):
            return {"domain": "permit", "findings": [{"check_id": "PERMIT", "status": "pass"}],
                    "ledger": {"ok": True, "content_hash": "h"}}
    monkeypatch.setattr(registry, "get_specialist", lambda d: _FakeAgent(), raising=True)

    coord = AgentCoordinator()
    out = await coord.dispatch("permit", {"dev_type": "다세대주택", "zone_type": "제2종일반주거지역"}, tenant_id="t", pnu="P1")
    assert out["domain"] == "permit" and out["ledger"]["ok"] is True


async def test_dispatch_unknown_domain_returns_error():
    coord = AgentCoordinator()
    out = await coord.dispatch("nonexistent", {})
    assert out["ok"] is False and "unknown" in out["message"].lower()
```

- [ ] **Step 2: 실패 확인** — FAIL(`dispatch` 없음).
- [ ] **Step 3: 구현(coordinator.py에 메서드 additive 추가 — 기존 `request_domain_agent` 불변)**

```python
    async def dispatch(self, domain: str, data: dict, **ctx) -> dict:
        """Phase 3: 도메인 → SpecialistAgent 디스패치(prior read+도구+citation_gate+원장 cite). W4.

        기존 request_domain_agent(stub)와 별개 경로(하위호환). 미등록 도메인은 정직 에러.
        """
        from app.services.agents.registry import get_specialist
        try:
            agent = get_specialist(domain)
        except KeyError as e:
            return {"ok": False, "message": f"unknown domain: {domain}", "detail": str(e)}
        result = await agent.run(data, **ctx)
        return {"ok": True, "domain": domain, **result}
```

> coordinator.py 상단 import 경로 확인: 기존 클래스가 `core.coordinator`인지 `apps.api.core.coordinator`인지 실행 시 확인(이중 import 루트 — 테스트 import도 정합 맞춤).

- [ ] **Step 4: 통과 확인** — `pytest tests/agents/test_coordinator_dispatch.py -q` → 2 passed. **+회귀** `pytest tests/test_core_modules.py -q`(기존 stub 테스트 불변 통과).
- [ ] **Step 5: 커밋** — `feat(core): Phase3 T4 coordinator.dispatch 실구현(registry 디스패치, stub 불변)`

---

## Task 5: e2e — W4 닫힘 (실 DB, 결정론, skipped==0)

**Files:** Modify `apps/api/tests/agents/test_phase3_e2e.py`

coordinator.dispatch("permit", ...) → SpecialistAgent → 계층1 도구 → 원장 cite. 2회차 모순+lineage, 무결성 불변.

- [ ] **Step 1: e2e 테스트 추가**

```python
async def test_w4_closed_specialist_dispatch_cites_ledger_with_lineage():
    if not await _db():
        pytest.skip("DB 미가용")
    import uuid
    from core.coordinator import AgentCoordinator
    from app.services.ledger import analysis_ledger_service as ledger, lineage
    tid, pnu = f"t-p3e2e-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    coord = AgentCoordinator()
    try:
        # 1회차: 허용 용도 → pass
        r1 = await coord.dispatch("permit", {"dev_type": "다세대주택", "zone_type": "제2종일반주거지역"},
                                  tenant_id=tid, pnu=pnu)
        assert r1["ok"] and r1["ledger"]["ok"]
        # 2회차: 불허 용도 → fail (status flip 모순 + lineage)
        r2 = await coord.dispatch("permit", {"dev_type": "공장", "zone_type": "제2종일반주거지역"},
                                  tenant_id=tid, pnu=pnu)
        assert r2["contradictions"]["has_contradiction"] is True
        latest = await ledger.get_latest(analysis_type="domain_agent_permit", tenant_id=tid, pnu=pnu)
        parents = await lineage.get_parents(child_hash=latest["content_hash"], tenant_id=tid)
        assert parents                       # W4: 계층3가 원장에 cite + 파생 엣지
        # 무결성 불변
        vr = await ledger.verify_chain(analysis_type="domain_agent_permit", tenant_id=tid, pnu=pnu)
        assert vr["verified"] is True
    finally:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM analysis_lineage WHERE tenant_id=:t"), {"t": tid})
            await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id=:t"), {"t": tid})
            await db.commit()
```

> ⚠️ 실행 시 `check_permit_feasibility`가 "공장"/"다세대주택"·"제2종일반주거지역"에 대해 실제 pass/fail을 주는지 ZONE_PERMIT_MATRIX(permit_validator.py:6) 확인 후 dev_type 값 보정(결정론 결과에 맞춰 테스트 입력 선택).

- [ ] **Step 2: 전체 게이트** — `pytest tests/agents tests/ledger -q -rs` → all passed, **skipped==0**.
- [ ] **Step 3: 회귀** — `pytest tests/test_core_modules.py tests/integration -q -rs`(coordinator stub·Phase1 성장루프 불변).
- [ ] **Step 4: 커밋 + push** — `test(agents): Phase3 T5 e2e W4 닫힘(coordinator→specialist→원장 lineage) + skipped==0`, `git push`(머지·배포 보류).

---

## Self-Review
- **Spec coverage:** SpecialistAgent(계층1 도구+citation_gate grounded, T1/T3) ✅ · coordinator 실디스패치(데드 스텁 격상, T4) ✅ · W4 닫기(계층3→원장 cite+lineage+contradiction, T2/T5) ✅ · 결정론 코어 불변(수치=도구만, LLM=citation_gate enforce, T1 테스트) ✅ · expert_panel ROSTER는 후속(미니멀 슬라이스엔 미포함 — gaps에 명시).
- **Placeholder scan:** T1~T4 완전 코드. T3 `_permit_tool`·T5 입력값은 `check_permit_feasibility`/`ZONE_PERMIT_MATRIX` 실반환 확인 후 보정(서비스 정밀 미독 구간의 정직 표기, 실행 시 grep).
- **Type consistency:** `SpecialistAgent(domain,task_type,tool,interpreter,recorder,prior_loader).run(data,*,tenant_id,...)` 전 Task 일치. `record_specialist_result(*,analysis_type,payload,...)` ← `_append_with_lineage`(Phase2). `get_specialist(domain)->SpecialistAgent` / `AgentCoordinator.dispatch(domain,data,**ctx)`.
- **범위 메모(후속 Phase 3.2 후보):** 다수 도메인 specialist(market/feasibility/cost…), expert_panel ROSTER 토론 통합, domain_agents_service에 SpecialistAgent 경로 합류, 라우터 엔드포인트 마운트(현재 coordinator.dispatch는 서비스레벨), output_summary_json findings 보존.
