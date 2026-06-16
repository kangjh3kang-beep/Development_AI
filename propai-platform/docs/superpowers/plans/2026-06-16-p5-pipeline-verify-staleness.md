# P5 — 파이프라인 단계검증 · 원장 staleness/재분석 루프 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans / subagent-driven-development. 체크박스(`- [ ]`) 추적.

**Goal:** (1) 파이프라인 각 단계 산출을 `VerifierService.verify`로 강제 검증(additive 검증블록), (2) 원장 read로 staleness(시간경과)+변경감지 → 재분석 제안 서비스 신설(분석루프 폐쇄), (3) pipeline 공공데이터 입력에 cross_validate/freshness 가드.

**배경(배포 코디 P5 인계, 실측 보정):** 원장 read 루프 자체는 Phase 1/2가 닫음(`load_prior`/`get_latest` 소비자 다수, 변경감지=`contradiction.py`). P5는 그 위에 **get_history 소비 + staleness + 재분석 제안**을 additive로 얹는다. cross_validate/Freshness는 정의·타 경로 연결됨 → pipeline 경로에만 가드 추가.

**Architecture:** 전부 제 소유 파일(`app/services/pipeline/**`·`app/services/ledger/**`·`app/services/data_validation/**`) 내 additive. `VerifierService.verify`는 LLM 부재 시 규칙기반(_prescan+calc_ledger+range_rules) verdict 반환 → 결정론 검증 가능. staleness는 순수 임계로직 + DB read.

**불변규칙:** additive·하위호환(원장 스키마·8엔진·StageResult 계약 불변) · 결정론 코어/수치 불변(검증·staleness는 read·표면화 전용, stage 산출 수치 변경 금지) · LLM 비수치 · 정직표기(verdict/issues/data_source/skipped, silent failure 금지) · feature 브랜치 푸시까지(머지·배포=배포 코디).

**환경:** `DATABASE_URL=...asyncpg...`, `INTERP_REDIS_CACHE=0`, `cd apps/api && .venv/bin/python -m pytest <f> -q -rs`. ⚠️ WSL=PowerShell 도구, 실DB=engine.dispose 루프격리.

---

## File Structure
- Create `apps/api/app/services/ledger/staleness.py` — get_latest/get_history 소비 → age+변경 → 재분석 제안.
- Modify `apps/api/app/services/pipeline/project_pipeline.py` — `run()` 루프에 단계별 `_verify_stage` 훅(verification 블록 additive) + 공공데이터 입력 trust 가드.
- Create `apps/api/tests/ledger/test_staleness.py`, `apps/api/tests/pipeline/__init__.py`, `apps/api/tests/pipeline/test_pipeline_verification.py`.

---

## Task 1: ledger staleness/재분석 제안 서비스 (분석루프 폐쇄)

**Files:** Create `apps/api/app/services/ledger/staleness.py` · Test `apps/api/tests/ledger/test_staleness.py`

- [ ] **Step 1: 실패 테스트**

```python
# apps/api/tests/ledger/test_staleness.py
import uuid
import pytest
from app.services.ledger import staleness as S

pytestmark = pytest.mark.asyncio


def test_recommend_pure_logic():
    # 순수 임계 로직(무 DB): stale 또는 changed면 재분석 권장
    assert S._recommend(age_days=120, max_age_days=90, changed=False)["recommend_reanalysis"] is True
    assert S._recommend(age_days=10, max_age_days=90, changed=False)["recommend_reanalysis"] is False
    assert S._recommend(age_days=10, max_age_days=90, changed=True)["recommend_reanalysis"] is True
    r = S._recommend(age_days=200, max_age_days=90, changed=True)
    assert r["stale"] is True and r["changed"] is True and "stale" in r["reasons"] and "changed" in r["reasons"]


async def _db():
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory, engine
        await engine.dispose()
        async with async_session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def test_no_prior_returns_no_reanalysis():
    if not await _db():
        pytest.skip("DB 미가용")
    pnu = f"P{uuid.uuid4().hex[:10]}"
    r = await S.check_staleness(analysis_type="site_analysis", tenant_id=f"t-{uuid.uuid4().hex[:8]}", pnu=pnu)
    assert r["recommend_reanalysis"] is False and r["reason"] == "no_prior"


async def test_fresh_prior_with_change_recommends_reanalysis():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger import analysis_ledger_service as ledger
    from sqlalchemy import text
    from app.core.database import async_session_factory
    tid, pnu = f"t-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        await ledger.append_analysis(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                     payload={"effective_far": 200.0, "verdict": "적합"})
        # 갓 적재 → not stale(max 90), 그러나 current가 크게 다르면 changed=True → 재분석 권장
        r = await S.check_staleness(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                    current={"effective_far": 260.0, "verdict": "부적합"}, max_age_days=90)
        assert r["stale"] is False                  # 방금 적재(age≈0)
        assert r["changed"] is True                 # far 30%↑ + verdict flip
        assert r["recommend_reanalysis"] is True
        assert r["prior_version"] == 1 and r["age_days"] is not None
    finally:
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id=:t"), {"t": tid})
            await db.commit()


async def test_history_trend_counts_versions():
    if not await _db():
        pytest.skip("DB 미가용")
    from app.services.ledger import analysis_ledger_service as ledger
    from sqlalchemy import text
    from app.core.database import async_session_factory
    tid, pnu = f"t-{uuid.uuid4().hex[:8]}", f"P{uuid.uuid4().hex[:10]}"
    try:
        for far in (100.0, 150.0, 220.0):
            await ledger.append_analysis(analysis_type="site_analysis", tenant_id=tid, pnu=pnu,
                                         payload={"effective_far": far})
        rep = await S.staleness_report(analysis_type="site_analysis", tenant_id=tid, pnu=pnu)
        assert rep["versions"] == 3 and rep["latest_version"] == 3
    finally:
        async with async_session_factory() as db:
            await db.execute(text("DELETE FROM analysis_ledger WHERE tenant_id=:t"), {"t": tid})
            await db.commit()
```

- [ ] **Step 2: 실패 확인** — FAIL(모듈 없음).

- [ ] **Step 3: 구현 `staleness.py`**

```python
"""P5 — 원장 read 기반 staleness/재분석 제안(분석루프 폐쇄).

get_latest/get_history를 소비해 (a)시간경과(staleness) (b)변경감지(contradiction)로
'재분석 권장'을 결정론으로 산출한다. 원장·산출 수치 불변(read·표면화 전용).
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_MAX_AGE_DAYS = 90


def _recommend(*, age_days: float | None, max_age_days: int, changed: bool) -> dict[str, Any]:
    """순수 임계 로직 — stale(시간) 또는 changed(내용)면 재분석 권장. (무 DB·결정론)"""
    stale = age_days is not None and age_days > max_age_days
    reasons: list[str] = []
    if stale:
        reasons.append("stale")
    if changed:
        reasons.append("changed")
    return {"stale": stale, "changed": changed,
            "recommend_reanalysis": bool(stale or changed), "reasons": reasons}


async def check_staleness(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None,
    current: dict[str, Any] | None = None, max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
) -> dict[str, Any]:
    """동일 체인 최신 분석의 age + (current 제공 시) 변경 → 재분석 제안.

    - prior 없음: recommend_reanalysis=False, reason='no_prior'(정직).
    - age_days: DB에서 now()-created_at(일). 파싱 불필요.
    - changed: detect_contradictions(prior, current).has_contradiction.
    """
    try:
        from app.services.ledger import analysis_ledger_service as ledger
        prior = await ledger.get_latest(analysis_type=analysis_type, tenant_id=tenant_id,
                                        pnu=pnu, address=address, project_id=project_id)
        if not prior:
            return {"analysis_type": analysis_type, "prior_version": None, "age_days": None,
                    "recommend_reanalysis": False, "reason": "no_prior",
                    "stale": False, "changed": False, "reasons": []}
        age_days = await _age_days(analysis_type=analysis_type, tenant_id=tenant_id,
                                   pnu=pnu, address=address, project_id=project_id)
        changed = False
        max_sev = None
        if current is not None:
            from app.services.ledger.contradiction import detect_contradictions
            contra = detect_contradictions(prior, current)
            changed = bool(contra.get("has_contradiction"))
            max_sev = contra.get("max_severity")
        rec = _recommend(age_days=age_days, max_age_days=max_age_days, changed=changed)
        return {"analysis_type": analysis_type, "prior_version": prior.get("version"),
                "age_days": age_days, "max_severity": max_sev, "reason": "ok", **rec}
    except Exception as e:  # noqa: BLE001
        logger.warning("staleness 점검 실패(graceful)", analysis_type=analysis_type, err=str(e)[:160])
        return {"analysis_type": analysis_type, "recommend_reanalysis": False,
                "reason": "error", "message": str(e)[:160],
                "stale": False, "changed": False, "reasons": []}


async def _age_days(*, analysis_type, tenant_id, pnu, address, project_id) -> float | None:
    """최신 버전의 now()-created_at(일)을 DB에서 직접 산출(파싱·tz 이슈 회피)."""
    from sqlalchemy import text
    from app.core.database import async_session_factory
    from app.services.ledger.analysis_ledger_service import _chain_where, _ensure, _norm_addr
    async with async_session_factory() as db:
        await _ensure(db)
        key_sql, params = _chain_where(pnu, _norm_addr(address), project_id)
        params.update({"tid": tenant_id, "atype": analysis_type})
        tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
        row = (await db.execute(text(
            f"SELECT EXTRACT(EPOCH FROM (now() - created_at)) / 86400.0 "
            f"FROM analysis_ledger WHERE {tenant_sql} AND {key_sql} AND analysis_type = :atype "
            f"ORDER BY version DESC LIMIT 1"), params)).first()
        return float(row[0]) if row and row[0] is not None else None


async def staleness_report(
    *, analysis_type: str, tenant_id: str | None = None, pnu: str | None = None,
    address: str | None = None, project_id: str | None = None, limit: int = 50,
) -> dict[str, Any]:
    """get_history 소비 — 버전 타임라인 요약(재분석 추세 판단용)."""
    from app.services.ledger import analysis_ledger_service as ledger
    hist = await ledger.get_history(analysis_type=analysis_type, tenant_id=tenant_id,
                                    pnu=pnu, address=address, project_id=project_id, limit=limit)
    return {"analysis_type": analysis_type, "versions": len(hist),
            "latest_version": hist[0]["version"] if hist else 0, "history": hist}
```

- [ ] **Step 4: 통과 확인** — 실DB all passed, skipped==0.
- [ ] **Step 5: 커밋** — `feat(ledger): P5 staleness/재분석 제안 서비스(get_history 소비·분석루프 폐쇄)`

---

## Task 2: 파이프라인 단계별 검증 강제 (VerifierService)

**Files:** Modify `apps/api/app/services/pipeline/project_pipeline.py`(run 루프 + 신규 `_verify_stage`) · Test `apps/api/tests/pipeline/test_pipeline_verification.py`

`run()`의 각 stage COMPLETED 직후, `VerifierService.verify(stage.value, source, output=stage.data)` 호출 → 결과를 `stage.data["verification"]`에 additive 부착. LLM 부재 시 규칙기반 verdict(graceful). 결정론 산출 수치는 불변.

- [ ] **Step 1: 실패 테스트**

```python
# apps/api/tests/pipeline/test_pipeline_verification.py
import pytest
from app.services.pipeline.project_pipeline import ProjectPipeline, PipelineState, StageResult, PipelineStage, PipelineStatus

pytestmark = pytest.mark.asyncio


async def test_verify_stage_attaches_verification_block_additive():
    p = ProjectPipeline()
    state = PipelineState(address="서울 테스트")
    state.stages["feasibility"] = StageResult(stage=PipelineStage.FEASIBILITY,
                                              status=PipelineStatus.COMPLETED,
                                              data={"profit_rate_pct": 12.0, "land_area_sqm": 300.0})
    await p._verify_stage(state, PipelineStage.FEASIBILITY)
    v = state.stages["feasibility"].data["verification"]
    assert v["verdict"] in ("pass", "warn", "fail")     # 규칙기반이라도 verdict 산출
    assert "issues" in v
    # 결정론 산출 수치는 불변
    assert state.stages["feasibility"].data["profit_rate_pct"] == 12.0


async def test_verify_stage_flags_negative_area():
    p = ProjectPipeline()
    state = PipelineState(address="서울 테스트")
    state.stages["site_analysis"] = StageResult(stage=PipelineStage.SITE_ANALYSIS,
                                                status=PipelineStatus.COMPLETED,
                                                data={"land_area_sqm": -10.0, "max_far": 200.0})
    await p._verify_stage(state, PipelineStage.SITE_ANALYSIS)
    v = state.stages["site_analysis"].data["verification"]
    assert v["verdict"] == "fail"                       # 음수 면적 → high → fail(규칙)


async def test_verify_stage_skips_non_completed():
    p = ProjectPipeline()
    state = PipelineState(address="x")
    state.stages["cost"] = StageResult(stage=PipelineStage.COST, status=PipelineStatus.SKIPPED, data={})
    await p._verify_stage(state, PipelineStage.COST)
    assert "verification" not in state.stages["cost"].data   # skip 단계는 검증 안 함(정직)
```

- [ ] **Step 2: 실패 확인** — FAIL(`_verify_stage` 없음).

- [ ] **Step 3: 구현 — `project_pipeline.py`에 `_verify_stage` 추가 + `run()` 루프 배선**

`run()`의 `stage_result.status = PipelineStatus.COMPLETED` 직후(try 블록 말미)에:
```python
                stage_result.status = PipelineStatus.COMPLETED
                await self._verify_stage(state, stage)   # P5: 단계 산출 검증(additive)
```

신규 메서드(클래스 내, additive):
```python
    async def _verify_stage(self, state: "PipelineState", stage: "PipelineStage") -> None:
        """P5: 단계 산출을 VerifierService로 검증해 stage.data['verification']에 additive 부착.

        LLM 부재 시 규칙기반(_prescan+calc_ledger+range_rules) verdict — graceful. 결정론 산출
        수치는 변경하지 않는다(read·표면화 전용). COMPLETED 단계만 검증(skip/실패 단계 제외 — 정직).
        """
        try:
            sr = state.stages.get(stage.value)
            if sr is None or sr.status != PipelineStatus.COMPLETED:
                return
            data = sr.data if isinstance(sr.data, dict) else {}
            if not data:
                return
            from app.services.verification.verifier_service import VerifierService
            # source=단계 입력 맥락(있으면 직전 payload), output=단계 산출. 없으면 자기일관성 검사.
            source = self._verify_source_for(state, stage) or data
            result = await VerifierService().verify(stage.value, source, data)
            data["verification"] = result
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).warning("단계 검증 스킵: %s", str(e)[:140])

    def _verify_source_for(self, state: "PipelineState", stage: "PipelineStage") -> dict | None:
        """검증 source(근거 입력) 선택 — 단계간 payload 우선(없으면 None → 자기일관성)."""
        m = {
            PipelineStage.DESIGN: state.site_to_design,
            PipelineStage.COST: state.design_to_cost,
            PipelineStage.FEASIBILITY: state.cost_to_feasibility,
        }
        payload = m.get(stage)
        return payload.model_dump() if payload is not None else None
```

- [ ] **Step 4: 통과 확인** — `pytest tests/pipeline/test_pipeline_verification.py -q` → 3 passed.
- [ ] **Step 5: 회귀** — `pytest tests/integration/test_full_pipeline.py -q -rs`(기존 파이프라인 계약 불변).
- [ ] **Step 6: 커밋** — `feat(pipeline): P5 단계별 VerifierService 검증 강제(additive verification 블록)`

---

## Task 3: (HIGH) pipeline 공공데이터 가드 — cross_validate/freshness (additive)

**Files:** Modify `apps/api/app/services/pipeline/project_pipeline.py` · Test 동일 파일

site_analysis 단계의 공공데이터 입력(공시지가·실거래·면적)에 `data_validation.trust.cross_validate`/freshness 메타를 stage.data["trust_guard"]로 additive 부착(값 불변, 신뢰 표면화). 실행 시 trust.cross_validate·freshness API 시그니처 확인 후 배선.

- [ ] T1~T2 동형(테스트 먼저 → 배선 → 통과 → 커밋). **단**: 결정론 수치 불변, 가드는 data_source/confidence/skipped 표기만. 신호 부족 시 skipped(정직).

```bash
git commit -m "feat(pipeline): P5 공공데이터 cross_validate/freshness 가드(additive trust_guard)"
```

---

## Task 4: e2e + 정직표기 회귀 + skipped==0 게이트
- [ ] `pytest tests/ledger/test_staleness.py tests/pipeline -q -rs` → all passed, skipped==0.
- [ ] 회귀: `pytest tests/ledger tests/agents tests/integration/test_full_pipeline.py -q -rs`(원장·에이전트·파이프라인 불변).
- [ ] 핸드오프 노트(배포 코디용): 변경 파일·라이브검증 엔드포인트(원장 read=`routers/analysis_ledger.py` 기존, staleness는 서비스레벨)·skipped==0 증빙.
- [ ] 커밋 + push(머지·배포=배포 코디).

## Self-Review
- **Spec coverage:** #1 pipeline verify(T2) · #2 staleness/재분석(T1, get_history 소비) · #3 cross_validate/freshness pipeline 가드(T3) · 정직표기·결정론 불변(T1/T2 테스트). #4 일부는 기존 연결됨(pipeline 경로만 T3).
- **Placeholder scan:** T1/T2 완전 코드. T3는 trust.cross_validate/freshness 시그니처 실행 시 확인(서비스 미독 구간 정직 표기).
- **Type consistency:** `check_staleness(*,analysis_type,tenant_id,pnu,address,project_id,current,max_age_days)→{recommend_reanalysis,stale,changed,age_days,...}` · `_recommend(*,age_days,max_age_days,changed)` · `_verify_stage(state,stage)`/`_verify_source_for`.
