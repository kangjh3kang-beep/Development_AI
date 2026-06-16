# Phase 2 — Lineage DAG · 결정론 모순 자동감지 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 원장(prior)과 현재 분석을 비교해 모순(status 플립·수치 델타)을 자동 플래그(+심각도)하고, 분석 파생 관계를 lineage 그래프로 기록한다.

**Architecture:** 순수 결정론 탐지기(`ledger/contradiction.py`, LLM·DB 없음) + lazy `_ensure` 그래프 테이블(`ledger/lineage.py`, `analysis_ledger` 패턴 모방). 기존 `_compare_with_prior`(design_audit) seed를 탐지기 호출로 격상하고, comprehensive·feasibility의 prior read 지점(Phase 1)에 모순 표면화 + lineage write-back을 additive로 합류. **결정론 verdict/수치 절대 불변 — 탐지기는 비교·표면화 전용.**

**Tech Stack:** Python 3.12, SQLAlchemy 2.0(async)/asyncpg, Postgres16(실DB), pytest 9 (asyncio_mode=auto). 코드 WSL 네이티브. 테스트는 PowerShell→`wsl.exe`로 venv 실행.

**불변규칙(전 Task):** additive·하위호환 · 결정론 코어/수치/verdict 불변 · LLM 수치 비생성 · 정직표기(except→logger.warning) · alembic 금지(lazy `_ensure`) · feature 브랜치 커밋·푸시만(머지·배포 보류).

**환경(매 테스트):**
```
export DATABASE_URL='postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5432/propai_db'
export INTERP_REDIS_CACHE=0
cd apps/api && .venv/bin/python -m pytest <파일> -q -rs   # -k 금지, 파일 명시. psycopg2 미설치 → async만.
```

---

## File Structure

- Create `apps/api/app/services/ledger/contradiction.py` — 순수 결정론 모순 탐지기(무 DB).
- Create `apps/api/app/services/ledger/lineage.py` — lazy `_ensure` lineage 엣지 테이블 기록/조회.
- Create `apps/api/tests/ledger/test_contradiction.py` — 단위(무 DB).
- Create `apps/api/tests/ledger/test_lineage.py` — 통합(실 DB, skip-if-unavailable).
- Create `apps/api/tests/ledger/test_phase2_e2e.py` — e2e(실 DB).
- Modify `apps/api/app/services/design_audit/design_audit_orchestrator.py:208-223,349-350` — `_compare_with_prior`에 contradictions 합류(additive).
- Modify `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py:149-155 및 write-back 지점` — 모순 표면화 + lineage write-back.
- Modify `apps/api/app/services/market/feasibility_service.py` — (실행 시 정밀 확인) prior read 지점에 동일 합류.

---

## Task 1: contradiction.py — 순수 결정론 모순 탐지기 (무 DB)

**Files:**
- Create: `apps/api/app/services/ledger/contradiction.py`
- Test: `apps/api/tests/ledger/test_contradiction.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/ledger/test_contradiction.py
from app.services.ledger import contradiction as C


def test_status_flip_pass_to_fail_is_high():
    flips = C.detect_status_flips({"far": "pass"}, {"far": "fail"})
    assert flips == [{"kind": "status_flip", "key": "far",
                      "prev": "pass", "now": "fail", "severity": "high"}]


def test_status_flip_pass_to_warning_is_medium():
    flips = C.detect_status_flips({"a": "적합"}, {"a": "조건부적합"})
    assert flips[0]["severity"] == "medium"


def test_status_improvement_is_low_but_flagged():
    flips = C.detect_status_flips({"a": "fail"}, {"a": "pass"})
    assert flips[0]["severity"] == "low"


def test_status_unchanged_not_flagged():
    assert C.detect_status_flips({"a": "pass"}, {"a": "pass"}) == []


def test_numeric_delta_relative_thresholds():
    out = C.detect_numeric_deltas({"x": 100.0, "y": 100.0, "z": 100.0},
                                  {"x": 121.0, "y": 111.0, "z": 105.0},
                                  rel_threshold=0.10)
    sev = {d["key"]: d["severity"] for d in out}
    assert sev["x"] == "high" and sev["y"] == "medium"   # z(5%)는 임계 미만 → 제외
    assert "z" not in sev


def test_numeric_abs_threshold_for_rate():
    # profit_rate 5%p 절대임계 — 상대변화는 작아도 절대 변화로 플래그
    out = C.detect_numeric_deltas({"profit_rate": 18.0}, {"profit_rate": 12.0},
                                  rel_threshold=0.50, abs_thresholds={"profit_rate": 5.0})
    assert out and out[0]["key"] == "profit_rate"


def test_extract_status_from_findings_brief():
    payload = {"findings_brief": [{"check_id": "far", "status": "fail"}],
               "verdict": "부적합"}
    st = C.extract_status(payload)
    assert st["far"] == "fail" and st["__verdict__"] == "부적합"


def test_extract_numbers_flattens_paths_skipping_bools():
    nums = C.extract_numbers({"a": 1, "b": {"c": 2.5}, "ok": True, "lst": [10, 20]})
    assert nums == {"a": 1.0, "b.c": 2.5, "lst[0]": 10.0, "lst[1]": 20.0}


def test_detect_contradictions_aggregates_and_summarizes():
    prior = {"payload": {"findings_brief": [{"check_id": "far", "status": "pass"}],
                         "profit_rate": 20.0}}
    current = {"payload": {"findings_brief": [{"check_id": "far", "status": "fail"}],
                           "profit_rate": 10.0}}
    res = C.detect_contradictions(prior, current, rel_threshold=0.10)
    assert res["has_contradiction"] is True
    assert res["max_severity"] == "high"
    keys = {c["key"] for c in res["contradictions"]}
    assert "far" in keys and "profit_rate" in keys


def test_detect_contradictions_empty_when_no_prior():
    assert C.detect_contradictions(None, {"payload": {"x": 1}})["has_contradiction"] is False
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/ledger/test_contradiction.py -q`
Expected: FAIL (`ModuleNotFoundError: app.services.ledger.contradiction`).

- [ ] **Step 3: Implement `contradiction.py`**

```python
"""Phase 2 결정론 모순 탐지 — prior(원장) vs 현재 분석의 모순을 자동 플래그한다.

순수 함수(LLM·DB 없음). 새 수치/판정을 만들지 않는다(비교·플래그 전용).
적용: design_audit(findings_brief) · comprehensive(site_analysis) · feasibility.
"""
from __future__ import annotations

from typing import Any

# status 위계(낮을수록 양호). 한/영 동의어 동일 랭크.
_STATUS_RANK: dict[str, int] = {
    "pass": 0, "ok": 0, "적합": 0, "정상": 0,
    "warning": 1, "warn": 1, "조건부적합": 1, "주의": 1,
    "fail": 2, "부적합": 2, "위반": 2, "error": 2,
}


def _norm_status(s: Any) -> str | None:
    if s is None:
        return None
    return str(s).strip().lower()


def _status_rank(s: Any) -> int | None:
    return _STATUS_RANK.get(_norm_status(s) or "")


def _flip_severity(prev: Any, now: Any) -> str:
    """status 플립 심각도(결정론): 악화 폭이 클수록 높음. 개선/미지는 low."""
    pr, nr = _status_rank(prev), _status_rank(now)
    if pr is None or nr is None:
        return "low"
    diff = nr - pr
    if diff >= 2:
        return "high"
    if diff == 1:
        return "medium"
    return "low"


def _numeric_severity(rel: float) -> str:
    if rel >= 0.20:           # inf 포함
        return "high"
    if rel >= 0.10:
        return "medium"
    return "low"


def detect_status_flips(prior_status: dict[str, Any], current_status: dict[str, Any]) -> list[dict[str, Any]]:
    """동일 키 status 변화 플래그(+severity). 키 정렬로 결정론."""
    flips: list[dict[str, Any]] = []
    for key in sorted(set(prior_status) & set(current_status)):
        pv, cv = prior_status[key], current_status[key]
        if _norm_status(pv) != _norm_status(cv):
            flips.append({"kind": "status_flip", "key": key, "prev": pv, "now": cv,
                          "severity": _flip_severity(pv, cv)})
    return flips


def detect_numeric_deltas(
    prior_numbers: dict[str, float], current_numbers: dict[str, float],
    *, rel_threshold: float = 0.10, abs_thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """동일 키 수치의 상대변화(또는 키별 절대임계) 초과 플래그(+severity). 결정론."""
    abs_thresholds = abs_thresholds or {}
    out: list[dict[str, Any]] = []
    for key in sorted(set(prior_numbers) & set(current_numbers)):
        pv, cv = float(prior_numbers[key]), float(current_numbers[key])
        delta = cv - pv
        denom = abs(pv)
        if denom > 1e-9:
            rel = abs(delta) / denom
        else:
            rel = 0.0 if abs(delta) <= 1e-9 else float("inf")
        key_abs = abs_thresholds.get(key)
        flagged = (key_abs is not None and abs(delta) >= key_abs) or rel >= rel_threshold
        if not flagged:
            continue
        out.append({"kind": "numeric_delta", "key": key, "prev": pv, "now": cv, "delta": delta,
                    "rel_change": None if rel == float("inf") else round(rel, 4),
                    "severity": _numeric_severity(rel)})
    return out


def extract_status(payload: Any) -> dict[str, str]:
    """payload에서 (식별자→status) 추출. findings_brief/findings + 최상위 verdict."""
    out: dict[str, str] = {}
    if not isinstance(payload, dict):
        return out
    for listkey in ("findings_brief", "findings"):
        items = payload.get(listkey)
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("status") is not None:
                    cid = it.get("check_id") or it.get("id") or it.get("name")
                    if cid is not None:
                        out[str(cid)] = it.get("status")
    if payload.get("verdict") is not None:
        out["__verdict__"] = payload.get("verdict")
    return out


def extract_numbers(payload: Any, *, _prefix: str = "", _out: dict[str, float] | None = None,
                    _depth: int = 0) -> dict[str, float]:
    """payload를 점경로 키로 평탄화해 수치만 추출(bool 제외, 깊이 제한). 결정론."""
    out = {} if _out is None else _out
    if _depth > 12 or isinstance(payload, bool):
        return out
    if isinstance(payload, (int, float)):
        if _prefix:
            out[_prefix] = float(payload)
        return out
    if isinstance(payload, dict):
        for k in payload:
            extract_numbers(payload[k], _prefix=f"{_prefix}.{k}" if _prefix else str(k),
                            _out=out, _depth=_depth + 1)
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            extract_numbers(v, _prefix=f"{_prefix}[{i}]", _out=out, _depth=_depth + 1)
    return out


def _unwrap(p: Any) -> dict[str, Any]:
    if isinstance(p, dict) and "payload" in p and isinstance(p.get("payload"), dict):
        return p["payload"]
    return p if isinstance(p, dict) else {}


def detect_contradictions(
    prior: Any, current: Any,
    *, rel_threshold: float = 0.10, abs_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """prior payload vs 현재 payload 모순(status 플립 + 수치 델타) 결정론 집계.

    prior/current는 원장 payload 또는 {'payload': ...} 래퍼 허용.
    반환: {contradictions, counts(by severity), max_severity, has_contradiction, note}.
    """
    pp, cc = _unwrap(prior), _unwrap(current)
    flips = detect_status_flips(extract_status(pp), extract_status(cc))
    deltas = detect_numeric_deltas(extract_numbers(pp), extract_numbers(cc),
                                   rel_threshold=rel_threshold, abs_thresholds=abs_thresholds)
    items = flips + deltas
    counts = {"low": 0, "medium": 0, "high": 0}
    for it in items:
        counts[it["severity"]] = counts.get(it["severity"], 0) + 1
    max_sev = next((s for s in ("high", "medium", "low") if counts.get(s)), None)
    return {
        "contradictions": items, "counts": counts, "max_severity": max_sev,
        "has_contradiction": bool(items),
        "note": "결정론 모순탐지(prior 대비 status 플립·수치 델타) — 판정/수치 비생성, 비교 전용",
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/ledger/test_contradiction.py -q`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/ledger/contradiction.py apps/api/tests/ledger/test_contradiction.py
git commit -F /tmp/msg.txt   # feat(ledger): Phase2 T1 결정론 모순 탐지기(contradiction.py) + 단위테스트
```

---

## Task 2: lineage.py — lazy `_ensure` lineage 엣지 (실 DB)

**Files:**
- Create: `apps/api/app/services/ledger/lineage.py`
- Test: `apps/api/tests/ledger/test_lineage.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/ledger/test_lineage.py
import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"), reason="실 DB 필요(DATABASE_URL)")


@pytest.mark.asyncio
async def test_record_edge_and_get_parents():
    from app.services.ledger import lineage
    ch, ph = f"c{uuid.uuid4().hex}", f"p{uuid.uuid4().hex}"
    r = await lineage.record_edge(child_hash=ch, child_type="design_audit",
                                  parent_hash=ph, parent_type="design_audit",
                                  contradiction_count=2, max_severity="high")
    assert r["ok"] is True
    parents = await lineage.get_parents(child_hash=ch)
    assert any(p["parent_hash"] == ph and p["max_severity"] == "high" for p in parents)


@pytest.mark.asyncio
async def test_record_edge_idempotent_upsert():
    from app.services.ledger import lineage
    ch, ph = f"c{uuid.uuid4().hex}", f"p{uuid.uuid4().hex}"
    await lineage.record_edge(child_hash=ch, child_type="t", parent_hash=ph, parent_type="t",
                              contradiction_count=1, max_severity="low")
    await lineage.record_edge(child_hash=ch, child_type="t", parent_hash=ph, parent_type="t",
                              contradiction_count=3, max_severity="high")  # upsert
    parents = await lineage.get_parents(child_hash=ch)
    edges = [p for p in parents if p["parent_hash"] == ph]
    assert len(edges) == 1 and edges[0]["contradiction_count"] == 3   # 중복행 없이 갱신


@pytest.mark.asyncio
async def test_self_edge_rejected():
    from app.services.ledger import lineage
    h = f"h{uuid.uuid4().hex}"
    r = await lineage.record_edge(child_hash=h, child_type="t", parent_hash=h, parent_type="t")
    assert r["ok"] is False


@pytest.mark.asyncio
async def test_get_lineage_walks_ancestors():
    from app.services.ledger import lineage
    a, b, c = (f"h{uuid.uuid4().hex}" for _ in range(3))  # c→b→a
    await lineage.record_edge(child_hash=b, child_type="t", parent_hash=a, parent_type="t")
    await lineage.record_edge(child_hash=c, child_type="t", parent_hash=b, parent_type="t")
    g = await lineage.get_lineage(content_hash=c)
    anc = {e["parent_hash"] for e in g["ancestors"]}
    assert a in anc and b in anc
```

- [ ] **Step 2: Run to verify fail**

Run: `DATABASE_URL=... .venv/bin/python -m pytest tests/ledger/test_lineage.py -q -rs`
Expected: FAIL (`ModuleNotFoundError: app.services.ledger.lineage`).

- [ ] **Step 3: Implement `lineage.py`**

```python
"""Phase 2 Lineage DAG — 분석 파생 그래프(어떤 prior에서 파생됐는지) 엣지 원장.

analysis_ledger와 동일한 lazy `_ensure` 패턴(alembic from-scratch 깨짐 회피).
순수 기록/조회 — 결정론 코어 불변, additive. 모순탐지 결과(개수·심각도)를 엣지에 동반.
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_LINEAGE_DDL = (
    "CREATE TABLE IF NOT EXISTS analysis_lineage ("
    "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  tenant_id text,"
    "  child_hash text NOT NULL,"
    "  child_type text NOT NULL,"
    "  parent_hash text NOT NULL,"
    "  parent_type text NOT NULL,"
    "  relation text NOT NULL DEFAULT 'derived_from',"
    "  contradiction_count int NOT NULL DEFAULT 0,"
    "  max_severity text,"
    "  created_at timestamptz DEFAULT now()"
    ")"
)
_LINEAGE_IDX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_lineage_edge "
    "ON analysis_lineage(child_hash, parent_hash, relation)",
    "CREATE INDEX IF NOT EXISTS idx_lineage_child ON analysis_lineage(tenant_id, child_hash)",
    "CREATE INDEX IF NOT EXISTS idx_lineage_parent ON analysis_lineage(tenant_id, parent_hash)",
)


async def _ensure(db) -> None:
    from sqlalchemy import text
    await db.execute(text(_LINEAGE_DDL))
    for ix in _LINEAGE_IDX:
        await db.execute(text(ix))


async def record_edge(
    *, child_hash: str, child_type: str, parent_hash: str, parent_type: str,
    tenant_id: str | None = None, relation: str = "derived_from",
    contradiction_count: int = 0, max_severity: str | None = None,
) -> dict[str, Any]:
    """파생 엣지 1건 기록(멱등 upsert). self-edge/빈 해시는 거부."""
    if not child_hash or not parent_hash:
        return {"ok": False, "message": "child_hash·parent_hash 필수"}
    if child_hash == parent_hash:
        return {"ok": False, "skipped": True, "message": "self-edge 금지"}
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            await db.execute(text(
                "INSERT INTO analysis_lineage"
                "(tenant_id, child_hash, child_type, parent_hash, parent_type, relation,"
                " contradiction_count, max_severity)"
                " VALUES (:tid,:ch,:ct,:ph,:pt,:rel,:cc,:ms)"
                " ON CONFLICT (child_hash, parent_hash, relation) DO UPDATE SET"
                "   contradiction_count = EXCLUDED.contradiction_count,"
                "   max_severity = EXCLUDED.max_severity"),
                {"tid": tenant_id, "ch": child_hash, "ct": child_type, "ph": parent_hash,
                 "pt": parent_type, "rel": relation, "cc": int(contradiction_count),
                 "ms": max_severity})
            await db.commit()
            return {"ok": True, "child_hash": child_hash, "parent_hash": parent_hash,
                    "relation": relation}
    except Exception as e:  # noqa: BLE001
        logger.warning("lineage 엣지 기록 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}


async def get_parents(*, child_hash: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """직계 부모(파생 원천) 엣지 목록."""
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            await _ensure(db)
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            rows = (await db.execute(text(
                f"SELECT parent_hash, parent_type, relation, contradiction_count, max_severity,"
                f" created_at FROM analysis_lineage "
                f"WHERE {tenant_sql} AND child_hash = :ch ORDER BY created_at"),
                {"tid": tenant_id, "ch": child_hash})).all()
            return [{"parent_hash": r[0], "parent_type": r[1], "relation": r[2],
                     "contradiction_count": int(r[3]), "max_severity": r[4],
                     "created_at": str(r[5])} for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("lineage 부모 조회 실패", err=str(e)[:160])
        return []


async def get_lineage(*, content_hash: str, tenant_id: str | None = None,
                      max_depth: int = 5) -> dict[str, Any]:
    """조상(파생 원천)을 max_depth까지 BFS로 수집 — 파생 계보 그래프."""
    ancestors: list[dict[str, Any]] = []
    seen: set[str] = set()
    frontier = [content_hash]
    depth = 0
    while frontier and depth < max_depth:
        nxt: list[str] = []
        for h in frontier:
            for edge in await get_parents(child_hash=h, tenant_id=tenant_id):
                ph = edge["parent_hash"]
                ancestors.append({"child_hash": h, **edge})
                if ph not in seen:
                    seen.add(ph)
                    nxt.append(ph)
        frontier = nxt
        depth += 1
    return {"content_hash": content_hash, "depth": depth, "ancestors": ancestors}
```

- [ ] **Step 4: Run to verify pass**

Run: `DATABASE_URL=... INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_lineage.py -q -rs`
Expected: PASS (4 passed, skipped==0).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/ledger/lineage.py apps/api/tests/ledger/test_lineage.py
git commit -F /tmp/msg.txt   # feat(ledger): Phase2 T2 lineage 엣지 lazy 테이블(record/get) + 실DB 테스트
```

---

## Task 3: design_audit 모순 합류 (seed 격상)

**Files:**
- Modify: `apps/api/app/services/design_audit/design_audit_orchestrator.py:208-223` (`_compare_with_prior`)
- Test: `apps/api/tests/ledger/test_contradiction.py` (추가)

`_compare_with_prior`는 status 변화 나열만 한다. contradiction 탐지기 결과를 **additive 키 `contradictions`로 합류**(기존 `status_changes` 불변, verdict 불변).

- [ ] **Step 1: Write failing test (additive 키 확인)**

```python
# tests/ledger/test_contradiction.py 에 추가
def test_compare_with_prior_adds_contradictions_keeping_status_changes():
    from app.services.design_audit.design_audit_orchestrator import _compare_with_prior
    prior = {"version": 1, "payload": {"verdict": "적합",
             "findings_brief": [{"check_id": "far", "status": "pass"}]}}
    findings = [{"check_id": "far", "status": "fail"}]
    out = _compare_with_prior(prior, findings)
    assert out["status_changes"] == [{"check_id": "far", "prev_status": "pass", "now_status": "fail"}]
    assert out["contradictions"]["has_contradiction"] is True
    assert out["contradictions"]["max_severity"] == "high"
    assert out["prior_verdict"] == "적합"   # 기존 키 불변
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/ledger/test_contradiction.py::test_compare_with_prior_adds_contradictions_keeping_status_changes -q`
Expected: FAIL (`KeyError: 'contradictions'`).

- [ ] **Step 3: Modify `_compare_with_prior` (additive)**

`design_audit_orchestrator.py:218-223` `return {...}` 직전에 contradictions 계산을 추가하고 반환 dict에 키 1개 가산:

```python
def _compare_with_prior(prior: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Phase 1: status 변화 표면화 + Phase 2: 결정론 모순 플래그(additive, 판정 미반영, 순수)."""
    from app.services.ledger.contradiction import detect_contradictions
    payload = (prior or {}).get("payload") or {}
    prev = {f.get("check_id"): f for f in (payload.get("findings_brief") or [])}
    cur = {f.get("check_id"): f for f in findings}
    changes = []
    for cid, c in cur.items():
        p = prev.get(cid)
        if p and p.get("status") != c.get("status"):
            changes.append({"check_id": cid, "prev_status": p.get("status"), "now_status": c.get("status")})
    contradictions = detect_contradictions(prior, {"findings_brief": findings, "verdict": payload.get("verdict")})
    return {
        "prior_version": prior.get("version"),
        "prior_verdict": payload.get("verdict"),
        "status_changes": changes,
        "contradictions": contradictions,
        "note": "이전 대비 상태 변화·모순(참고용) — 종합판정은 현재 결정론 결과를 따른다",
    }
```

> 참고: 현재 분석의 verdict는 이 함수 호출 시점엔 findings만 있으므로 prior verdict를 current 쪽에 넣지 않는다(현재 findings status로만 비교). verdict 모순은 status `__verdict__`가 아닌 findings status 플립으로 감지된다.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/ledger/test_contradiction.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/design_audit/design_audit_orchestrator.py apps/api/tests/ledger/test_contradiction.py
git commit -F /tmp/msg.txt   # feat(design_audit): Phase2 T3 _compare_with_prior 모순 플래그 합류(additive)
```

---

## Task 4: comprehensive 모순 표면화 + lineage write-back (실 DB)

**Files:**
- Modify: `apps/api/app/services/land_intelligence/comprehensive_analysis_service.py:149-155` (prior read 지점) + write-back 지점(Phase 1 T4, `append_analysis` 호출부 — 실행 시 정밀 확인).
- Test: `apps/api/tests/ledger/test_phase2_e2e.py`

설계: `load_prior`로 얻은 `prior`(content_hash 포함)와 현재 `result`로 `detect_contradictions` 호출 → `result["contradictions"]`에 표면화(additive). write-back(`append_analysis`)이 새 content_hash를 반환하면, prior가 있었을 때 `lineage.record_edge(child=new_hash, parent=prior_hash, contradiction_count, max_severity)` 기록.

- [ ] **Step 1: Write failing e2e test**

```python
# apps/api/tests/ledger/test_phase2_e2e.py
import os
import uuid
import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="실 DB 필요")


@pytest.mark.asyncio
async def test_writeback_records_lineage_edge_with_contradiction_meta():
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import lineage
    from app.services.ledger.contradiction import detect_contradictions

    pnu = f"TESTPNU{uuid.uuid4().hex[:10]}"
    v1 = await ledger.append_analysis(analysis_type="site_analysis", pnu=pnu,
                                      payload={"far": 200.0, "verdict": "적합"})
    v2_payload = {"far": 260.0, "verdict": "부적합"}   # 30%↑ + verdict 변화
    contra = detect_contradictions({"payload": {"far": 200.0, "verdict": "적합"}},
                                   {"payload": v2_payload})
    v2 = await ledger.append_analysis(analysis_type="site_analysis", pnu=pnu, payload=v2_payload)
    edge = await lineage.record_edge(
        child_hash=v2["content_hash"], child_type="site_analysis",
        parent_hash=v1["content_hash"], parent_type="site_analysis",
        contradiction_count=len(contra["contradictions"]), max_severity=contra["max_severity"])
    assert edge["ok"] is True
    parents = await lineage.get_parents(child_hash=v2["content_hash"])
    assert parents and parents[0]["parent_hash"] == v1["content_hash"]
    assert parents[0]["max_severity"] in ("high", "medium")
```

- [ ] **Step 2: Run to verify fail/pass baseline**

Run: `DATABASE_URL=... INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_phase2_e2e.py -q -rs`
Expected: T1·T2 구현 후엔 PASS 가능(이 테스트는 서비스 배선과 독립적인 계약 검증). 서비스 배선(Step 3)은 런타임 표면화를 추가.

- [ ] **Step 3: Wire comprehensive (실행 시 `append_analysis` write-back 호출부 라인 확정 후 additive 삽입)**

`comprehensive_analysis_service.py`에서 (a) `result` 조립 직후 `result["contradictions"] = detect_contradictions(prior, result)` 가산, (b) write-back `append_analysis(...)` 성공 결과 `wb`에 대해 `if prior and prior.get("content_hash") and not wb.get("unchanged"): await lineage.record_edge(child_hash=wb["content_hash"], child_type="site_analysis", parent_hash=prior["content_hash"], parent_type=prior.get("analysis_type","site_analysis"), contradiction_count=len(result["contradictions"]["contradictions"]), max_severity=result["contradictions"]["max_severity"], tenant_id=tenant_id)`. import는 함수 내부 지역 import(순환참조 회피, 기존 패턴 동일).

- [ ] **Step 4: Run to verify pass**

Run: `DATABASE_URL=... INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_phase2_e2e.py -q -rs`
Expected: PASS, skipped==0.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/land_intelligence/comprehensive_analysis_service.py apps/api/tests/ledger/test_phase2_e2e.py
git commit -F /tmp/msg.txt   # feat(comprehensive): Phase2 T4 모순 표면화 + lineage write-back(실DB)
```

---

## Task 5: feasibility 모순 합류

**Files:**
- Modify: `apps/api/app/services/market/feasibility_service.py` (prior read/`_compare_with_prior` 지점 — 실행 시 grep `_compare_with_prior|load_prior|append_analysis`로 정밀 확인)
- Test: `apps/api/tests/ledger/test_phase2_e2e.py` (feasibility 케이스 추가)

설계: feasibility는 수치(profit_rate·net_profit_won·total)가 핵심 → `detect_contradictions(prior, current, abs_thresholds={"profit_rate": 5.0})`로 수익률 5%p 절대임계 포함. design_audit과 동일하게 결과 dict에 `contradictions` 키 additive, write-back 시 lineage 엣지.

- [ ] **Step 1~5:** T4와 동형(테스트 먼저 → 배선 → 실DB PASS → 커밋). feasibility 통합테스트는 `analysis_type="feasibility"` 체인으로 v1(profit_rate 18)→v2(profit_rate 11) 모순(절대임계 5%p 초과) 플래그 + lineage 엣지 검증.

```bash
git commit -F /tmp/msg.txt   # feat(feasibility): Phase2 T5 모순 합류 + lineage(실DB)
```

---

## Task 6: e2e 통합 + 무결성 불변 + skipped==0 게이트

**Files:**
- Modify: `apps/api/tests/ledger/test_phase2_e2e.py`

- [ ] **Step 1: 통합·불변 테스트 추가**

```python
@pytest.mark.asyncio
async def test_contradiction_does_not_mutate_ledger_verdict_and_chain_intact():
    from app.services.ledger import analysis_ledger_service as ledger
    pnu = f"TESTPNU{uuid.uuid4().hex[:10]}"
    await ledger.append_analysis(analysis_type="site_analysis", pnu=pnu,
                                 payload={"far": 100.0, "verdict": "적합"})
    await ledger.append_analysis(analysis_type="site_analysis", pnu=pnu,
                                 payload={"far": 150.0, "verdict": "부적합"})
    # 모순탐지는 read 전용 — 원장 체인 무결성 불변
    vr = await ledger.verify_chain(analysis_type="site_analysis", pnu=pnu)
    assert vr["verified"] is True and vr["length"] == 2
    latest = await ledger.get_latest(analysis_type="site_analysis", pnu=pnu)
    assert latest["payload"]["verdict"] == "부적합"   # 결정론 판정 불변(탐지기 비개입)
```

- [ ] **Step 2: 전체 Phase 2 스위트 실행(skipped==0 게이트)**

Run: `DATABASE_URL=... INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_contradiction.py tests/ledger/test_lineage.py tests/ledger/test_phase2_e2e.py -q -rs`
Expected: all passed, **skipped == 0**(실 DB 가용). 교차-이벤트루프 spurious skip 시 Phase 1 패턴(`engine.dispose()` 격리) 적용.

- [ ] **Step 3: 회귀 — 인접 원장 테스트 불변 확인**

Run: `DATABASE_URL=... INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger -q -rs`
Expected: 기존 Phase 0/1 원장 테스트 + Phase 2 전부 PASS.

- [ ] **Step 4: Commit + push**

```bash
git add apps/api/tests/ledger/test_phase2_e2e.py
git commit -F /tmp/msg.txt   # test(ledger): Phase2 T6 e2e + 무결성 불변 + skipped==0 게이트
git push                      # feature/trust-infra-2026-06-11 (머지·배포 보류)
```

---

## Self-Review

- **Spec coverage:** 모순 자동감지(status 플립+수치 델타+severity, design_audit·comprehensive·feasibility=T1/T3/T4/T5) ✅ · Lineage DAG(파생 엣지 lazy 테이블 record/get + write-back=T2/T4/T5) ✅ · 결정론 불변·additive(T3 status_changes 보존, T6 verdict/chain 불변 테스트) ✅ · 실DB skipped==0(T6) ✅.
- **Placeholder scan:** T1/T2/T3는 완전 코드. T4/T5는 write-back `append_analysis` 호출부 라인만 실행 시 grep으로 확정(코드 형태·키는 명시) — 서비스 파일 미독해 구간의 정직 표기.
- **Type consistency:** `detect_contradictions`→`{contradictions[], counts, max_severity, has_contradiction}` 전 Task 동일. `record_edge(child_hash,child_type,parent_hash,parent_type,contradiction_count,max_severity)` / `get_parents(child_hash)` / `get_lineage(content_hash)` 시그니처 T2 정의와 T4/T5 호출 일치.
