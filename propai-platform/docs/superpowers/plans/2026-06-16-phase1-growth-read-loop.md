# Phase 1 — 원장 read 성장루프 (쌓일수록 정확해지는 피드백) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 원장(analysis_ledger SSOT)에 누적된 직전 분석을 `prior_context`로 다시 read하여 다음 분석의 근거에 additive로 주입하고, citation_gate가 prior 근거를 인정하게 함으로써 "쌓일수록 정확해지는" 성장 피드백 루프를 닫는다. **결정론 코어의 판정·수치는 절대 바꾸지 않는다(read는 비교·근거 표면화 전용).**

**Architecture:** Phase 0가 깐 write·무결성·페이로드 규약(`schema_version`+`kind`+`findings_brief`+backlink) 위에서, (1) read 진입점은 기존 `analysis_ledger_service.get_latest`(신규 read 서비스 불필요), (2) 모든 LLM 인터프리터의 단일 합류점 `BaseInterpreter._invoke`에 `prior_context` 근거블록을 additive 주입(9개 인터프리터 동시 적용), (3) 결정론 `citation_gate`에 `prior_evidence`를 합쳐 prior 수치/법조문을 grounded로 인정, (4) 분석 서비스 진입부(comprehensive/design_audit/feasibility)에서 prior read→주입→write-back을 best-effort로 배선. W1 미배선(pricing/cost)도 SSOT에 합류시킨다.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async(asyncpg), structlog, pytest + pytest-asyncio(1.4.0), Postgres(PostGIS, infra/docker-compose.yml host 5444). 테스트는 Phase 0의 skip-if-unavailable Postgres 픽스처 재사용. LLM 호출은 fake/mock로 결정론 단위테스트.

**불변규칙(전 Task 준수):** additive·하위호환(기존 호출부 무변동), 결정론 코어 불변(verdict/counts/engines/수치 미변경), LLM 수치 비생성(citation_gate enforce), 정직표기(prior 부재/DB오류 시 `skipped`·`None` 폴백, silent failure 금지→logger.warning), 멱등(동일 payload는 `unchanged`). 커밋 footer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

**실행 환경 전제:** 테스트 명령은 `apps/api`에서 실행. DB 통합테스트는 `infra/docker-compose.yml`의 Postgres 기동(host 5444) + `export DATABASE_URL='postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db'` + `alembic upgrade head` 후. 캐시 격리: `export INTERP_REDIS_CACHE=0`. 미기동 시 DB 통합테스트는 자동 skip(픽스처) — 단 **Task 8에서 `skipped==0` 강제**(skip≠검증).

---

## File Structure

**신규(focused, 단일책임):**
- `apps/api/app/services/ledger/prior_context.py` — 성장루프 read SSOT. `load_prior()`(get_latest best-effort 래퍼), `build_prior_block()`(payload→인터프리터 근거블록+모순명시 규칙), `prior_numbers()`(citation_gate용 수치 추출). 읽기·포맷 한 가지 책임.
- 테스트: `apps/api/tests/ledger/test_prior_context.py`, `apps/api/tests/ai/test_base_interpreter_prior.py`, `apps/api/tests/design_audit/test_citation_gate_prior.py`, `apps/api/tests/ledger/test_pricing_cost_adapters.py`, `apps/api/tests/integration/test_*_growth_loop.py`, `apps/api/tests/integration/test_growth_loop_e2e.py`.

**수정(additive only):**
- `apps/api/app/services/ai/base_interpreter.py` — `_invoke`에 `prior_context` 키워드 + evidences/캐시키 배선(9 인터프리터 공통).
- `apps/api/app/services/design_audit/blindspot_interpreter.py` — `citation_gate`에 `prior_evidence` 선택 인자.
- `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py` + `apps/api/app/routers/comprehensive_analysis.py` — read→주입→write-back.
- `apps/api/app/services/design_audit/design_audit_orchestrator.py` + `apps/api/app/routers/design_audit.py` — `prior_context` 패스스루 + `prior_comparison` 섹션.
- `apps/api/app/services/ledger/ledger_adapters.py` — feasibility/pricing/cost 매퍼+래퍼 신규.
- `apps/api/app/routers/v2_feasibility.py`, `apps/api/app/api/endpoints/sales/actions.py`, `apps/api/app/routers/cost.py` — write 배선.

---

## Task 0: Phase 1 브랜치·환경 점검 (게이트)

**Files:** 없음(검증만).

- [ ] **Step 1: 브랜치·환경 확인**

Run:
```bash
cd apps/api && git -C .. rev-parse --abbrev-ref HEAD
.venv/bin/python -c "import pytest_asyncio, structlog, sqlalchemy; print('deps OK')"
.venv/bin/python -c "from app.services.ledger import analysis_ledger_service as l; print('ledger import OK', bool(l.get_latest))"
```
Expected: 브랜치 `feature/trust-infra-2026-06-11`, `deps OK`, `ledger import OK True`.

- [ ] **Step 2: DB 가용성 확인(없으면 통합테스트 skip 모드로 진행)**

Run:
```bash
.venv/bin/python -c "import asyncio,os; from sqlalchemy import text; from sqlalchemy.ext.asyncio import create_async_engine; \
url=os.environ.get('DATABASE_URL','postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db'); \
asyncio.run((lambda e: e.dispose())(create_async_engine(url))); print('engine ok (연결은 통합테스트에서)')"
```
Expected: `engine ok`. (실제 연결 실패는 통합테스트 skip으로 처리 — Task 8 게이트에서 강제 확인.)

---

## Task 1: prior_context 모듈 — read SSOT + 근거블록 포맷

**Files:**
- Create: `apps/api/app/services/ledger/prior_context.py`
- Test: `apps/api/tests/ledger/test_prior_context.py`

- [ ] **Step 1: 실패 테스트 작성(순수 — DB·LLM 불필요)**

`apps/api/tests/ledger/test_prior_context.py`:
```python
"""Phase 1: prior_context 근거블록 포맷·수치추출 단위테스트(순수)."""
from app.services.ledger.prior_context import build_prior_block, prior_numbers


def _prior():
    return {
        "analysis_type": "design_audit",
        "version": 3,
        "content_hash": "abc123",
        "created_at": "2026-06-10 09:00:00",
        "payload": {
            "kind": "design_audit", "schema_version": "design_audit/v1",
            "verdict": "conditional", "counts": {"fail": 1, "warn": 2},
            "findings_brief": [
                {"check_id": "FAR-01", "status": "fail", "current": 250.0, "limit": 200.0},
                {"check_id": "BCR-02", "status": "pass", "current": 55.0, "limit": 60.0},
            ],
        },
    }


def test_build_prior_block_includes_version_and_contradiction_rule():
    block = build_prior_block(_prior())
    assert "이전 분석" in block
    assert "v3" in block  # 버전 표면화
    assert "design_audit" in block
    assert "FAR-01" in block and "250" in block  # 비교 핵심(findings_brief)
    # 모순명시 규칙(spec: 이전결론 모순 시 명시)
    assert "모순" in block


def test_build_prior_block_none_returns_empty():
    assert build_prior_block(None) == ""
    assert build_prior_block({}) == ""


def test_prior_numbers_extracts_findings_values():
    nums = prior_numbers(_prior())
    assert 250.0 in nums and 200.0 in nums and 55.0 in nums and 60.0 in nums
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ledger/test_prior_context.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.ledger.prior_context`.

- [ ] **Step 3: 모듈 구현**

`apps/api/app/services/ledger/prior_context.py`:
```python
"""Phase 1 성장루프 read SSOT — 원장 prior를 read하고 인터프리터 근거블록으로 포맷한다.

읽기·포맷 한 가지 책임. 결정론 판정/수치는 절대 만들지 않는다(비교·근거 표면화 전용).
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def load_prior(
    *, analysis_type: str, tenant_id: str | None = None,
    pnu: str | None = None, address: str | None = None, project_id: str | None = None,
) -> dict[str, Any] | None:
    """동일 체인의 직전 분석을 best-effort로 회수. DB 부재/오류 시 None(분석 무중단)."""
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        return await ledger.get_latest(
            analysis_type=analysis_type, tenant_id=tenant_id,
            pnu=pnu, address=address, project_id=project_id,
        )
    except Exception as e:  # noqa: BLE001 — read 실패는 분석을 막지 않음(정직 degrade)
        logger.warning("prior_context read 실패 — prior 없이 진행", analysis_type=analysis_type, err=str(e)[:160])
        return None


def prior_numbers(prior: dict[str, Any] | None) -> list[float]:
    """citation_gate grounded corpus용 — prior payload의 수치를 평탄 추출."""
    out: list[float] = []
    if not prior:
        return out
    payload = prior.get("payload") or {}

    def _walk(obj: Any) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            out.append(float(obj))
        elif isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                _walk(v)

    _walk(payload)
    return out


def build_prior_block(prior: dict[str, Any] | None) -> str:
    """prior payload → 인터프리터 프롬프트 말미에 붙일 근거블록(+모순명시 규칙).

    spec: prior_context 근거블록 + '이전결론 모순 시 명시'. 결정론 비교핵심(findings_brief/
    verdict/counts)만 표면화하고 LLM이 새 수치를 만들지 않도록 지시한다.
    """
    if not prior or not prior.get("payload"):
        return ""
    payload = prior["payload"]
    version = prior.get("version")
    atype = prior.get("analysis_type") or payload.get("kind") or "분석"
    created = prior.get("created_at") or ""
    lines: list[str] = [
        f"## 이전 분석 기록(원장 prior · {atype} v{version} · {created})",
        "아래는 같은 대상의 직전 분석 결과다. 이번 분석은 이 기록을 참고하되, "
        "**제공된 현재 데이터에서만 수치를 인용**하고 새 수치를 만들지 마라. "
        "**이번 결론이 이전 결론과 모순되면 그 사실과 사유를 명시**하라.",
    ]
    if payload.get("verdict") is not None:
        lines.append(f"- 이전 종합판정: {payload.get('verdict')} / counts: {payload.get('counts') or {}}")
    brief = payload.get("findings_brief") or []
    if brief:
        lines.append("- 이전 주요 항목(check_id·status·current/limit):")
        for f in brief[:12]:
            lines.append(
                f"  - {f.get('check_id')}: {f.get('status')} "
                f"(current={f.get('current')}, limit={f.get('limit')})"
            )
    # 재무/원가 요약(summary·total_revenue_10k 등)도 있으면 표면화
    for k in ("summary", "total_revenue_10k", "net_profit_won", "grade"):
        if k in payload:
            lines.append(f"- 이전 {k}: {payload.get(k)}")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ledger/test_prior_context.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: 커밋**

```bash
git add apps/api/app/services/ledger/prior_context.py apps/api/tests/ledger/test_prior_context.py
git commit -m "feat(phase1): prior_context read SSOT — load_prior + build_prior_block + prior_numbers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: BaseInterpreter._invoke — prior_context 근거블록 additive 주입(9 인터프리터 공통)

**Files:**
- Modify: `apps/api/app/services/ai/base_interpreter.py:282`(_invoke 시그니처), `:300-309`(캐시키), `:321-332`(evidences)
- Test: `apps/api/tests/ai/test_base_interpreter_prior.py`

- [ ] **Step 1: 실패 테스트 작성(LLM mock — DB 불필요)**

`apps/api/tests/ai/test_base_interpreter_prior.py`:
```python
"""Phase 1: _invoke prior_context가 프롬프트에 부착되고 캐시키를 분리하는지(LLM mock)."""
import pytest

from app.services.ai.base_interpreter import BaseInterpreter


class _Probe(BaseInterpreter):
    name = "probe"
    expected_keys = ("text",)
    fallback_key = "text"
    max_tokens = 256
    system_prompt = "test"


@pytest.mark.asyncio
async def test_prior_context_appended_to_prompt(monkeypatch):
    captured = {}

    async def _fake_call(self, user_prompt, **kw):
        captured["prompt"] = user_prompt
        return {"text": "ok"}

    monkeypatch.setattr(BaseInterpreter, "_call_llm", _fake_call, raising=False)
    monkeypatch.setenv("INTERP_REDIS_CACHE", "0")
    itp = _Probe()
    await itp._invoke("BASE PROMPT", cache_data=None, prior_context="## 이전 분석 기록 v2\n- FAR-01: fail")
    assert "이전 분석 기록" in captured["prompt"]
    assert "FAR-01" in captured["prompt"]


@pytest.mark.asyncio
async def test_prior_context_separates_cache_key(monkeypatch):
    monkeypatch.setenv("INTERP_REDIS_CACHE", "0")
    itp = _Probe()
    k_no = itp._cache_key({"_data": {"x": 1}})
    # prior가 있으면 cache_data가 묶여 키가 달라져야 함(stale 캐시 미반환)
    k_prior = itp._cache_key({"_data": {"_data": {"x": 1}, "_prior": "v2"}})
    assert k_no != k_prior
```
> 주의: `_call_llm` 실제 메서드명은 구현부에서 LLM 호출을 감싸는 메서드다. base_interpreter.py에서 `_get_llm`/실호출 지점을 확인해 monkeypatch 대상명을 일치시킨다(실패 시 테스트가 `AttributeError`로 즉시 드러남).

- [ ] **Step 2: 실패 확인**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ai/test_base_interpreter_prior.py -q`
Expected: FAIL — `_invoke() got an unexpected keyword argument 'prior_context'`.

- [ ] **Step 3: 구현 — _invoke 시그니처 + 캐시키 + evidences(additive)**

`base_interpreter.py` `_invoke` 시그니처(현재 `:282`)에 `prior_context` 키워드 추가:
```python
    async def _invoke(
        self, user_prompt: str, *, cache_data: Any = None,
        evidence_data: dict | None = None, evidence_text: str | None = None,
        prior_context: str | None = None,   # Phase 1: 원장 prior 근거블록(additive)
    ) -> dict[str, str]:
```

캐시키 블록(현재 `:300-305`, evidence_text/_retry 패턴 바로 뒤)에 추가:
```python
        # Phase 1: prior_context도 결과를 바꾸므로 캐시키에 포함(prior 다르면 캐시 분리).
        if cache_data is not None and prior_context:
            cache_data = {"_data": cache_data, "_prior": prior_context}
```

evidences 결합 블록(현재 `:321-332`, `if evidence_text: evidences.append(evidence_text)` 바로 뒤)에 추가:
```python
        if prior_context:
            evidences.append(prior_context)
```
> 이후 기존 `if evidences: joined = "\n".join(evidences); user_prompt = f"{user_prompt}\n\n## 추가 근거 자료\n{joined}"` 로직이 prior_context를 그대로 프롬프트에 포함한다. 기존 호출부는 `prior_context` 미지정→None→무변동(비파괴).

- [ ] **Step 4: 통과 확인**

Run: `cd apps/api && INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ai/test_base_interpreter_prior.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: 회귀 확인(기존 인터프리터 무변동)**

Run: `cd apps/api && .venv/bin/python -m py_compile app/services/ai/base_interpreter.py && echo OK`
Expected: `OK`.

- [ ] **Step 6: 커밋**

```bash
git add apps/api/app/services/ai/base_interpreter.py apps/api/tests/ai/test_base_interpreter_prior.py
git commit -m "feat(phase1): BaseInterpreter._invoke prior_context 근거블록 additive 주입(9 인터프리터 공통)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: citation_gate — prior_evidence 합류(결정론 게이트가 prior 수치/법조문 인정)

**Files:**
- Modify: `apps/api/app/services/design_audit/blindspot_interpreter.py:256`(citation_gate 시그니처), `:280-285`(evidence corpus), `:480`(호출처)
- Test: `apps/api/tests/design_audit/test_citation_gate_prior.py`

- [ ] **Step 1: 실패 테스트 작성(순수 — DB·LLM 불필요)**

`apps/api/tests/design_audit/test_citation_gate_prior.py`:
```python
"""Phase 1: citation_gate가 prior_evidence의 수치를 grounded로 인정(치환 안 함)."""
from app.services.design_audit.blindspot_interpreter import citation_gate


def test_prior_number_is_grounded_not_gated():
    # findings엔 없지만 prior 원장엔 있는 수치(250.0)를 인용하면, prior_evidence 합류 시 치환되지 않아야.
    items = [{"claim": "용적률이 250.0%로 한도를 초과합니다", "basis": "FAR-01", "confidence": "high"}]
    findings = [{"check_id": "FAR-01", "status": "fail"}]  # 수치 없음
    prior = {"payload": {"findings_brief": [{"check_id": "FAR-01", "current": 250.0, "limit": 200.0}]}}

    without = citation_gate(items, findings, None)
    with_prior = citation_gate(items, findings, None, prior_evidence=prior)

    # prior 없으면 250.0이 미근거로 치환(gated)
    assert without[0]["citation_gate"]["gated"] is True
    # prior 합류 시 grounded → 치환 안 됨
    assert with_prior[0]["citation_gate"]["gated"] is False
    assert "250" in with_prior[0]["claim"]


def test_backward_compatible_two_three_args():
    items = [{"claim": "면적 검토", "basis": "AREA-01", "confidence": "medium"}]
    findings = [{"check_id": "AREA-01", "status": "pass"}]
    # 기존 2~3인자 호출 무변동(prior_evidence 기본 None)
    assert citation_gate(items, findings) == citation_gate(items, findings, None)
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/design_audit/test_citation_gate_prior.py -q`
Expected: FAIL — `citation_gate() got an unexpected keyword argument 'prior_evidence'`.

- [ ] **Step 3: 구현 — prior_evidence 선택 인자(결정론·순수 유지)**

`blindspot_interpreter.py` `citation_gate` 시그니처(현재 `:256`):
```python
def citation_gate(
    items: list[dict[str, str]], findings: Any, derived_signals: Any = None,
    *, prior_evidence: Any = None,   # Phase 1: 원장 prior payload(grounded corpus 합류)
) -> list[dict[str, Any]]:
```

evidence corpus 구성부(현재 `:280-285`, `_walk_numbers(derived_signals, evidence_numbers)` 직후)에 추가:
```python
    if prior_evidence is not None:
        from app.services.ledger.prior_context import prior_numbers
        for n in prior_numbers(prior_evidence):
            evidence_numbers.add(n)
        # 법조문 본문 corpus에도 prior payload를 합쳐 prior 인용 법조문을 grounded로 인정
        evidence_norm = _norm_law(
            evidence_norm + json.dumps(prior_evidence.get("payload", prior_evidence), ensure_ascii=False, default=str)
        )
```
> `evidence_numbers`/`evidence_norm`은 현재 `:280-285`에서 정의된 지역변수. 위 블록을 그 정의 직후에 둔다. `prior_numbers`는 Task 1 모듈. 기본값 None이라 기존 호출 전부 무변동, 순수 함수·결정론 유지.

호출처(현재 `:480`, `generate_blindspot` 내부)는 Task 5에서 prior 배선 시 수정한다. 본 Task에서는 호출처 변경 없음(테스트는 함수 직접 호출).

- [ ] **Step 4: 통과 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/design_audit/test_citation_gate_prior.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: 기존 citation_gate 회귀 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ -k citation -q`
Expected: 기존 citation 테스트 PASS(변동 없음).

- [ ] **Step 6: 커밋**

```bash
git add apps/api/app/services/design_audit/blindspot_interpreter.py apps/api/tests/design_audit/test_citation_gate_prior.py
git commit -m "feat(phase1): citation_gate prior_evidence 합류 — prior 원장 수치/법조문 grounded 인정(결정론·additive)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: comprehensive_analysis 성장루프 (read prior → 주입 → write-back) ★flagship

**Files:**
- Modify: `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py:129`(analyze 시그니처+read/write), `apps/api/app/routers/comprehensive_analysis.py:14,27`(handler current_user + project_id)
- Test: `apps/api/tests/integration/test_comprehensive_growth_loop.py`(DB)

- [ ] **Step 1: 실패 통합테스트 작성(DB 픽스처 — 미가용 시 skip)**

`apps/api/tests/integration/test_comprehensive_growth_loop.py`:
```python
"""Phase 1: 종합분석 성장루프 — 2회차가 1회차 원장 prior를 읽어 주입하고, 새 버전을 write한다."""
import os
import pytest

pytestmark = pytest.mark.asyncio

_DB = os.environ.get("DATABASE_URL", "")


async def _db_available() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_second_analysis_reads_prior_and_writes_new_version(monkeypatch):
    if not await _db_available():
        pytest.skip("DB 미가용 — Postgres(5444) 기동 후 실행(skip≠검증, Task8 게이트)")
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService

    addr = "의정부동 224"
    tid = "t-phase1-test"
    # 외부 의존(land_info/LLM)을 결정론 스텁으로 고정
    svc = ComprehensiveAnalysisService()

    async def _fake_collect(self, address, pnu=None):
        return {"pnu": "1115010300102240000", "zone_type": "제2종일반주거지역", "land_area_sqm": 300.0}
    monkeypatch.setattr(type(svc.land_info), "collect_comprehensive", _fake_collect, raising=True)

    # 1회차
    r1 = await svc.analyze(addr, tenant_id=tid, project_id=None)
    # 1회차 직후 원장에 site_analysis가 write됐는지(write-back)
    prior = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                    pnu="1115010300102240000", address=addr, project_id=None)
    assert prior is not None and prior["version"] >= 1

    # 2회차 — prior가 분석에 주입되고 새 버전 write
    r2 = await svc.analyze(addr, tenant_id=tid, project_id=None)
    assert "prior_analysis" in r2  # read-only 첨부(주입 증거)
    after = await ledger.get_latest(analysis_type="site_analysis", tenant_id=tid,
                                    pnu="1115010300102240000", address=addr, project_id=None)
    assert after["version"] >= prior["version"]  # 멱등이면 동일, 변경이면 +1
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/api && DATABASE_URL=postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/integration/test_comprehensive_growth_loop.py -q -rs`
Expected: FAIL(`analyze() got an unexpected keyword argument 'tenant_id'`) 또는 DB 미가용 시 SKIP.

- [ ] **Step 3: 구현 — analyze() read→주입→write-back(additive·best-effort)**

`comprehensive_analysis_service.py` `analyze` 시그니처(현재 `:129`)에 keyword-only 추가:
```python
    async def analyze(
        self, address: str, llm_provider: str | None = None, llm_model: str | None = None,
        *, tenant_id: str | None = None, project_id: str | None = None,
    ) -> dict[str, Any]:
```

`base = await self.land_info.collect_comprehensive(address)`(현재 `:143`) 직후에 prior read:
```python
        # Phase 1: 직전 분석 prior read(best-effort, 없으면 None — 무중단)
        from app.services.ledger.prior_context import load_prior, build_prior_block
        _pnu = base.get("pnu")
        prior = await load_prior(
            analysis_type="site_analysis", tenant_id=tenant_id,
            pnu=_pnu, address=address, project_id=project_id,
        )
        prior_block = build_prior_block(prior)
```
> 인터프리터 호출 지점(analyze 내부에서 `ai_interpretation`/`market_interpretation`을 만드는 곳)이 `generate_interpretation(...)`을 호출할 때 `prior_context=prior_block`(또는 베이스 `_invoke(..., prior_context=prior_block)` 경로)을 전달한다. 인터프리터 진입 함수가 `**kwargs`를 받지 않으면 해당 인터프리터의 `generate_*`에 `prior_context: str | None = None`을 additive로 추가한 뒤 `self._invoke(..., prior_context=prior_context)`로 패스스루(Task 2 경로 재사용).

`analyze` 반환 직전(result dict 완성 후, 현재 `:240` 부근 `return result`)에 prior 첨부 + write-back:
```python
        # Phase 1: prior를 read-only로 첨부(주입 증거·프론트 표면화), 기존 키 미변경
        result["prior_analysis"] = prior  # None이면 None(정직)
        # write-back: 이번 분석을 원장에 best-effort 적재(다음 회차의 prior가 됨)
        from app.services.ledger import analysis_ledger_service as ledger
        await ledger.append_analysis(
            analysis_type="site_analysis",
            payload={
                "kind": "site_analysis", "schema_version": "site_analysis/v1",
                "zone_type": result.get("zone_type"), "effective_far": result.get("effective_far"),
                "land_area_sqm": result.get("land_area_sqm"),
                "potential_far_range": result.get("potential_far_range"),
                "findings_brief": [
                    {"check_id": "ZONE", "status": "info", "current": result.get("effective_far"), "limit": None},
                ],
            },
            tenant_id=tenant_id, pnu=_pnu, address=address, project_id=project_id,
            source="comprehensive", created_by=None,
        )
        return result
```
> `append_analysis`는 내부 try/except로 `{ok:False,...}` 폴백(분석 무중단). 멱등이라 동일 입력 재실행은 `unchanged`. **결정론 수치는 result에서 그대로 인용**(LLM 생성 아님).

`comprehensive_analysis.py` 핸들러(현재 `:27`)가 current_user→tenant_id 배선:
```python
class ComprehensiveAnalysisRequest(BaseModel):
    address: str = Field(..., description="분석 대상 주소")
    llm_provider: str | None = Field(None, description="LLM 프로바이더 ...")
    llm_model: str | None = Field(None, description="LLM 모델 ID ...")
    project_id: str | None = Field(None, description="프로젝트 ID(원장 체인 스코프)")  # Phase 1 additive


@router.post("/comprehensive")
async def run_comprehensive_analysis(req: ComprehensiveAnalysisRequest, current_user=Depends(get_current_user)):
    from app.services.land_intelligence.comprehensive_analysis_service import ComprehensiveAnalysisService
    service = ComprehensiveAnalysisService()
    return await service.analyze(
        address=req.address, llm_provider=req.llm_provider, llm_model=req.llm_model,
        tenant_id=str(getattr(current_user, "tenant_id", "") or "") or None,
        project_id=req.project_id,
    )
```
> `get_current_user`는 이미 `comprehensive_analysis.py:10`에 import됨(라우터 레벨 의존성). 핸들러 인자로 받도록만 변경. 다른 호출부 `project_pipeline.py:684 comp_svc.analyze(state.address)`는 keyword-only 기본값으로 무영향.

- [ ] **Step 4: 통과 확인**

Run: `cd apps/api && DATABASE_URL=postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/integration/test_comprehensive_growth_loop.py -q -rs`
Expected: PASS(DB 가용 시) 또는 SKIP(미가용).

- [ ] **Step 5: 커밋**

```bash
git add apps/api/app/services/land_intelligence/comprehensive_analysis_service.py apps/api/app/routers/comprehensive_analysis.py apps/api/tests/integration/test_comprehensive_growth_loop.py
git commit -m "feat(phase1): comprehensive_analysis 성장루프 — prior read 주입 + write-back(site_analysis)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: design_audit 성장루프 (read prior → prior_comparison 섹션, verdict 불변)

**Files:**
- Modify: `apps/api/app/services/design_audit/design_audit_orchestrator.py:215,354`(audit/run prior_context 키워드 + _compare_with_prior), `apps/api/app/routers/design_audit.py:318`(_execute_run read 주입 + citation_gate prior 배선)
- Test: `apps/api/tests/integration/test_design_audit_growth_loop.py`(DB)

- [ ] **Step 1: 실패 테스트 작성(orchestrator 단위 — DB 불필요)**

`apps/api/tests/integration/test_design_audit_growth_loop.py`:
```python
"""Phase 1: design_audit가 prior_context를 받아 sections.prior_comparison을 가산하되 verdict는 불변."""
import pytest

pytestmark = pytest.mark.asyncio


async def test_prior_comparison_added_without_changing_verdict():
    from app.services.design_audit.design_audit_orchestrator import DesignAuditOrchestrator
    orch = DesignAuditOrchestrator()
    params = {"zone_type": "제2종일반주거지역", "site_area": 300.0, "gfa": 600.0}

    base = await orch.audit(params, zone_type="제2종일반주거지역")
    prior = {"payload": {"verdict": "fail", "findings_brief": [
        {"check_id": "FAR-01", "status": "fail", "current": 999.0, "limit": 200.0}]}}
    withp = await orch.audit(params, zone_type="제2종일반주거지역", prior_context=prior)

    # verdict·counts·engines 결정론 불변(read는 비교표면화 전용)
    assert withp["overall"]["verdict"] == base["overall"]["verdict"]
    assert withp["overall"].get("counts") == base["overall"].get("counts")
    # prior_comparison 섹션만 additive 가산
    assert "prior_comparison" in withp.get("sections", {})
    assert "prior_comparison" not in base.get("sections", {})


async def test_audit_without_prior_unchanged():
    from app.services.design_audit.design_audit_orchestrator import DesignAuditOrchestrator
    orch = DesignAuditOrchestrator()
    params = {"zone_type": "제2종일반주거지역", "site_area": 300.0, "gfa": 600.0}
    a = await orch.audit(params, zone_type="제2종일반주거지역")
    assert "prior_comparison" not in a.get("sections", {})  # 미제공 시 무변동
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/integration/test_design_audit_growth_loop.py -q`
Expected: FAIL — `audit() got an unexpected keyword argument 'prior_context'`.

- [ ] **Step 3: 구현 — run/audit prior_context 패스스루 + _compare_with_prior**

`design_audit_orchestrator.py` `audit` 시그니처(현재 `:215`)에 keyword 추가:
```python
    async def audit(
        self, params: dict[str, Any] | None, *, zone_type: str | None = None,
        sigungu: str | None = None, address: str | None = None, pnu: str | None = None,
        shapes: dict[str, Any] | None = None, regulation_payload: Any = None,
        plan_payload: Any = None, case_service: Any = None,
        rooms: list[dict[str, Any]] | None = None, prior_context: dict | None = None,
    ) -> dict[str, Any]:
```

`audit` 반환 직전(현재 `:329` `return` 직전, sections 조립 후)에 비교섹션 가산:
```python
        # Phase 1: prior 비교 — verdict/counts/engines 결정론 결과는 절대 미변경, sections만 가산
        if prior_context:
            result.setdefault("sections", {})["prior_comparison"] = _compare_with_prior(
                prior_context, result.get("findings") or []
            )
```

모듈 레벨 헬퍼 추가(순수·결정론):
```python
def _compare_with_prior(prior: dict, findings: list[dict]) -> dict:
    """prior findings_brief vs 현재 findings의 status/수치 델타(표면화 전용, 판정 미반영)."""
    payload = (prior or {}).get("payload") or {}
    prev = {f.get("check_id"): f for f in (payload.get("findings_brief") or [])}
    cur = {f.get("check_id"): f for f in findings}
    changes = []
    for cid, c in cur.items():
        p = prev.get(cid)
        if p and p.get("status") != c.get("status"):
            changes.append({"check_id": cid, "prev_status": p.get("status"), "now_status": c.get("status")})
    return {
        "prior_version": prior.get("version"),
        "prior_verdict": payload.get("verdict"),
        "status_changes": changes,
        "note": "이전 대비 상태 변화(참고용) — 종합판정은 현재 결정론 결과를 따른다",
    }
```

`run` 시그니처(현재 `:354`)에 `prior_context: dict | None = None` 추가하고, `audit` 호출(현재 `:399`)에 패스스루:
```python
        result = await self.audit(
            merged_params, zone_type=site.get("zone_type"), sigungu=site.get("sigungu"),
            address=site.get("address"), pnu=site.get("pnu"), shapes=geometry, rooms=rooms,
            prior_context=prior_context,
        )
```

`design_audit.py` `_execute_run`의 `orchestrator.run(db, **run_kwargs)`(현재 `:318`) 직전에 read 주입:
```python
    # Phase 1: 직전 design_audit prior read(best-effort, 없으면 None)
    from app.services.ledger.prior_context import load_prior
    _prior = await load_prior(
        analysis_type="design_audit",
        tenant_id=str(getattr(current, "tenant_id", "") or "") or None,
        project_id=req.project_id,
        address=req.site.get("address") if isinstance(req.site, dict) else None,
        pnu=req.site.get("pnu") if isinstance(req.site, dict) else None,
    )
    if _prior:
        run_kwargs["prior_context"] = _prior
```
> write(`record_design_audit`, `:382`)는 변경 없음(read와 동일 체인키=project_id+tenant). 두 진입점(/run·/run-upload)이 `_execute_run` 단일지점이라 한 곳 수정으로 양쪽 커버.

- [ ] **Step 4: 통과 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/integration/test_design_audit_growth_loop.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: verdict 결정론 회귀 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ -k "design_audit and verdict" -q`
Expected: 기존 verdict 테스트 PASS(불변).

- [ ] **Step 6: 커밋**

```bash
git add apps/api/app/services/design_audit/design_audit_orchestrator.py apps/api/app/routers/design_audit.py apps/api/tests/integration/test_design_audit_growth_loop.py
git commit -m "feat(phase1): design_audit 성장루프 — prior read 주입 + prior_comparison 섹션(verdict 결정론 불변)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: feasibility 성장루프 ('feasibility' write+read 쌍 신설)

**Files:**
- Modify: `apps/api/app/services/ledger/ledger_adapters.py`(feasibility_result_to_ledger + record_feasibility_result, analysis_type='feasibility'), `apps/api/app/routers/v2_feasibility.py:861`(vcs_commit: prior read + result write)
- Test: `apps/api/tests/ledger/test_feasibility_result_adapter.py` + `apps/api/tests/integration/test_feasibility_growth_loop.py`

> **배경(그라운딩 G4):** 기존 write는 `analysis_type='feasibility_vcs'`(VCS 커밋 메타). read 성장루프 재무키 `'feasibility'`로는 write하는 코드가 전무 → 항상 None. 따라서 **실제 수지 결과를 'feasibility'로 write하는 짝을 신설**한다(VCS 메타와 분리·비충돌).

- [ ] **Step 1: 실패 테스트(매퍼 순수 단위)**

`apps/api/tests/ledger/test_feasibility_result_adapter.py`:
```python
"""Phase 1: feasibility 수지결과 → 원장 payload 순수매퍼."""
from app.services.ledger.ledger_adapters import feasibility_result_to_ledger


def test_feasibility_result_payload_shape():
    out = feasibility_result_to_ledger({
        "development_type": "다세대", "total_revenue_won": 5_000_000_000,
        "net_profit_won": 800_000_000, "profit_rate_pct": 16.0, "npv_won": 600_000_000, "grade": "B",
    })
    assert out["kind"] == "feasibility"
    assert out["schema_version"] == "feasibility/v1"
    assert out["grade"] == "B"
    assert out["net_profit_won"] == 800_000_000
    # 비교핵심 findings_brief 존재
    assert any(f["check_id"] == "PROFIT_RATE" for f in out["findings_brief"])
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ledger/test_feasibility_result_adapter.py -q`
Expected: FAIL — `cannot import name 'feasibility_result_to_ledger'`.

- [ ] **Step 3: 구현 — 매퍼+래퍼(ledger_adapters.py 끝에 additive)**

`ledger_adapters.py`에 추가(기존 함수 0건 수정):
```python
def feasibility_result_to_ledger(result: dict[str, Any]) -> dict[str, Any]:
    """수지분석 결과(ModuleOutput dict) → 원장 payload(재무 성장루프 read 대상)."""
    return {
        "kind": "feasibility", "schema_version": "feasibility/v1",
        "development_type": result.get("development_type"),
        "total_revenue_won": result.get("total_revenue_won"),
        "net_profit_won": result.get("net_profit_won"),
        "profit_rate_pct": result.get("profit_rate_pct"),
        "npv_won": result.get("npv_won"), "grade": result.get("grade"),
        "findings_brief": [
            {"check_id": "PROFIT_RATE", "status": "info",
             "current": result.get("profit_rate_pct"), "limit": None},
            {"check_id": "NPV", "status": "info", "current": result.get("npv_won"), "limit": None},
        ],
    }


async def record_feasibility_result(
    *, result: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, pnu: str | None = None, address: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    # analysis_type="feasibility" (VCS 메타 'feasibility_vcs'와 분리 — read 성장루프 재무 체인)
    return await ledger.append_analysis(
        analysis_type="feasibility", payload=feasibility_result_to_ledger(result),
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source="feasibility", created_by=created_by,
    )
```

`v2_feasibility.py` `vcs_commit`(현재 `:861`)에서 `record_feasibility_commit` 배선 옆에 result write + prior read 추가:
```python
        # Phase 1: 수지 결과 자체를 'feasibility' 체인에 적재(성장루프 read 대상) + 직전 prior read
        try:
            from app.services.ledger.ledger_adapters import record_feasibility_result
            from app.services.ledger.prior_context import load_prior
            _tid = str(current_user.tenant_id) if current_user.tenant_id else None
            _pid = str(_parse_project_id(project_id))
            prior = await load_prior(analysis_type="feasibility", tenant_id=_tid, project_id=_pid)
            await record_feasibility_result(result=req.snapshot, tenant_id=_tid, project_id=_pid)
            if prior:
                result["prior_feasibility"] = prior  # read-only 첨부(주입 증거)
        except Exception as e:  # noqa: BLE001
            logger.warning("feasibility 성장루프 배선 실패 — skipped", err=str(e)[:160])
```
> `req.snapshot`은 수지 스냅샷(development_type/net_profit_won 등 보유). prior는 비교·표면화 전용(결정론 수치 불변).

- [ ] **Step 4: 통과 확인(매퍼 + 통합)**

Run:
```bash
cd apps/api && .venv/bin/python -m pytest tests/ledger/test_feasibility_result_adapter.py -q
DATABASE_URL=postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db .venv/bin/python -m pytest tests/integration/test_feasibility_growth_loop.py -q -rs
```
Expected: 매퍼 PASS; 통합 PASS(DB 가용) 또는 SKIP.

- [ ] **Step 5: 커밋**

```bash
git add apps/api/app/services/ledger/ledger_adapters.py apps/api/app/routers/v2_feasibility.py apps/api/tests/ledger/test_feasibility_result_adapter.py apps/api/tests/integration/test_feasibility_growth_loop.py
git commit -m "feat(phase1): feasibility 성장루프 — 'feasibility' 수지결과 write+read 쌍 신설(VCS 메타와 분리)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: W1 미배선 합류 — pricing/cost 원장 write 배선 (SSOT 완결)

**Files:**
- Modify: `apps/api/app/services/ledger/ledger_adapters.py`(pricing_revenue_to_ledger/record_pricing_revenue, cost_estimate_to_ledger/record_cost_estimate), `apps/api/app/api/endpoints/sales/actions.py:216`(pricing write), `apps/api/app/routers/cost.py:714`(cost write)
- Test: `apps/api/tests/ledger/test_pricing_cost_adapters.py`

- [ ] **Step 1: 실패 테스트(매퍼 순수 단위)**

`apps/api/tests/ledger/test_pricing_cost_adapters.py`:
```python
"""Phase 1: pricing/cost 산출 → 원장 payload 순수매퍼(W1 미배선 합류)."""
from app.services.ledger.ledger_adapters import pricing_revenue_to_ledger, cost_estimate_to_ledger


def test_pricing_revenue_payload():
    out = pricing_revenue_to_ledger(
        {"round_id": "r1", "units_priced": 40, "total_revenue_10k": 120000, "avg_unit_10k": 3000,
         "by_type": {"84A": {"count": 20, "total_10k": 60000}}}, round_id="r1")
    assert out["kind"] == "sales_revenue"
    assert out["schema_version"] == "sales_revenue/v1"
    assert out["round_id"] == "r1"
    assert any(f["check_id"] == "TOTAL_REVENUE" for f in out["findings_brief"])


def test_cost_estimate_payload():
    out = cost_estimate_to_ledger(
        summary={"direct": 100, "indirect": 30, "total": 130, "confidence_grade": "B"},
        header={"building_type": "공동주택", "structure_type": "RC", "total_gfa_sqm": 5000.0},
        estimate_id="e1")
    assert out["kind"] == "cost_estimate"
    assert out["estimate_id"] == "e1"
    assert any(f["check_id"] == "TOTAL_COST" for f in out["findings_brief"])
```

- [ ] **Step 2: 실패 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ledger/test_pricing_cost_adapters.py -q`
Expected: FAIL — `cannot import name 'pricing_revenue_to_ledger'`.

- [ ] **Step 3: 구현 — 매퍼+래퍼 신규(ledger_adapters.py)**

```python
def pricing_revenue_to_ledger(rev: dict[str, Any], *, round_id: str | None = None) -> dict[str, Any]:
    payload = {
        "kind": "sales_revenue", "schema_version": "sales_revenue/v1",
        "round_id": rev.get("round_id") or round_id, "units_priced": rev.get("units_priced"),
        "total_revenue_10k": rev.get("total_revenue_10k"), "avg_unit_10k": rev.get("avg_unit_10k"),
        "by_type": rev.get("by_type") or {},
        "findings_brief": [
            {"check_id": "TOTAL_REVENUE", "status": "info", "current": rev.get("total_revenue_10k"), "limit": None},
        ],
    }
    return payload


async def record_pricing_revenue(
    *, rev: dict[str, Any], round_id: str | None = None, tenant_id: str | None = None,
    project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type="sales_revenue", payload=pricing_revenue_to_ledger(rev, round_id=round_id),
        tenant_id=tenant_id, project_id=project_id, source="sales_pricing", created_by=created_by,
    )


def cost_estimate_to_ledger(*, summary: dict[str, Any], header: dict[str, Any],
                            estimate_id: str | None = None) -> dict[str, Any]:
    payload = {
        "kind": "cost_estimate", "schema_version": "cost_estimate/v1",
        "building_type": header.get("building_type"), "structure_type": header.get("structure_type"),
        "total_gfa_sqm": header.get("total_gfa_sqm"), "confidence_grade": summary.get("confidence_grade"),
        "direct": summary.get("direct"), "indirect": summary.get("indirect"), "total": summary.get("total"),
        "findings_brief": [
            {"check_id": "TOTAL_COST", "status": "info", "current": summary.get("total"), "limit": None},
        ],
    }
    if estimate_id is not None:
        payload["estimate_id"] = estimate_id
    return payload


async def record_cost_estimate(
    *, summary: dict[str, Any], header: dict[str, Any], estimate_id: str | None = None,
    tenant_id: str | None = None, project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type="cost_estimate",
        payload=cost_estimate_to_ledger(summary=summary, header=header, estimate_id=estimate_id),
        tenant_id=tenant_id, project_id=project_id, source="cost_boq", created_by=created_by,
    )
```

`cost.py`(현재 `:707-714`, `estimate_id = saved.get("estimate_id")` 직후) write 배선:
```python
        # Phase 1: 원가추정 SSOT 합류(best-effort 무중단)
        from app.services.ledger.ledger_adapters import record_cost_estimate
        await record_cost_estimate(
            summary=boq["summary"], header=boq["header"], estimate_id=estimate_id,
            tenant_id=req.tenant_id, project_id=project_id,
        )
```

`actions.py`의 pricing 라우터(현재 `:216` 부근 `pricing_revenue`/`pricing_solve_base`/`pricing_group_apply`)에서 산출 dict 확보 직후:
```python
        # Phase 1: 분양매출 SSOT 합류(best-effort)
        from app.services.ledger.ledger_adapters import record_pricing_revenue
        await record_pricing_revenue(
            rev=res, round_id=str(round_id),
            tenant_id=str(getattr(ctx.user, "tenant_id", "") or "") or None,
            project_id=str(ctx.site_id), created_by=str(ctx.user.id),
        )
```
> `record_*`는 `append_analysis`가 예외 흡수하므로 호출부는 throw 없음. 엔진 함수(`project_revenue` 등)·반환 dict·프론트 계약 절대 불변(라우터 호출부에만 한 줄 가산).

- [ ] **Step 4: 통과 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ledger/test_pricing_cost_adapters.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: 커밋**

```bash
git add apps/api/app/services/ledger/ledger_adapters.py apps/api/app/routers/cost.py apps/api/app/api/endpoints/sales/actions.py apps/api/tests/ledger/test_pricing_cost_adapters.py
git commit -m "feat(phase1): W1 미배선 합류 — pricing(sales_revenue)·cost(cost_estimate) 원장 write 배선

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: 통합 성장루프 e2e + 결정론 불변 검증 + skipped==0 게이트

**Files:**
- Test: `apps/api/tests/integration/test_growth_loop_e2e.py`

- [ ] **Step 1: e2e 테스트 작성(DB)**

`apps/api/tests/integration/test_growth_loop_e2e.py`:
```python
"""Phase 1 수용기준: (1)성장루프(2회차가 1회차 prior 사용) (2)결정론 불변 (3)멱등."""
import os
import pytest

pytestmark = pytest.mark.asyncio


async def _db() -> bool:
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_growth_loop_and_determinism():
    if not await _db():
        pytest.skip("DB 미가용 — Postgres(5444) 기동 후 실행")
    from app.services.ledger import analysis_ledger_service as ledger
    tid, addr, pnu = "t-e2e", "의정부동 224", "1115010300102240000"

    r1 = await ledger.append_analysis(
        analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr,
        payload={"kind": "design_audit", "schema_version": "design_audit/v1",
                 "verdict": "conditional", "findings_brief": [{"check_id": "FAR-01", "status": "fail",
                 "current": 250.0, "limit": 200.0}]})
    assert r1["ok"] is True
    # 멱등: 동일 payload 재append → unchanged
    r1b = await ledger.append_analysis(
        analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr,
        payload={"kind": "design_audit", "schema_version": "design_audit/v1",
                 "verdict": "conditional", "findings_brief": [{"check_id": "FAR-01", "status": "fail",
                 "current": 250.0, "limit": 200.0}]})
    assert r1b.get("unchanged") is True

    prior = await ledger.get_latest(analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr)
    assert prior is not None and prior["payload"]["findings_brief"][0]["current"] == 250.0

    # 체인 무결성 — prior가 read되어도 verify_chain 깨지지 않음(결정론 불변)
    v = await ledger.verify_chain(analysis_type="design_audit", tenant_id=tid, pnu=pnu, address=addr)
    assert v.get("ok") is not False  # 변조 없음
```

- [ ] **Step 2: 통과 확인**

Run: `cd apps/api && DATABASE_URL=postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/integration/test_growth_loop_e2e.py -q -rs`
Expected: PASS(DB 가용) 또는 SKIP.

- [ ] **Step 3: ★수용기준 게이트 — skipped==0 (skip≠검증)**

DB 기동 후 전체 Phase 1 통합테스트가 **skip 없이 PASS**해야 진짜 검증:
```bash
cd apps/api
# 1) 인프라 기동(미기동 시): docker compose -f ../../infra/docker-compose.yml up -d postgres
# 2) 마이그레이션: DATABASE_URL=... .venv/bin/alembic upgrade head
DATABASE_URL=postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db \
INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/integration/test_comprehensive_growth_loop.py \
  tests/integration/test_design_audit_growth_loop.py tests/integration/test_feasibility_growth_loop.py \
  tests/integration/test_growth_loop_e2e.py -rs -v
```
Expected: 전부 PASS, **skipped==0**. skip이 1건이라도 있으면 DB 미기동 → 수용기준 미충족(재기동 후 재실행).

- [ ] **Step 4: 전체 회귀 — 결정론 코어 불변 확인**

Run: `cd apps/api && .venv/bin/python -m pytest tests/ -k "verdict or citation or interpreter" -q`
Expected: 기존 결정론/citation/interpreter 테스트 전부 PASS(Phase 1은 additive라 무변동).

- [ ] **Step 5: 커밋 + 푸시**

```bash
git add apps/api/tests/integration/test_growth_loop_e2e.py
git commit -m "test(phase1): 성장루프 e2e + 결정론 불변 + 멱등 + skipped==0 수용기준 게이트

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push origin feature/trust-infra-2026-06-11
```

---

## Self-Review

**1. Spec coverage(spec:61,121-126 Phase 1):**
- "comprehensive_analysis·design_audit·feasibility 진입부에서 get_latest를 prior_context로 주입" → Task 4(comprehensive)·Task 5(design_audit)·Task 6(feasibility). ✓
- "BaseInterpreter 9개 프롬프트에 prior_context 근거블록" → Task 2(단일 합류점 _invoke). ✓
- "'이전결론 모순시 명시' citation_gate" → Task 1(build_prior_block 모순규칙)·Task 3(citation_gate prior_evidence). ✓
- W1 미배선(sales pricing/cost_estimate) SSOT 합류 → Task 7. ✓
- 모순 자동탐지·플래그는 **Phase 2**(범위 밖, 본 plan 미포함 — 정직). prior_comparison은 표면화까지만.

**2. Placeholder scan:** 모든 코드 스텝에 실제 코드 수록. "적절히 처리" 류 없음. feasibility 키 분기(feasibility_vcs vs feasibility)는 Task 6에서 명시 결정(신규 'feasibility' write 쌍). ✓

**3. Type consistency:** `prior`(get_latest 반환 dict: `{analysis_type,version,content_hash,created_at,payload}`), `build_prior_block(prior)`/`prior_numbers(prior)`는 전 Task 동일 시그니처. `prior_context` 키워드는 _invoke(str)·orchestrator.run/audit(dict) 두 타입 — 의도적 구분: 인터프리터엔 **포맷된 문자열 블록**(build_prior_block 결과), 오케스트레이터엔 **원본 dict**(_compare_with_prior가 payload 파싱). Task 4에서 인터프리터 호출 시 `prior_context=prior_block`(str), Task 5에서 run 호출 시 `prior_context=_prior`(dict)로 일관. ✓
- `record_*` 래퍼 시그니처는 기존 `record_design_audit` 패턴(keyword-only, best-effort) 일치. ✓

**검증 한계(정직):** 본 plan의 통합테스트(Task 4·5·6·8)는 DB 필요 — 무DB 환경에선 SKIP. **skip은 검증 아님**(Task 8 Step 3이 skipped==0 강제). 구현은 (B) 환경(infra Postgres+alembic) 기동 후 실행할 것. 순수 단위(Task 1·2·3·6매퍼·7매퍼)는 DB 없이 검증 가능.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-06-16-phase1-growth-read-loop.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — task별 fresh subagent + task 간 2단계 리뷰, 빠른 반복. (REQUIRED SUB-SKILL: superpowers:subagent-driven-development)

**2. Inline Execution** — 현 세션에서 executing-plans로 배치 실행 + 체크포인트. (REQUIRED SUB-SKILL: superpowers:executing-plans)

**권장 전제:** Task 4·5·6·8은 DB 통합테스트 → (B) 환경(infra Postgres 5444 + alembic upgrade head) 기동 후 실행해야 skipped==0 수용기준 충족. 순수 단위 Task(1·2·3 + 6·7 매퍼)는 지금 DB 없이 실행 가능.
