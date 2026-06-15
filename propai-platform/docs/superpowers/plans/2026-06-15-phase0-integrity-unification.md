# Phase 0 — 진실 정렬 + 무결성 단일화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 흩어진 해시체인/감사 무결성을 `analysis_ledger` 단일 SSOT로 수렴하고, 그 신뢰성을 코드로 검증 가능하게 만든다(새 분석 기능 0, 위험 0).

**Architecture:** 계층2(지식저장소)의 `analysis_ledger`(SHA256 해시체인, append-only)를 유일한 무결성 원장으로 확정한다. (1) 런타임 lazy-DDL로만 존재하던 원장 스키마를 alembic 마이그레이션으로 정식화하고, (2) prod 미사용 dead code인 in-memory `AuditTrailService`의 별도 해시체인을 폐기·하위호환 유지한 채 감사 이벤트를 원장에 `analysis_type="audit"`로 흡수하며, (3) 테넌트/프로젝트 전 체인을 한 번에 검증하는 `verify_all_chains` 일괄검증을 추가하고, (4) design_audit·feasibility_vcs·domain_agent 산출물을 원장 append 경로로 통합하는 어댑터를 만든다.

**Tech Stack:** Python 3.12 · FastAPI · async SQLAlchemy(`async_session_factory`) · PostgreSQL(postgis16, raw `text()` SQL) · Alembic(raw `op.execute`) · pytest(`asyncio_mode=auto`).

---

## 결정 사항(이 plan을 고정하는 전제)

- **승인된 마스터 spec**: `docs/superpowers/specs/2026-06-15-living-agent-knowledge-platform-design.md` (§8 Phase 0). 4대 결정 D1~D4 승인 완료.
- **unit(b) 수렴 방식**: **원장으로 흡수**(사용자 2026-06-15 확정). 별도 `audit_trail` 테이블 미생성. 감사 이벤트는 `analysis_ledger`에 `analysis_type="audit"`로 append → 단일 체인·단일 verify.
- **코드 실측 근거(file:line)**:
  - 원장 SSOT: `apps/api/app/services/ledger/analysis_ledger_service.py` — `append_analysis`/`get_latest`/`get_history`/`verify_chain` 구현·가동. 세션은 `from app.core.database import async_session_factory`, 테이블은 `_ensure(db)`의 `CREATE TABLE IF NOT EXISTS` **lazy-DDL**(마이그레이션 부재 — 실측 확인).
  - 원장 라우터: `apps/api/app/routers/analysis_ledger.py` — 단건 체인 `GET /verify`는 **이미 존재**(`:83`). 부재한 것은 **전 체인 일괄검증**.
  - 감사: in-memory `apps/api/app/services/audit/audit_service.py:68` `AuditTrailService`(SHA256 체인) = **prod 미사용(테스트만 import)**. 별개로 `app/core/audit.py`(`admin_audit_log` flat 로그)·`apps/api/services/audit_service.py`(`legal_audit_trail`)가 산재 → 무결성 체인의 SSOT는 원장으로 일원화.
  - 미통합 산출물: `append_analysis` 호출처 6곳(billing/pipeline/sales/router)에 **design_audit·feasibility_vcs·domain_agents 없음** → unit(d) 갭 실재.
- **불변규칙(전 task 위반 금지)**:
  1. 브랜치 `feature/trust-infra-2026-06-11`만. main 직푸시·머지 금지(배포는 별도 담당). 이 작업은 커밋·푸시까지.
  2. additive·하위호환. 기존 키/엔드포인트/스토어/테스트계약/8엔진/DesignReviewResult/원장 스키마 불변, 신규만. 마이그레이션은 additive·멱등(`IF NOT EXISTS`). **예외(버그픽스 carve-out, 2026-06-15 시뮬레이션 검증)**: `_chain_where`의 NULL/빈문자열 비대칭 결함(Task 2.5)은 project-keyed 체인의 read/write/verify를 모두 깨뜨리므로 단일 교정을 허용한다 — 빈문자열이 영구저장된 적 없어(유일 INSERT가 `or None`) 완전 backward-compatible이며, 커밋·plan에 carve-out임을 정직 명시.
  3. 결정론 코어(계층1) 불변. LLM 수치 비생성. 원장 append 실패가 분석을 막지 않음(best-effort, `logger.warning`).
  4. 무결성=내부 SHA256 해시체인+verify_chain로 한정(블록체인·Merkle 미도입).
  5. 갭 판단은 실코드 file:line 인용.
  6. 커밋 푸터: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` (리포 규약 — 하네스 기본값 아님).

## v2 고도화 요약 (가상 시뮬레이션 검증, 2026-06-15)

38-에이전트 시뮬레이션·적대적 검증으로 **28건 확정**(3건 기각). 목표 달성 verdict와 반영 패치:

| 목표 | v1 판정 | v2 보강 |
|---|---|---|
| (i) 최적 통합(SSOT 단일화) | **부분** — 감사 흡수가 실제 감사 발생 10곳(`audit_admin_action`6·`record_audit`4)에 미배선 → `append_audit` 호출처 0건(데드코드 재발) | **Task 4에 배선 Step 추가**(audit_admin_action·record_audit 흡수) |
| (ii) 최적 연동(배선) | **미흡** — design_audit 직접경로 ②(`document_audit_service.py`) 누락, best-effort가 `except: pass`(자기 불변규칙3 위반) | **Task 6**: grep 스코프+②경로·`except→logger.warning`·트랜잭션 가시성(commit 후 append) |
| (iii) 반복루프 데이터품질 | **미흡** — `_chain_where` NULL/'' 비대칭으로 project-keyed 체인 read/verify 전 경로 비기능 | **Task 2.5 carve-out**·**Task 5.5** schema_version+backlink 규약 |

**🔴 전제 차단(필수 선결)**: 현 `.venv`에 `pytest-asyncio` 미설치 → `asyncio_mode=auto` 무시 → plan의 **모든 async 테스트가 SKIP이 아니라 FAIL/ERROR** → 수용기준 3개 전부 검증 불가. **Task 0 Step 0**에서 해결.

**반영 우선순위**(차단 게이트 먼저): Task0 Step0(async 러너) → Task2.5(NULL-safe) → Task4 배선(감사 단일화) → Task5 P4·Task6(연동) → Task6 정합성(except/트랜잭션)·Task3 verify_all 재작성 → Task5.5(품질 규약) → Task7(검증 건전성).

**Phase 1로 명시 이관**(Phase 0 미구현, 한계 기재): chain_quality_metrics read 훅·`GET /metrics`, `get_prior_context` 정규화 헬퍼, dedup 카운터/unchanged_ratio, 비연속 dedup 강제, 기존 직접 적재 6곳 schema_version 태깅, project-only 기존 적재분 prev_hash 백필 마이그레이션, **동시 append 경쟁조건의 예방**(UNIQUE/advisory lock — 레거시 중복행과 충돌하므로 데이터 정리 후 별도 task; Phase 0은 verify_all의 `duplicate_version` **탐지**까지만).

**2차 재검증(2026-06-15, 9-에이전트 적대적):** (iii) 반복루프 데이터품질 = **완성**(Task 2.5 carve-out 실코드 정합 실증), (i) 통합·(ii) 연동 = **부분**. `correct:false` 2건을 추가 교정 — Task 0 Step 0 **pin 재현성·canary 재작성**(기존 canary는 async 아닌 prometheus_client 부재로 ERROR), Task 6 Step 2 **핸들러 변수 정합**(`current_user.tenant_id`/`created_by=None`/stdlib logger `%s`)·**rollback 쓰기경로 배선**(rollback도 신규 commit row 생성). **실행 준비도: Task 0 Step 0 + Task 6 Step 2가 차단 게이트 — 본 v2.1에 반영 완료**, 그 외 영역은 실코드 정합 확인.

---

## 작업환경·실행 규약(매 task 공통)

- **편집·커밋·테스트 위치(WSL2 Ubuntu)**: `/home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform`.
- **Windows→WSL 파일 접근(Read/Write/Edit)**: UNC `\\wsl.localhost\Ubuntu\home\kangjh3kang\My_Projects\Development_AI_trust_infra\propai-platform\...`. 평범한 `D:\` 경로는 "file not found"(알려진 실패모드) — 절대 "코드 없음"으로 판단 금지.
- **명령**: `wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform; <cmd>'`.
- **⚠️ async 러너 선결(Task 0 Step 0)**: 현 `.venv`에 `pytest-asyncio` 미설치(실측 `import pytest_asyncio`→ModuleNotFoundError) → `asyncio_mode=auto`가 "Unknown config option"으로 무시되어 **모든 async 테스트·픽스처가 SKIP이 아니라 FAIL/ERROR**. Task 0 Step 0에서 설치·검증한 뒤에야 아래 명령들의 Expected가 성립한다.
- **백엔드 테스트(apps/api에서)**: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest <파일> -q` — **파일 명시**(`-k` 금지). `asyncio_mode=auto`는 **pytest-asyncio 설치 후에만** 적용(설치 전 async 테스트 전부 실패).
- **⚠️ testpaths 미스매치**: `apps/api/pyproject.toml`·루트 `pytest.ini`의 `testpaths`가 repo-root `tests/`만 가리켜 **인자 없는 `pytest`로는 신규 `apps/api/tests/ledger/`가 미수집**된다 → ledger 테스트는 반드시 `tests/ledger` 경로를 명시 실행.
- **DB 통합테스트 전제**: 인프라 기동 `docker compose -f infra/docker-compose.yml up -d`(Postgres host **5444**). `apps/api/.env` 부재 시 기본 `DATABASE_URL`이 `localhost:5432`라 영구 skip되므로, 통합테스트 실행 시 compose와 일치하는 자격증명·포트를 명시: `export DATABASE_URL='postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db'`. 미기동 시 통합테스트는 자동 skip(Task 0 픽스처) — 단 **skip은 '검증됨'이 아니다**(Task 7에서 `skipped==0` 강제).
- **마이그레이션 검증(배포 담당 몫이나 로컬 확인 가능)**: apps/api에서 `.venv/bin/python -m alembic upgrade head`. alembic.ini `script_location=database/migrations`.
- **wsl.exe 인라인 커밋 주의**: 중첩 `$(...)`·내부 작은따옴표 금지 → 커밋 메시지는 `printf`로 `/tmp/msg.txt`에 쓰고 `git commit -q -F /tmp/msg.txt`.

---

## File Structure (생성/수정 파일 지도)

**생성(신규, additive)**
- `docs/architecture/layered-architecture.md` — 계층1/2/3 경계 + LLM 비수치 규칙 + 원장 SSOT 문서(unit a).
- `apps/api/database/migrations/versions/031_analysis_ledger.py` — 원장 스키마 정식화 마이그레이션(unit b1).
- `apps/api/app/services/ledger/audit_ledger.py` — 감사 이벤트 → 원장 흡수 경로(unit b2).
- `apps/api/app/services/ledger/ledger_adapters.py` — design_audit/feasibility/domain_agent → 원장 어댑터(unit d).
- `apps/api/tests/ledger/__init__.py`, `apps/api/tests/ledger/conftest.py` — 원장 통합테스트 DB 픽스처(skip-if-unavailable).
- `apps/api/tests/ledger/test_verify_all.py` — verify_all_chains 테스트.
- `apps/api/tests/ledger/test_audit_ledger.py` — 감사 흡수 테스트.
- `apps/api/tests/ledger/test_ledger_adapters.py` — 어댑터 매퍼 테스트.
- `apps/api/tests/ledger/test_migration_031.py` — 마이그레이션 연결/영속 테스트.
- `apps/api/tests/ledger/test_chain_where.py` — `_chain_where` NULL-safe 회귀(Task 2.5).
- `apps/api/tests/test_architecture_doc.py` — 아키텍처 문서 계약 테스트(unit a).

**수정(additive only — 예외 1건은 Task 2.5 carve-out)**
- `apps/api/app/services/ledger/analysis_ledger_service.py` — (carve-out) `_chain_where` else 분기 NULL-safe 교정(Task 2.5) + `verify_all_chains()` 신규 함수 추가(Task 3). 기존 함수 로직 불변.
- `apps/api/app/routers/analysis_ledger.py` — `GET /verify-all` 엔드포인트만 추가(기존 라우트 불변).
- `apps/api/app/services/audit/audit_service.py` — `AuditTrailService` docstring 비-SSOT 표기만(로직 불변).
- `apps/api/app/core/audit.py` — `audit_admin_action` 말미에 best-effort `append_audit` 배선(admin 감사 6곳, Task 4).
- `apps/api/services/audit_service.py` — `record_audit` 말미에 best-effort `append_audit` 배선(legal 감사 4곳, Task 4).
- `apps/api/services/domain_agents_service.py` — `run_domain` 말미에 best-effort 원장 append(+ logger, Task 6).
- feasibility commit **호출처**(예: `apps/api/app/routers/v2_feasibility.py`) — `await db.commit()` 이후 best-effort 원장 append(Task 6 Step 2; `version_control_db.commit()` 본문은 불변).
- design_audit 직접 호출 경로 2곳(`apps/api/app/routers/design_audit.py` + `apps/api/app/services/collaboration/document_audit_service.py`/`v2_collaboration.py`) — raw result 직후 best-effort `record_design_audit`(Task 6 Step 3).
- (Task 5.5) `apps/api/app/services/ledger/ledger_adapters.py`·`audit_ledger.py` — payload에 `schema_version`/backlink/`findings_brief` 보강(Task 5에서 생성 후 진화).

---

## Task 0: 원장 통합테스트 DB 픽스처 (skip-if-unavailable)

**근거**: Phase 0 수용기준("verify_chain이 전 프로젝트 변조 없음", "감사로그 재시작 후 0건 소실")은 **실 영속**을 검증해야 한다. 그런데 리포에는 DB 세션 픽스처가 전무(실측: conftest는 httpx client·샘플dict뿐, 워커 테스트만 `AsyncMock`). 원장 함수는 인자로 세션을 받지 않고 내부에서 `async_session_factory()`를 연다 → 실 Postgres에 붙는 픽스처가 필요. DB 미기동 시 자동 skip(정직).

**Files:**
- Create: `apps/api/tests/ledger/__init__.py`
- Create: `apps/api/tests/ledger/conftest.py`

- [ ] **Step 0: 비동기 러너·환경 게이트 (🔴 선결 — 재현가능 pin + 작동 probe까지)**

실측: 현 `.venv`의 `pytest`는 **9.1.0**이고 `pytest_asyncio`는 정상 설치 상태가 아니다(import 실패/메타데이터 없는 빈 namespace) → `asyncio_mode=auto` 무시, 모든 async 테스트·픽스처가 SKIP이 아니라 FAIL/ERROR. 또 `prometheus_client`·`shapely` 등 일부 선언 런타임 의존이 venv에 없어 **async와 무관한 import 에러**가 섞인다(그래서 `test_router_health.py`는 async가 아니라 prometheus_client 부재로 ERROR — canary로 부적합).

1) **pin 결정·기록(재현성 — literal `>=` 떠도는 설치 금지)** — `requirements.txt:83` `pytest-asyncio==0.24.0`은 `pytest<9` 요구라 venv의 9.1.0과 비호환. 둘 중 하나를 택해 **requirements/pyproject에 기록**:
   - (권장) pytest 9.x 유지 + pytest-asyncio를 pytest 9 호환 버전으로 상향(1.x 계열). 또는
   - pytest를 `==8.3.3`로 정렬 + `pytest-asyncio==0.24.0`.
   ```
   .venv/bin/python -m pip install 'pytest-asyncio'        # 위 결정에 맞는 정확한 버전 지정
   .venv/bin/python -c 'import importlib.metadata as m; print(m.version("pytest-asyncio"))'   # 메타데이터 있는 정상 설치 확인(빈 namespace 아님)
   ```
   해석된 버전을 `requirements.txt`/`pyproject.toml`에 반영(배포 담당 동기화).

2) **작동 probe(import만으론 부족 — async 테스트가 실제 PASS해야 함)** — ledger가 쓰는 모듈만 import하는 canary로:
   ```
   printf 'from app.core.database import async_session_factory\n\nasync def test_probe():\n    assert async_session_factory is not None\n' > tests/test_probe.py
   INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_probe.py -q   # 1 passed, 'Unknown config option: asyncio_mode' 경고 없음
   rm tests/test_probe.py
   ```
   ⚠️ canary로 `tests/test_router_health.py`를 쓰지 말 것(async 아닌 prometheus_client 부재로 ERROR → 게이트 오염).

3) **누락 런타임 의존 pre-flight** — 원장/ledger import 경로가 쓰는 의존이 venv에 있는지:
   ```
   .venv/bin/python -c 'import prometheus_client, shapely' 2>&1 | head -1   # ModuleNotFoundError면 설치 또는 게이트를 ledger-importable 모듈로 한정
   ```

Expected: pytest-asyncio 정상 메타데이터 버전 출력 + probe `1 passed`(경고 없음) + ledger import 경로 ModuleNotFoundError 0. ⚠️ MEMORY의 'known-broken 2 tests' 회귀 기준선은 위 정상화 후 재확립. 미충족 시 이후 모든 Step의 Expected(PASS/SKIP)가 성립하지 않으므로 여기서 중단·해결.

- [ ] **Step 1: 패키지 init 생성**

`apps/api/tests/ledger/__init__.py`:

```python
```

(빈 파일 — 디렉터리를 테스트 패키지로 인식시키기 위함.)

- [ ] **Step 2: DB 픽스처 작성**

`apps/api/tests/ledger/conftest.py`:

```python
"""원장 통합테스트 공용 픽스처.

원장 서비스 함수는 인자로 세션을 받지 않고 내부에서 ``async_session_factory()``를
열기 때문에, 동일 ``settings.DATABASE_URL``을 가리키는 세션을 직접 열어 시드/정리한다.
DB 미가용(인프라 미기동) 시 모듈 전체 skip(정직 — 거짓 통과 금지).
"""
from __future__ import annotations

import os
import sys
import uuid

import pytest
from sqlalchemy import text

# apps/api 를 import 경로에 추가(기존 tests/conftest.py와 동일 규약).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
async def ledger_db():
    """실 Postgres 세션(없으면 skip). 시드·검증·정리 전용(원장 함수와는 별도 세션)."""
    from app.core.database import async_session_factory

    try:
        async with async_session_factory() as probe:
            await probe.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"DB 미가용 — 원장 통합테스트 skip: {str(e)[:80]}")

    async with async_session_factory() as db:
        yield db


@pytest.fixture
async def tnt(ledger_db):
    """테스트 격리용 유니크 tenant_id. 종료 시 해당 테넌트 원장행 정리."""
    t = f"test-{uuid.uuid4().hex[:12]}"
    yield t
    await ledger_db.execute(
        text("DELETE FROM analysis_ledger WHERE tenant_id = :t"), {"t": t}
    )
    await ledger_db.commit()
```

- [ ] **Step 3: 픽스처 self-test로 skip/통과 동작 확인**

임시 확인용 테스트를 같은 폴더에 만들어 동작만 본다 — `apps/api/tests/ledger/test_smoke.py`:

```python
async def test_db_fixture_smoke(ledger_db, tnt):
    from sqlalchemy import text

    row = (await ledger_db.execute(text("SELECT 1"))).first()
    assert row[0] == 1
    assert tnt.startswith("test-")
```

- [ ] **Step 4: 실행 — DB 있으면 PASS, 없으면 SKIP**

Run (apps/api에서):
```
INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_smoke.py -q
```
Expected: DB 기동 시 `1 passed`; 미기동 시 `1 skipped`("DB 미가용" 메시지). 둘 다 정상(에러 0).

- [ ] **Step 5: 스모크 테스트 제거(픽스처만 남김)**

```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && rm apps/api/tests/ledger/test_smoke.py'
```

- [ ] **Step 6: Commit**

```
printf '%s\n' 'test(ledger): add skip-if-unavailable Postgres fixture for ledger integration tests' '' 'Phase 0 무결성 단일화 — 원장 함수는 내부 async_session_factory를 쓰므로 실 Postgres에' '붙는 ledger_db/tnt 픽스처 신설. DB 미기동 시 자동 skip(정직).' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add apps/api/tests/ledger/__init__.py apps/api/tests/ledger/conftest.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 1: 아키텍처 문서 (unit a) — 계층 경계 + LLM 비수치 규칙 명문화

**근거**: spec unit(a) "아키텍처 문서에 계층1/2/3 경계·LLM 비수치 규칙 명문화". 실측상 그런 문서 부재(`docs/`엔 ARCH_KNOWLEDGE_DEEPENING 등만). TDD로 "문서 계약 테스트"(필수 섹션 존재)를 먼저 실패시키고 문서로 통과.

**Files:**
- Test: `apps/api/tests/test_architecture_doc.py`
- Create: `docs/architecture/layered-architecture.md`

- [ ] **Step 1: 문서 계약 테스트(실패) 작성**

`apps/api/tests/test_architecture_doc.py`:

```python
"""아키텍처 문서 계약 — 계층 경계·LLM 비수치 규칙·원장 SSOT가 문서로 명문화됐는지 박제."""
import os

DOC = os.path.join(
    os.path.dirname(__file__), "..", "..", "..",
    "docs", "architecture", "layered-architecture.md",
)

REQUIRED = [
    "## 계층1 — 결정론 분석 코어",
    "## 계층2 — 프로젝트 지식저장소",
    "## 계층3 — 공동경영 멀티에이전트",
    "LLM은 절대 수치를 생성하지 않는다",
    "citation_gate",
    "analysis_ledger",
    "verify_chain",
    "schema_version",       # payload 규약(Task 5.5) 박제
    "prior_context",        # read 계약(Phase 1 전제) 박제
]


def test_architecture_doc_exists_and_covers_layers():
    assert os.path.exists(DOC), f"아키텍처 문서 부재: {DOC}"
    text = open(DOC, encoding="utf-8").read()
    missing = [s for s in REQUIRED if s not in text]
    assert not missing, f"필수 섹션/규칙 누락: {missing}"
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_architecture_doc.py -q`
Expected: FAIL — `아키텍처 문서 부재`.

- [ ] **Step 3: 문서 작성**

`docs/architecture/layered-architecture.md`:

```markdown
# 계층형 아키텍처 — 살아 성장하는 개발사업 지원 에이전트 플랫폼

작성: 2026-06-15 · 성격: 진실 정렬(Phase 0). 본 문서는 마스터 spec
(`docs/superpowers/specs/2026-06-15-living-agent-knowledge-platform-design.md`)의
3계층을 코드 경계로 못박는다.

## 계층1 — 결정론 분석 코어 (불변, '진실의 원천')

8엔진 오케스트레이터(`apps/api/app/services/design_audit/design_audit_orchestrator.py`)·
18+ 도메인 서비스·룰 사전예측(`design_change_predictor.py`)이 **모든 수치를 산출**한다.

- **LLM은 절대 수치를 생성하지 않는다.** 면적·비용·확률·판정 등 정량값은 항상 결정론
  서비스가 계산하고, LLM은 그 결과를 **해석·종합·토론**하는 데만 쓰인다.
- **citation_gate**: LLM 발언은 결정론 결과에 citation으로 매핑될 때만 허용(미근거 발언 차단).
- 정직 표기: `data_source(live|fallback|mock|unavailable)`·`confidence`·`skipped` 유지.

## 계층2 — 프로젝트 지식저장소 (SSOT)

`analysis_ledger`(SHA256 해시체인, append-only)가 **유일한 무결성 원장**이다.

- write: 계층1 산출물이 `analysis_ledger_service.append_analysis(...)`로 누적(버전+해시체인).
- payload 규약: 모든 신규 적재 payload는 `schema_version`+`kind`를 포함하고, read는 키 추정이 아니라
  `payload.get("schema_version")`로 안전 파싱한다(스키마 드리프트 방지). 대용량 원시는 원장에 넣지 않고
  `source` 참조키(`audit_id`/`sha`/`task_id`)로 기존 테이블과 역연결한다.
- 정규화·중복: 멱등은 '직전-동일 `content_hash`'일 때만 생략이며 A→B→A 같은 비연속 재출현은 의도된 누적이다.
  `_canonical`은 키 정렬만 보장하므로 매퍼는 수치 표현(소수자리·결측 표기)을 호출부에서 정규화(SHOULD).
- 무결성: `content_hash = sha256(정규화 payload)`, `prev_hash = 직전 버전 해시`. 변조탐지는
  `verify_chain`(단건 체인) / `verify_all_chains`(테넌트·프로젝트 전 체인 일괄)로 수행.
- 감사 흡수: 감사 이벤트도 `analysis_type="audit"`로 같은 원장에 append(별도 해시체인 폐기).
- read(성장 루프): 다음 분석이 이전 원장 버전을 `prior_context`로 읽는 경로는 **Phase 1**에서 닫는다.
  `get_latest`는 `analysis_type` 지정 시 단건 dict, 미지정 시 타입맵을 반환하며 `payload`는 임의 타입일 수
  있다(소비측 `isinstance(payload, dict)` 가드 필요) — 이 계약을 Phase 1 `get_prior_context` 헬퍼가 흡수한다.

## 계층3 — 공동경영 멀티에이전트

`expert_panel`(토론)·`coordinator`(supervisor)·SpecialistAgent(신설 예정)가 계층1을
**도구로 호출**해 결과를 근거로만 발언한다(citation_gate). 실구현은 Phase 3.

## 경계 규칙 요약

| 계층 | 책임 | 금지 |
|---|---|---|
| 1 | 수치 산출(결정론) | LLM 의존, 비결정성 |
| 2 | append-only 누적·무결성 검증 | 덮어쓰기, 원장 우회 |
| 3 | 해석·토론·종합 | 수치 생성, 미근거 발언 |
```

- [ ] **Step 4: 실행 — 통과 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_architecture_doc.py -q`
Expected: PASS (`1 passed`).

- [ ] **Step 5: Commit**

```
printf '%s\n' 'docs(arch): 계층1/2/3 경계 + LLM 비수치 규칙 명문화 (Phase 0 unit a)' '' '원장(analysis_ledger)=무결성 SSOT, citation_gate, verify_chain 명문화.' '문서 계약 테스트로 필수 섹션 박제.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add docs/architecture/layered-architecture.md apps/api/tests/test_architecture_doc.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 2: 원장 스키마 마이그레이션 정식화 (unit b1)

**근거**: `analysis_ledger`·`analysis_ledger_quota`는 런타임 `_ensure()`의 `CREATE TABLE IF NOT EXISTS`로만 존재(마이그레이션 부재 — 실측). "무결성 단일화·신뢰 가능"하려면 스키마가 버전관리돼야 한다. 마이그레이션은 **멱등(`IF NOT EXISTS`)**이라 기존 lazy-DDL과 충돌 없이 공존(기존 운영 DB·테스트 DB 모두 무해). alembic head는 `030_livekit_recordings`.

**Files:**
- Create: `apps/api/database/migrations/versions/031_analysis_ledger.py`
- Test: `apps/api/tests/ledger/test_migration_031.py`

- [ ] **Step 1: 마이그레이션 연결 테스트(실패) 작성**

`apps/api/tests/ledger/test_migration_031.py`:

```python
"""031 원장 마이그레이션 — 체인 연결 + (DB 있으면) 세션 간 영속 검증."""
import importlib.util
import os

MIG = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "database", "migrations", "versions", "031_analysis_ledger.py",
)


def _load():
    spec = importlib.util.spec_from_file_location("mig031", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_chain_links_to_030():
    assert os.path.exists(MIG), f"마이그레이션 부재: {MIG}"
    mod = _load()
    assert mod.revision == "031_analysis_ledger"
    assert mod.down_revision == "030_livekit_recordings"
    assert callable(mod.upgrade) and callable(mod.downgrade)
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_migration_031.py -q`
Expected: FAIL — `마이그레이션 부재`.

- [ ] **Step 3: 마이그레이션 작성**

`apps/api/database/migrations/versions/031_analysis_ledger.py` (스타일은 head `030_livekit_recordings.py`와 동일 — raw `op.execute`):

```python
"""031 — 분석 원장(해시체인) 스키마 정식화: analysis_ledger + analysis_ledger_quota

Revision ID: 031_analysis_ledger
Revises: 030_livekit_recordings
Create Date: 2026-06-15

기존 analysis_ledger_service._ensure()의 런타임 lazy-DDL을 alembic 버전관리로 흡수(무결성 단일화).
DDL은 서비스의 _DDL/_IDX/_QUOTA_DDL과 1:1 동일. additive·멱등(IF NOT EXISTS)이라 기존 lazy-DDL과
충돌 없이 공존. 감사 이벤트도 analysis_type='audit'로 본 테이블 한 곳에 누적(별도 audit 테이블 없음).
"""
from alembic import op

revision = "031_analysis_ledger"
down_revision = "030_livekit_recordings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id TEXT,
            pnu TEXT,
            address_norm TEXT,
            project_id TEXT,
            analysis_type TEXT NOT NULL,
            version INT NOT NULL,
            payload JSONB NOT NULL,
            content_hash TEXT NOT NULL,
            prev_hash TEXT,
            source TEXT,
            created_by TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_chain "
        "ON analysis_ledger(tenant_id, pnu, project_id, analysis_type, version DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ledger_addr "
        "ON analysis_ledger(tenant_id, address_norm, analysis_type, version DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_ledger_quota (
            tenant_id TEXT PRIMARY KEY,
            max_entries INT NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    # 원장은 무결성·계보 자산 — 자동 DROP 금지(데이터 소실 방지). 필요 시 운영자가 수동 처리.
    pass
```

> **DDL 일치 주의**: 위 DDL은 `analysis_ledger_service.py`의 `_DDL`/`_IDX`/`_QUOTA_DDL`(line 23~52)과 컬럼·인덱스가 **정확히 일치**해야 한다. 작성 후 두 정의를 나란히 비교(diff)해 1자도 다르지 않은지 확인할 것.

- [ ] **Step 4: 세션 간 영속 테스트 추가(DB 있을 때) — "재시작 후 0건 소실" 수용기준**

`apps/api/tests/ledger/test_migration_031.py` 끝에 추가:

```python
async def test_append_persists_across_sessions(tnt):
    """원장 append는 별도(=재오픈) 세션에서도 읽힌다 = 영속(재시작 후 소실 0)."""
    from app.services.ledger import analysis_ledger_service as ledger

    res = await ledger.append_analysis(
        analysis_type="site_analysis",
        payload={"gfa": 75000, "note": "persist-check"},
        tenant_id=tnt, pnu="1111010100100010000",
        source="quick", created_by="tester",
    )
    assert res["ok"] is True and res["version"] == 1

    # get_latest 는 새로운 async_session_factory() 세션을 연다 → 영속이면 읽혀야 함.
    latest = await ledger.get_latest(
        analysis_type="site_analysis", tenant_id=tnt, pnu="1111010100100010000",
    )
    assert latest is not None
    assert latest["payload"]["gfa"] == 75000
    assert latest["version"] == 1
```

> `tnt` 픽스처(Task 0)는 `tests/ledger/conftest.py`에서 자동 발견된다.

- [ ] **Step 5: 실행 — 통과(또는 DB 미가용 시 영속 테스트만 skip)**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_migration_031.py -q`
Expected: 연결 테스트 PASS. 영속 테스트는 DB 기동 시 PASS, 미기동 시 SKIP.

- [ ] **Step 6: (DB 있으면) 마이그레이션 멱등 적용 확인**

Run: `.venv/bin/python -m alembic upgrade head` 후 재실행 → 두 번째도 에러 없이 `head`. (멱등 확인. 배포 담당이 prod 적용하나 로컬에서 안전성 확인.)

- [ ] **Step 7: Commit**

```
printf '%s\n' 'feat(ledger): formalize analysis_ledger schema as alembic 031 (Phase 0 unit b1)' '' '런타임 lazy-DDL(_ensure)을 버전관리 마이그레이션으로 흡수 — 멱등(IF NOT EXISTS)이라 공존.' '세션 간 영속(재시작 후 소실 0) 통합테스트 추가.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add apps/api/database/migrations/versions/031_analysis_ledger.py apps/api/tests/ledger/test_migration_031.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 2.5: `_chain_where` NULL-safe 버그픽스 carve-out (무결성 정합 선결)

**근거(시뮬레이션 확정, high)**: `analysis_ledger_service.py`의 `_chain_where`는 pnu가 없을 때 `address_norm = :addr`(addr=`''`)로 조회하지만, INSERT는 `address_norm or None`으로 **NULL을 저장**한다. Postgres 3치논리상 `address_norm = ''`는 NULL 행을 못 잡으므로 **pnu·address가 둘 다 없고 project_id만 있는 체인**(Task 5의 feasibility/domain_agent 어댑터, 기존 billing/commission/termination_cert 호출처)은 매 append마다 version=1로 평탄화되고 get_latest/verify_chain이 0건/오탐이 된다. 고치지 않으면 unit d의 'project별 원장 일원화'와 Phase 1 read 루프가 출발부터 비기능 → **불변규칙2 carve-out**으로 단일 교정.

**Files:**
- Modify: `apps/api/app/services/ledger/analysis_ledger_service.py` (`_chain_where` else 분기만)
- Test: `apps/api/tests/ledger/test_chain_where.py`

- [ ] **Step 1: 회귀 테스트(실패) 작성**

`apps/api/tests/ledger/test_chain_where.py`:
```python
"""project_id-only(또는 빈 주소) 체인이 NULL-safe로 연결되는지 — _chain_where 버그픽스 회귀."""


async def test_project_only_chain_links_versions(tnt):
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
    assert r2["version"] == 2 and r2["unchanged"] is False     # 현재(버그)는 1,1로 평탄화

    latest = await ledger.get_latest(
        analysis_type="feasibility", tenant_id=tnt, project_id="PRJ-NULLSAFE",
    )
    assert latest is not None and latest["version"] == 2

    v = await ledger.verify_chain(
        analysis_type="feasibility", tenant_id=tnt, project_id="PRJ-NULLSAFE",
    )
    assert v["verified"] is True and v["length"] == 2          # 현재(버그)는 chain_broken 오탐
```

- [ ] **Step 2: 실행 — 실패 확인(DB 있을 때; 없으면 SKIP)**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_chain_where.py -q`
Expected: FAIL — `version==2` 단언에서 실패(현재는 1,1). DB 미가용 시 SKIP(그 경우 Step 4에서 DB 기동 후 확인).

- [ ] **Step 3: `_chain_where` else 분기 NULL-safe 교정**

`apps/api/app/services/ledger/analysis_ledger_service.py`의 `_chain_where`를 연다. 현재 else 분기는 pnu가 없으면 무조건 `address_norm = :addr`를 쓴다. 빈 주소일 때 `address_norm IS NULL`로 분기하도록 교정한다(read/write/verify 전 경로가 같은 `_chain_where`를 쓰므로 한 곳 수정이 전체를 정합화):

교정 후 키 선택 로직(의미 — 실제 파일의 변수명·들여쓰기를 그대로 따를 것):
```python
    if pnu:
        key_sql = "pnu = :pnu"
        params["pnu"] = pnu
    elif address_norm:                       # 비어있지 않은 주소만 동등 비교
        key_sql = "address_norm = :addr"
        params["addr"] = address_norm
    else:                                    # pnu·address 모두 없음 → NULL 저장행과 정합
        key_sql = "address_norm IS NULL"
    # project_id 분기는 기존과 동일(있으면 "AND project_id = :pid", 없으면 "AND project_id IS NULL")
```
> ⚠️ pnu·address·project_id가 **전부 없을 때**는 의도된 키가 아니다 — 호출부(어댑터/라우터)는 이미 project_id를 주거나(어댑터) audit는 합성주소를 준다(전부-NULL 단일 거대 체인 오염 방지). 빈문자열이 영구저장된 적 없음(유일 INSERT가 `or None`)을 확인했으므로 완전 backward-compatible.

- [ ] **Step 4: 실행 — 통과 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_chain_where.py -q`
Expected: DB 기동 시 PASS(version 1,2 연결·verified). 미기동 시 SKIP.

- [ ] **Step 5: 기존 project-only 호출처 회귀 확인**

`get_latest`/`verify_chain`이 project-only로 호출되는 기존 경로가 교정으로 깨지지 않는지(오히려 복구) 확인:
```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && grep -rn "get_latest\|verify_chain" apps/api/app/services/cost apps/api/app/api/endpoints/sales apps/api/app/routers/pipeline.py --include="*.py"'
```
관련 기존 테스트가 있으면 명시 실행. 교정은 NULL 행을 '못 보던' 것을 '보게' 하는 방향이라 동작을 더 정확하게 만든다 — 평탄화 값을 기대하는 테스트가 있으면 그 테스트가 결함 동결이므로 함께 교정(정직 명시).

- [ ] **Step 6: Commit**
```
printf '%s\n' 'fix(ledger): NULL-safe _chain_where for project-only chains (Phase 0 carve-out)' '' '기존 _chain_where는 pnu 없을 때 address_norm=:addr(빈문자열)로 조회하나 INSERT는 NULL 저장 →' 'project_id-only 체인이 매 append마다 version=1로 평탄화·verify 오탐. else 분기를 NULL-safe로 교정' '(빈문자열 영구저장 이력 0 → backward-compatible). 불변규칙2 버그픽스 carve-out.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add apps/api/app/services/ledger/analysis_ledger_service.py apps/api/tests/ledger/test_chain_where.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

> **동시 append 경쟁조건(시뮬레이션 high) — 탐지만 Phase 0, 예방은 Phase 1**: `append_analysis`는 `SELECT max(version) → INSERT`를 잠금·유니크 제약 없이 수행 → 동일 체인 동시 append 시 version 중복·체인 포크 가능. 단 **UNIQUE 제약 추가는 위 NULL 버그로 이미 적재된 레거시 중복행(project-only version=1 다수)과 충돌**해 마이그레이션이 실패하므로 Phase 0에서 도입하지 않는다(데이터 정리 후 별도 task). Phase 0은 Task 3 `verify_all_chains`에 `duplicate_version` **탐지**를 넣어 포크를 사후 보고하는 데까지만 한다(불변규칙3·위험0).

---

## Task 3: 전 체인 일괄검증 `verify_all_chains` + `GET /verify-all` (unit c)

**근거**: 단건 체인 `GET /verify`는 이미 존재(`analysis_ledger.py:83`). 부재한 것은 수용기준 "verify_chain이 **전 프로젝트** '변조 없음' 반환"을 충족하는 **테넌트/프로젝트 전 체인 일괄검증**. 기존 `verify_chain`은 **건드리지 않고**(위험 0) 신규 함수만 추가, 단건 결과와 일치함을 회귀로 박제.

**Files:**
- Modify: `apps/api/app/services/ledger/analysis_ledger_service.py` (함수 1개 추가)
- Modify: `apps/api/app/routers/analysis_ledger.py` (엔드포인트 1개 추가)
- Test: `apps/api/tests/ledger/test_verify_all.py`

- [ ] **Step 1: 통합 테스트(실패) 작성**

`apps/api/tests/ledger/test_verify_all.py`:

```python
"""verify_all_chains — 다중 체인 일괄검증 + 변조탐지 + 단건 verify 일치 회귀."""
from sqlalchemy import text


async def _seed(tnt):
    from app.services.ledger import analysis_ledger_service as ledger

    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"gfa": 1000},
        tenant_id=tnt, pnu="PNU-A", source="quick",
    )
    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"gfa": 1200},
        tenant_id=tnt, pnu="PNU-A", source="quick",
    )
    await ledger.append_analysis(
        analysis_type="feasibility", payload={"npv": 50},
        tenant_id=tnt, project_id="PRJ-1", source="project",
    )


async def test_all_clean_chains_verified(tnt):
    from app.services.ledger import analysis_ledger_service as ledger

    await _seed(tnt)
    res = await ledger.verify_all_chains(tenant_id=tnt)
    assert res["ok"] is True
    assert res["verified"] is True
    assert res["chains_checked"] == 2          # site_analysis(PNU-A) + feasibility(PRJ-1)
    assert res["broken_chains"] == []


async def test_tampered_payload_detected(tnt, ledger_db):
    from app.services.ledger import analysis_ledger_service as ledger

    await _seed(tnt)
    # payload 직접 변조(content_hash 불일치 유발).
    await ledger_db.execute(
        text(
            "UPDATE analysis_ledger SET payload = CAST(:p AS jsonb) "
            "WHERE tenant_id = :t AND pnu = 'PNU-A' AND version = 1"
        ),
        {"p": '{"gfa": 999999}', "t": tnt},
    )
    await ledger_db.commit()

    res = await ledger.verify_all_chains(tenant_id=tnt)
    assert res["verified"] is False
    assert any(c["analysis_type"] == "site_analysis" for c in res["broken_chains"])


async def test_project_filter_and_agreement_with_single_verify(tnt):
    from app.services.ledger import analysis_ledger_service as ledger

    await _seed(tnt)
    # project 필터: feasibility 체인만.
    res = await ledger.verify_all_chains(tenant_id=tnt, project_id="PRJ-1")
    assert res["chains_checked"] == 1
    assert res["verified"] is True
    # 단건 verify_chain 과 일치(회귀): 동일 체인은 동일 판정.
    single = await ledger.verify_chain(
        analysis_type="feasibility", tenant_id=tnt, project_id="PRJ-1"
    )
    assert single["verified"] is True


async def test_pnu_chain_with_mixed_address_is_single_chain(tnt):
    """같은 pnu에 address 유/무가 섞여도 _chain_where(pnu 우선)와 동일하게 한 체인으로 검증(G5 회귀)."""
    from app.services.ledger import analysis_ledger_service as ledger

    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"v": 1},
        tenant_id=tnt, pnu="PNU-MIX", address="서울 어딘가", source="quick",
    )
    await ledger.append_analysis(
        analysis_type="site_analysis", payload={"v": 2},
        tenant_id=tnt, pnu="PNU-MIX", source="quick",        # address 미지정
    )
    res = await ledger.verify_all_chains(tenant_id=tnt)
    mix = [c for c in res["broken_chains"] if c["pnu"] == "PNU-MIX"]
    assert mix == []                                          # pnu 우선 → 끊김 오탐 없음
    single = await ledger.verify_chain(
        analysis_type="site_analysis", tenant_id=tnt, pnu="PNU-MIX"
    )
    assert single["verified"] is True and single["length"] == 2


async def test_duplicate_version_detected(tnt, ledger_db):
    """동시 append 경쟁조건 사후탐지 — 같은 version 2행이면 duplicate_version 보고."""
    from sqlalchemy import text
    from app.services.ledger import analysis_ledger_service as ledger

    await ledger.append_analysis(
        analysis_type="permit", payload={"x": 1},
        tenant_id=tnt, pnu="PNU-DUP", source="quick",
    )
    # version=1 행을 복제(잠금 부재 경쟁조건 시뮬레이션).
    await ledger_db.execute(text(
        "INSERT INTO analysis_ledger(tenant_id, pnu, analysis_type, version, payload, content_hash) "
        "SELECT tenant_id, pnu, analysis_type, version, payload, content_hash FROM analysis_ledger "
        "WHERE tenant_id = :t AND pnu = 'PNU-DUP'"), {"t": tnt})
    await ledger_db.commit()

    res = await ledger.verify_all_chains(tenant_id=tnt)
    dup = [c for c in res["broken_chains"]
           if c["pnu"] == "PNU-DUP" and any(b["issue"] == "duplicate_version" for b in c["broken"])]
    assert dup, "동일 version 중복이 duplicate_version으로 탐지돼야 함"
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_verify_all.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'verify_all_chains'` (DB 미가용이면 SKIP — 그 경우 Step 6에서 DB 기동 후 재확인).

- [ ] **Step 3: `verify_all_chains` 추가 — 파일 끝에 append**

`apps/api/app/services/ledger/analysis_ledger_service.py` 맨 끝에 추가(기존 함수·`verify_chain` 불변):

```python
async def verify_all_chains(
    *, tenant_id: str | None = None, project_id: str | None = None,
) -> dict[str, Any]:
    """테넌트(옵션: 프로젝트)의 모든 체인을 일괄 무결성 검증.

    단일 패스 SELECT로 전 행을 읽어(N+1 라운드트립 제거) 파이썬에서 verify_chain과 '동일한 체인 키
    규칙'(_chain_where: pnu 있으면 pnu, 없으면 address_norm; +project_id, analysis_type)으로 그룹핑해
    검증한다 → 단건 verify_chain과 판정 일치. 검증은 prev_hash 연속성 + content_hash 재계산에 더해
    동일 version 중복(동시 append 경쟁조건 사후탐지)까지 본다. 기존 verify_chain은 불변(별도 함수).
    """
    try:
        from sqlalchemy import text
        from app.core.database import async_session_factory

        async with async_session_factory() as db:
            await _ensure(db)
            tenant_sql = "tenant_id = :tid" if tenant_id else "tenant_id IS NULL"
            params: dict[str, Any] = {"tid": tenant_id}
            proj_sql = ""
            if project_id:
                proj_sql = " AND project_id = :pid"
                params["pid"] = project_id
            rows = (await db.execute(text(
                f"SELECT pnu, address_norm, project_id, analysis_type, version, "
                f"payload, content_hash, prev_hash FROM analysis_ledger "
                f"WHERE {tenant_sql}{proj_sql}"), params)).all()

            # _chain_where와 동일한 체인 키(pnu 우선, 없으면 address_norm)로 그룹핑.
            chains: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
            for r in rows:
                pnu_v, addr_v, pid_v, atype = r[0], r[1], r[2], r[3]
                pnu_key = pnu_v or None    # 빈문자열 pnu도 address 분기로(=_chain_where `if pnu:` 동형)
                key = (pnu_key if pnu_key is not None else f"@addr:{addr_v}", pid_v, atype)
                chains.setdefault(key, {
                    "pnu": pnu_v, "address_norm": addr_v, "project_id": pid_v,
                    "analysis_type": atype, "rows": [],
                })["rows"].append((int(r[4]), r[5], r[6], r[7]))

            broken_chains: list[dict[str, Any]] = []
            for ch in chains.values():
                broken: list[dict[str, Any]] = []
                prev_hash = None
                seen: set[int] = set()
                for ver, payload, stored_hash, ph in sorted(ch["rows"], key=lambda x: x[0]):
                    if ver in seen:
                        broken.append({"version": ver, "issue": "duplicate_version"})
                    seen.add(ver)
                    if _content_hash(payload) != stored_hash:
                        broken.append({"version": ver, "issue": "payload_tampered"})
                    if ph != prev_hash:
                        broken.append({"version": ver, "issue": "chain_broken"})
                    prev_hash = stored_hash
                if broken:
                    broken_chains.append({
                        "analysis_type": ch["analysis_type"], "pnu": ch["pnu"],
                        "address_norm": ch["address_norm"], "project_id": ch["project_id"],
                        "broken": broken,
                    })

            return {
                "ok": True, "verified": not broken_chains,
                "chains_checked": len(chains), "broken_chains": broken_chains,
                "message": ("전 체인 무결성 정상(변조 없음)" if not broken_chains
                            else f"무결성 이상 체인 {len(broken_chains)}건 탐지"),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("분석원장 전체검증 실패", err=str(e)[:160])
        return {"ok": False, "message": str(e)[:160]}
```

- [ ] **Step 4: 엔드포인트 추가 — `GET /verify-all`**

`apps/api/app/routers/analysis_ledger.py`의 기존 `verify`(line 83~93) 핸들러 **바로 다음**에 추가:

```python
@router.get("/verify-all", summary="전 체인 무결성 일괄검증(테넌트/프로젝트)")
async def verify_all(
    project_id: str | None = None,
    current: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return await ledger.verify_all_chains(tenant_id=_tid(current), project_id=project_id)
```

- [ ] **Step 5: 실행 — 통과 확인(서비스 함수)**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_verify_all.py -q`
Expected: DB 기동 시 `5 passed`(clean·tamper·project필터·mixed주소·duplicate탐지); 미기동 시 `5 skipped`.

- [ ] **Step 6: 라우터 import 무결성 확인(엔드포인트 등록)**

Run (apps/api에서): `PYTHONPATH=../.. INTERP_REDIS_CACHE=0 .venv/bin/python -c "from app.routers.analysis_ledger import router; print([r.path for r in router.routes if 'verify' in r.path])"`
(repo 루트를 `PYTHONPATH=../..`로 주입 — 라우터가 `apps.api.*`를 import하므로 필수. 생략 시 `ModuleNotFoundError: No module named 'apps'`.)
Expected: `['/api/v1/analysis-ledger/verify', '/api/v1/analysis-ledger/verify-all']` 둘 다 출력.

- [ ] **Step 7: 기존 원장 테스트 회귀(있다면) + audit 테스트 무손상 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/test_audit_service.py -q`
Expected: 기존 `test_audit_service.py` 전부 PASS(불변 확인).

- [ ] **Step 8: Commit**

```
printf '%s\n' 'feat(ledger): add verify_all_chains sweep + GET /verify-all (Phase 0 unit c)' '' '단건 /verify는 기존 존재 — 테넌트/프로젝트 전 체인 일괄검증을 신규 추가(verify_chain 불변).' '변조탐지·project 필터·단건 일치 회귀 통합테스트.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add apps/api/app/services/ledger/analysis_ledger_service.py apps/api/app/routers/analysis_ledger.py apps/api/tests/ledger/test_verify_all.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 4: 감사 이벤트 → 원장 흡수 (unit b2)

**근거**: in-memory `AuditTrailService`(SHA256 체인)는 prod 미사용 dead code(실측). 무결성 단일화 = 감사 이벤트를 원장에 `analysis_type="audit"`로 누적(단일 체인·단일 verify). 감사 체인 키는 안정적·비-NULL이어야 하므로 합성 주소 `__audit__/<tenant>`를 사용(원장의 빈-주소 NULL 키 함정 회피). 각 이벤트는 `event_id`/`event_ts`로 유일 → 멱등 dedup에 삼켜지지 않음.

**Files:**
- Create: `apps/api/app/services/ledger/audit_ledger.py`
- Modify: `apps/api/app/services/audit/audit_service.py` (docstring 표기만)
- Modify: `apps/api/app/core/audit.py` (`audit_admin_action` 말미에 원장 흡수 배선 — admin 감사 6곳)
- Modify: `apps/api/services/audit_service.py` (`record_audit` 말미에 원장 흡수 배선 — legal 감사 4곳)
- Test: `apps/api/tests/ledger/test_audit_ledger.py`

> **⚠️ 단일화 핵심**: 흡수 함수(`append_audit`)를 만들기만 하고 배선하지 않으면 호출처 0건 = 데드코드 재발(과거 `AuditTrailService`와 동일 함정). Step 4b·4c가 실제 감사 발생 10곳(`audit_admin_action` 6 + `record_audit` 4)을 원장으로 흡수해야 unit b의 '단일 SSOT'가 비로소 완성된다.

- [ ] **Step 1: 순수 로직 + 통합 테스트(실패) 작성**

`apps/api/tests/ledger/test_audit_ledger.py`:

```python
"""감사 흡수 — 순수 payload/키 함수(무DB) + 원장 누적·검증(DB)."""


def test_audit_stream_address_stable_and_nonempty():
    from app.services.ledger.audit_ledger import audit_stream_address

    assert audit_stream_address("t1") == "__audit__/t1"
    assert audit_stream_address(None) == "__audit__/global"
    # 같은 입력 = 같은 키(안정).
    assert audit_stream_address("t1") == audit_stream_address("t1")


def test_build_audit_payload_is_deterministic():
    from app.services.ledger.audit_ledger import build_audit_payload

    p = build_audit_payload(
        action="EXPORT", resource_type="project", resource_id="p1",
        user_id="u1", event_id="e1", event_ts=123.0,
        changes={"k": "v"}, metadata={"ip": "1.2.3.4"},
    )
    assert p == {
        "kind": "audit", "action": "EXPORT", "resource_type": "project",
        "resource_id": "p1", "user_id": "u1", "event_id": "e1", "event_ts": 123.0,
        "changes": {"k": "v"}, "metadata": {"ip": "1.2.3.4"},
    }
    # None → 빈 dict 정규화.
    p2 = build_audit_payload(
        action="LOGIN", resource_type="user", resource_id="u1",
        user_id="u1", event_id="e2", event_ts=1.0,
    )
    assert p2["changes"] == {} and p2["metadata"] == {}


async def test_append_audit_persists_and_verifies(tnt):
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger import audit_ledger

    r1 = await audit_ledger.append_audit(
        action="CREATE", user_id="u1", resource_type="project", resource_id="p1",
        tenant_id=tnt, changes={"name": "n1"},
    )
    r2 = await audit_ledger.append_audit(
        action="UPDATE", user_id="u1", resource_type="project", resource_id="p1",
        tenant_id=tnt, changes={"name": "n2"},
    )
    assert r1["ok"] and r2["ok"]
    # 서로 다른 이벤트 → 멱등 dedup에 삼켜지지 않고 버전 증가.
    assert r1["version"] == 1 and r2["version"] == 2 and r2["unchanged"] is False

    v = await audit_ledger.verify_audit_chain(tenant_id=tnt)
    assert v["verified"] is True and v["length"] == 2
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_audit_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError: ...audit_ledger`.

- [ ] **Step 3: `audit_ledger.py` 작성**

`apps/api/app/services/ledger/audit_ledger.py`:

```python
"""감사 이벤트 → 분석원장(analysis_ledger) 단일 SSOT 흡수.

무결성 단일화(Phase 0 unit b): in-memory AuditTrailService의 별도 SHA256 해시체인을 폐기하고,
모든 감사 이벤트를 원장에 analysis_type='audit'로 누적한다(단일 체인·단일 verify_chain).

체인 키: 합성 주소 '__audit__/<tenant>'(비-NULL·안정 — 원장의 빈-주소 NULL 키 함정 회피).
각 이벤트는 event_id/event_ts로 유일 → 원장의 멱등 dedup에 삼켜지지 않음.
정직·best-effort: append 실패가 본 작업을 막지 않음(호출부는 반환 dict의 ok만 확인).
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from app.services.ledger import analysis_ledger_service as ledger

AUDIT_ANALYSIS_TYPE = "audit"


def audit_stream_address(tenant_id: str | None) -> str:
    """테넌트별 감사 체인 키(합성 주소, 비-NULL·안정)."""
    return f"__audit__/{tenant_id or 'global'}"


def build_audit_payload(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    user_id: str | None,
    event_id: str,
    event_ts: float,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """감사 1건의 결정적 원장 payload. event_id/event_ts는 호출부 주입(테스트 결정성)."""
    return {
        "kind": "audit",
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "user_id": user_id,
        "event_id": event_id,
        "event_ts": event_ts,
        "changes": changes or {},
        "metadata": metadata or {},
    }


async def append_audit(
    *,
    action: str,
    user_id: str | None,
    resource_type: str,
    resource_id: str,
    tenant_id: str | None = None,
    changes: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """감사 이벤트 1건을 원장에 append(analysis_type='audit'). best-effort."""
    payload = build_audit_payload(
        action=action, resource_type=resource_type, resource_id=resource_id,
        user_id=user_id, event_id=uuid.uuid4().hex, event_ts=time.time(),
        changes=changes, metadata=metadata,
    )
    return await ledger.append_analysis(
        analysis_type=AUDIT_ANALYSIS_TYPE, payload=payload,
        tenant_id=tenant_id, address=audit_stream_address(tenant_id),
        source="audit", created_by=user_id,
    )


async def verify_audit_chain(*, tenant_id: str | None = None) -> dict[str, Any]:
    """테넌트 감사 체인 무결성 검증(원장 verify_chain 위임)."""
    return await ledger.verify_chain(
        analysis_type=AUDIT_ANALYSIS_TYPE, tenant_id=tenant_id,
        address=audit_stream_address(tenant_id),
    )
```

- [ ] **Step 4: 레거시 표기 — `AuditTrailService` docstring에 비-SSOT 명시(로직 불변)**

`apps/api/app/services/audit/audit_service.py`의 `class AuditTrailService:` docstring을 교체(로직·메서드 일절 불변, 문구만):

기존:
```python
class AuditTrailService:
    """불변 감사 추적 (append-only, SHA-256 해시 체인)."""
```
변경:
```python
class AuditTrailService:
    """불변 감사 추적 (append-only, SHA-256 해시 체인).

    ⚠️ 레거시·비-SSOT: 본 클래스는 in-memory 전용(영속 없음)이며 무결성 SSOT가 아니다.
    영속 감사 경로는 app.services.ledger.audit_ledger.append_audit(원장 흡수, Phase 0)다.
    하위호환을 위해 보존하되 신규 코드는 audit_ledger를 사용할 것.
    """
```

- [ ] **Step 4b: 배선 — `audit_admin_action`(admin 감사 6곳) 원장 흡수**

`apps/api/app/core/audit.py`의 `audit_admin_action`은 이미 `async_session_factory`로 `admin_audit_log`에 best-effort 적재한다(호출처 6곳: `admin_secrets.py:87,109,128,159`·`analysis_ledger.py:132`·`routers/billing.py:181`). 그 `await db.commit()` 직후에 원장 흡수를 추가(무한루프 없음 — `append_analysis`는 `audit_admin_action`을 호출하지 않음):
```python
    # Phase 0 unit b2: admin 감사 이벤트를 원장 단일 SSOT에도 흡수(best-effort, 실패 무중단).
    try:
        from app.services.ledger.audit_ledger import append_audit
        await append_audit(
            action=action, user_id=actor_id, resource_type="admin",
            resource_id=target, tenant_id=tenant_id,
            metadata={"actor_role": actor_role, "detail": detail or {}},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("감사 원장 흡수 실패", action=action, err=str(e)[:120])
```
(`audit.py`엔 이미 module-level `logger`가 있음 — 확인 후 사용.)

- [ ] **Step 4c: 배선 — `record_audit`(legal 감사 4곳) 원장 흡수**

`apps/api/services/audit_service.py`의 `record_audit`(→`legal_audit_trail`, 호출처 4곳 `routers/projects.py:161,210,250,280`)의 본체 INSERT/flush 성공 후 return 직전에 best-effort 흡수를 추가(실측 시그니처 `entity_type`/`entity_id`/`actor_id`/`before_state`/`after_state`/`reason`/`ip_address` 정합):
```python
    # Phase 0 unit b2: legal 감사 이벤트를 원장 단일 SSOT에도 흡수(best-effort).
    try:
        from app.services.ledger.audit_ledger import append_audit
        await append_audit(
            action=action, user_id=str(actor_id), resource_type=entity_type,
            resource_id=str(entity_id), tenant_id=str(tenant_id),
            changes={"before": before_state, "after": after_state},
            metadata={"reason": reason, "ip_address": ip_address},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("감사 원장 흡수 실패", err=str(e)[:120])
```
> ⚠️ `services/audit_service.py`에 module-level `logger`가 없으면 상단에 `import structlog` + `logger = structlog.get_logger(__name__)` 추가. 본체 감사 기록이 성공한 뒤(반환 직전) 호출해 원장 적재 실패가 legal 감사를 막지 않도록 try 분리.

- [ ] **Step 5: 실행 — 통과 + 배선 존재 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_audit_ledger.py tests/test_audit_service.py -q`
Expected: 순수 테스트 2개 PASS(무조건), 감사-원장 통합 1개 PASS(DB 기동) 또는 SKIP. 기존 `test_audit_service.py` 전부 PASS(레거시 불변 확인).

배선 존재(데드코드 아님) 확인:
```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && grep -rln "append_audit" apps/api --include="*.py" | grep -v /tests/'
```
Expected: `app/core/audit.py`·`services/audit_service.py`(+정의 파일 `audit_ledger.py`)가 출력 — 프로덕션 호출처 ≥2.

- [ ] **Step 6: Commit**

```
printf '%s\n' 'feat(ledger): absorb audit events into ledger + wire 10 call sites (Phase 0 unit b2)' '' 'in-memory AuditTrailService(prod 미사용 dead code)의 별도 해시체인 폐기 — 감사 이벤트를' '원장 단일 SSOT로 흡수(audit_ledger). audit_admin_action(6)·record_audit(4) 실호출처에 best-effort' '배선해 데드코드 재발 방지. 레거시는 비-SSOT 표기·보존.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add apps/api/app/services/ledger/audit_ledger.py apps/api/app/services/audit/audit_service.py apps/api/app/core/audit.py apps/api/services/audit_service.py apps/api/tests/ledger/test_audit_ledger.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 5: 산출물→원장 어댑터 (unit d) — 순수 매퍼 + 기록 래퍼

**근거**: spec unit(d) "design_audits·feasibility_vcs·DomainAgentTask 산출물을 ledger append 경로로 일원화하는 어댑터(기존 테이블 유지)". 실측상 `append_analysis` 호출처에 이 셋이 없음. 매퍼는 **순수 함수**(무DB·결정적)로 만들어 직접 단위테스트, 기록 래퍼는 best-effort append.

> **⚠️ analysis_type 분리(시뮬레이션 확정 high)**: feasibility 커밋 메타는 `analysis_type="feasibility_vcs"`로 적재한다. read 성장루프(`bank_report`·`pipeline`의 `_LEDGER_TYPE_TO_KEY`/`_LEDGER_TYPE_TO_STAGE`)가 `"feasibility"`를 **재무 분석값의 권위 키**로 소비하므로, git-커밋 요약(`{kind,sha,...}`)을 같은 키로 넣으면 리포트의 total_revenue/net_profit가 None으로 오염된다. design_audit/domain_agent은 read 키와 무충돌이라 그대로.
> **⚠️ pipeline.py:425 전제 정정**: `pipeline.py:425`는 **interpreter stage** 적재이지 8엔진 design_audit raw 적재가 아니다 — design_audit 원장 흡수는 Task 6 Step 3의 직접 호출 경로(2곳) 배선에 **전적으로 의존**한다(파이프라인이 대신 적재해 주지 않는다).

**Files:**
- Create: `apps/api/app/services/ledger/ledger_adapters.py`
- Test: `apps/api/tests/ledger/test_ledger_adapters.py`

- [ ] **Step 1: 순수 매퍼 테스트(실패) 작성**

`apps/api/tests/ledger/test_ledger_adapters.py`:

```python
"""산출물→원장 어댑터 — 순수 매퍼(무DB) + 기록 래퍼(DB)."""


def test_design_audit_to_ledger_extracts_core_fields():
    from app.services.ledger.ledger_adapters import design_audit_to_ledger

    result = {
        "schema_version": "design_audit/v1",
        "zone_type": "제2종일반주거",
        "sigungu": "강남구",
        "overall": {"verdict": "조건부적합", "counts": {"pass": 5, "warning": 2}},
        "engines": {"far": "ok", "bcr": "ok"},
        "findings": [{"check_id": "far_limit"}, {"check_id": "height"}],
    }
    p = design_audit_to_ledger(result)
    assert p == {
        "kind": "design_audit",
        "schema_version": "design_audit/v1",
        "zone_type": "제2종일반주거",
        "sigungu": "강남구",
        "verdict": "조건부적합",
        "counts": {"pass": 5, "warning": 2},
        "engines": {"far": "ok", "bcr": "ok"},
        "findings_count": 2,
    }


def test_design_audit_to_ledger_tolerates_missing_keys():
    from app.services.ledger.ledger_adapters import design_audit_to_ledger

    p = design_audit_to_ledger({})
    assert p["kind"] == "design_audit"
    assert p["verdict"] is None and p["counts"] == {} and p["findings_count"] == 0


def test_feasibility_commit_to_ledger():
    from app.services.ledger.ledger_adapters import feasibility_commit_to_ledger

    commit = {
        "sha": "abc123", "parent_sha": "def456",
        "message": "init", "author": "u1", "timestamp": "2026-06-15T00:00:00",
    }
    p = feasibility_commit_to_ledger(commit)
    assert p == {
        "kind": "feasibility_commit",
        "sha": "abc123", "parent_sha": "def456",
        "message": "init", "author": "u1", "timestamp": "2026-06-15T00:00:00",
    }


def test_domain_agent_task_to_ledger():
    from app.services.ledger.ledger_adapters import domain_agent_task_to_ledger

    task = {
        "domain": "finance", "task_type": "analysis", "status": "completed",
        "confidence_score": 0.82, "recommendation": "review",
        "requires_approval": True,
    }
    p = domain_agent_task_to_ledger(task)
    assert p == {
        "kind": "domain_agent_task",
        "domain": "finance", "task_type": "analysis", "status": "completed",
        "confidence_score": 0.82, "recommendation": "review",
        "requires_approval": True,
    }


async def test_record_design_audit_appends_to_ledger(tnt):
    from app.services.ledger import analysis_ledger_service as ledger
    from app.services.ledger.ledger_adapters import record_design_audit

    res = await record_design_audit(
        result={"schema_version": "design_audit/v1", "overall": {"verdict": "적합"}},
        tenant_id=tnt, project_id="PRJ-9", created_by="u1",
    )
    assert res["ok"] is True
    latest = await ledger.get_latest(
        analysis_type="design_audit", tenant_id=tnt, project_id="PRJ-9"
    )
    assert latest is not None and latest["payload"]["verdict"] == "적합"
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_ledger_adapters.py -q`
Expected: FAIL — `ModuleNotFoundError: ...ledger_adapters`.

- [ ] **Step 3: `ledger_adapters.py` 작성**

`apps/api/app/services/ledger/ledger_adapters.py`:

```python
"""산출물 → 분석원장 어댑터(Phase 0 unit d).

design_audit(8엔진)·feasibility 커밋·domain_agent 태스크의 산출물을 원장 append payload로
정규화하는 순수 매퍼 + best-effort 기록 래퍼. 기존 테이블/모델은 그대로 두고(불변) 원장에
'추가로' 일원화한다(요약·핵심 필드만 — 원시 대용량은 기존 테이블에 잔류).
"""
from __future__ import annotations

from typing import Any

from app.services.ledger import analysis_ledger_service as ledger


# ── 순수 매퍼(무DB·결정적) ──

def design_audit_to_ledger(result: dict[str, Any]) -> dict[str, Any]:
    """8엔진 design_audit 결과 dict → 원장 payload(핵심 요약)."""
    overall = result.get("overall") or {}
    return {
        "kind": "design_audit",
        "schema_version": result.get("schema_version"),
        "zone_type": result.get("zone_type"),
        "sigungu": result.get("sigungu"),
        "verdict": overall.get("verdict"),
        "counts": overall.get("counts") or {},
        "engines": result.get("engines") or {},
        "findings_count": len(result.get("findings") or []),
    }


def feasibility_commit_to_ledger(commit: dict[str, Any]) -> dict[str, Any]:
    """version_control_db.commit() 반환 dict → 원장 payload."""
    return {
        "kind": "feasibility_commit",
        "sha": commit.get("sha"),
        "parent_sha": commit.get("parent_sha"),
        "message": commit.get("message"),
        "author": commit.get("author"),
        "timestamp": commit.get("timestamp"),
    }


def domain_agent_task_to_ledger(task: dict[str, Any]) -> dict[str, Any]:
    """domain_agent 태스크 요약 dict → 원장 payload."""
    return {
        "kind": "domain_agent_task",
        "domain": task.get("domain"),
        "task_type": task.get("task_type"),
        "status": task.get("status"),
        "confidence_score": task.get("confidence_score"),
        "recommendation": task.get("recommendation"),
        "requires_approval": task.get("requires_approval"),
    }


# ── best-effort 기록 래퍼(원장 append) ──

async def record_design_audit(
    *, result: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, pnu: str | None = None,
    address: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type="design_audit", payload=design_audit_to_ledger(result),
        tenant_id=tenant_id, project_id=project_id, pnu=pnu, address=address,
        source="design_audit", created_by=created_by,
    )


async def record_feasibility_commit(
    *, commit: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    # ⚠️ analysis_type="feasibility_vcs" (NOT "feasibility") — read 루프의 재무 키와 분리(위 근거).
    return await ledger.append_analysis(
        analysis_type="feasibility_vcs", payload=feasibility_commit_to_ledger(commit),
        tenant_id=tenant_id, project_id=project_id,
        source="feasibility_vcs", created_by=created_by,
    )


async def record_domain_agent_task(
    *, task: dict[str, Any], tenant_id: str | None = None,
    project_id: str | None = None, created_by: str | None = None,
) -> dict[str, Any]:
    return await ledger.append_analysis(
        analysis_type="domain_agent", payload=domain_agent_task_to_ledger(task),
        tenant_id=tenant_id, project_id=project_id,
        source="domain_agents", created_by=created_by,
    )
```

- [ ] **Step 4: 실행 — 통과 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_ledger_adapters.py -q`
Expected: 순수 매퍼 4개 PASS(무조건), `record_design_audit` 통합 1개 PASS(DB) 또는 SKIP.

- [ ] **Step 5: Commit**

```
printf '%s\n' 'feat(ledger): add output->ledger adapters (design_audit/feasibility/domain_agent) (Phase 0 unit d)' '' '순수 매퍼(무DB·결정적) + best-effort 기록 래퍼. 기존 테이블 불변, 원장에 요약만 일원화 append.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add apps/api/app/services/ledger/ledger_adapters.py apps/api/tests/ledger/test_ledger_adapters.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 5.5: 원장 payload 규약 — schema_version + backlink + findings_brief (반복루프 전제)

**근거(시뮬레이션 medium, 반복루프 데이터품질)**: Phase 1 read 루프가 free-dict payload를 안전 파싱하려면 (a) `schema_version` 태깅, (b) 원본 테이블 역추적 backlink(`audit_id`/`sha`/`task_id`), (c) design_audit는 요약(verdict/counts)만 저장하면 재계산·비교 입력이 부족하므로 비교 핵심(`check_id`+`status`+`current`/`limit`)을 `findings_brief`로 보존해야 한다. Task 5 매퍼를 additive로 보강(`append_analysis` 시그니처 불변). Task 6 wiring이 `audit_id`를 넘기므로 **Task 5와 6 사이**에 둔다.

**Files:**
- Modify: `apps/api/app/services/ledger/ledger_adapters.py`·`audit_ledger.py`·tests(`test_ledger_adapters.py`/`test_audit_ledger.py`)

- [ ] **Step 1: 테스트 기대 갱신(실패) — schema_version + backlink + findings_brief + read-키 가드**

`test_ledger_adapters.py`에 추가:
```python
def test_design_audit_payload_has_schema_version_and_backlink_and_brief():
    from app.services.ledger.ledger_adapters import design_audit_to_ledger

    result = {
        "schema_version": "design_audit/v1",
        "overall": {"verdict": "조건부적합", "counts": {"pass": 1}},
        "findings": [{"check_id": "far_limit", "status": "warning", "current": 250, "limit": 200}],
    }
    p = design_audit_to_ledger(result, audit_id="AUD-1")
    assert p["schema_version"] == "design_audit/v1"
    assert p["audit_id"] == "AUD-1"
    assert p["findings_brief"] == [
        {"check_id": "far_limit", "status": "warning", "current": 250, "limit": 200},
    ]
    assert "audit_id" not in design_audit_to_ledger(result)   # 미지정 시 키 생략(가짜키 금지)


def test_adapter_types_do_not_collide_with_read_loop_keys():
    # read 성장루프(bank_report·pipeline)가 소비하는 키와 어댑터 analysis_type이 겹치면 리포트 오염.
    read_keys = {"feasibility", "site_analysis", "design", "esg", "permit"}
    adapter_types = {"design_audit", "feasibility_vcs", "domain_agent"}
    assert read_keys.isdisjoint(adapter_types)


def test_feasibility_and_domain_payload_have_schema_version():
    from app.services.ledger.ledger_adapters import (
        feasibility_commit_to_ledger, domain_agent_task_to_ledger)

    assert feasibility_commit_to_ledger({"sha": "x"})["schema_version"] == "feasibility_vcs/v1"
    assert domain_agent_task_to_ledger({"domain": "finance"})["schema_version"] == "domain_agent/v1"
```
`test_audit_ledger.py`의 `test_build_audit_payload_is_deterministic` 기대 dict에 `"schema_version": "audit/v1"`를 추가.

- [ ] **Step 2: 실행 — 실패 확인**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_ledger_adapters.py tests/ledger/test_audit_ledger.py -q`
Expected: FAIL(신규 키 부재).

- [ ] **Step 3: 매퍼 보강**

`ledger_adapters.py` `design_audit_to_ledger`를 교체:
```python
def design_audit_to_ledger(result: dict[str, Any], *, audit_id: str | None = None) -> dict[str, Any]:
    """8엔진 design_audit 결과 dict → 원장 payload(핵심 요약 + 비교용 findings_brief)."""
    overall = result.get("overall") or {}
    findings = result.get("findings") or []
    payload: dict[str, Any] = {
        "kind": "design_audit",
        "schema_version": result.get("schema_version") or "design_audit/v1",
        "zone_type": result.get("zone_type"),
        "sigungu": result.get("sigungu"),
        "verdict": overall.get("verdict"),
        "counts": overall.get("counts") or {},
        "engines": result.get("engines") or {},
        "findings_count": len(findings),
        # 비교·재계산 핵심만 보존(대용량 legal_refs/improvement 본문 제외).
        "findings_brief": [
            {"check_id": f.get("check_id"), "status": f.get("status"),
             "current": f.get("current"), "limit": f.get("limit")}
            for f in findings
        ],
    }
    if audit_id is not None:                 # 원본 design_audits 행 역추적(없으면 키 생략 — 정직)
        payload["audit_id"] = audit_id
    return payload
```
- `feasibility_commit_to_ledger` payload에 `"schema_version": "feasibility_vcs/v1"` 추가.
- `domain_agent_task_to_ledger` payload에 `"schema_version": "domain_agent/v1"` + `task`에 `id`가 있으면 `"task_id": task.get("id")` backlink 추가.
- `record_design_audit(*, result, audit_id: str | None = None, ...)`로 인자 추가해 매퍼에 전달.
- `audit_ledger.build_audit_payload` 반환 dict에 `"schema_version": "audit/v1"` 추가.

> ⚠️ Task 5 기존 매퍼 테스트(`test_design_audit_to_ledger_extracts_core_fields`·`..._tolerates_missing_keys`·`test_feasibility_commit_to_ledger`·`test_domain_agent_task_to_ledger`)는 키가 늘어 기대 dict가 달라지므로 **함께 갱신**(계약 진화 — 정직 명시).

- [ ] **Step 4: 실행 — 통과**

Run: `INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger/test_ledger_adapters.py tests/ledger/test_audit_ledger.py -q`
Expected: 전부 PASS(무DB 순수 테스트).

- [ ] **Step 5: Commit**
```
printf '%s\n' 'feat(ledger): payload regula — schema_version + backlink + findings_brief (Phase 0 loop-enabling)' '' '반복루프 read 전제: 신규 payload에 schema_version/kind, 원본 역추적 backlink(audit_id/task_id),' 'design_audit 비교핵심 findings_brief 보존. read-키 충돌 가드 테스트 추가.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add apps/api/app/services/ledger/ledger_adapters.py apps/api/app/services/ledger/audit_ledger.py apps/api/tests/ledger/test_ledger_adapters.py apps/api/tests/ledger/test_audit_ledger.py && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 6: 어댑터 배선 (unit d 마무리) — best-effort, 실패 무중단

**근거**: 어댑터는 호출돼야 통합이 완성된다. 배선은 **additive·best-effort**(try/except → **`logger.warning`**, 실패가 본 작업을 막지 않음 — 불변규칙3. ⚠️ `except: pass`는 silent-failure로 불변규칙3 위반이므로 금지). 시뮬레이션 보정 3건 반영: (1) `except`는 반드시 `logger.warning`(해당 파일에 module-level logger 없으면 추가), (2) **feasibility는 `commit()` 내부가 아니라 호출처에서 외부 트랜잭션 commit 이후** 배선(고아 레코드 방지 — Step 2), (3) **design_audit 직접 호출 경로는 2곳**이고 grep 스코프에 `services`를 포함해야 한다(Step 3). `pipeline.py:425`는 interpreter stage 적재라 design_audit raw를 대신 적재하지 않는다.

**Files:**
- Modify: `apps/api/services/domain_agents_service.py` (run_domain 배선 + logger)
- Modify: feasibility commit **호출처**(예: `apps/api/app/routers/v2_feasibility.py`) — `commit()` 본문은 불변, 호출처에서 `await db.commit()` 이후 배선
- Modify: design_audit 직접 호출 경로 2곳 — `apps/api/app/routers/design_audit.py`(+ `apps/api/app/services/collaboration/document_audit_service.py` 또는 그 호출처 `v2_collaboration.py`)

- [ ] **Step 1: `run_domain` 배선 — commit/refresh 직후, return 직전**

`apps/api/services/domain_agents_service.py`의 `run_domain` 말미, 기존:
```python
    await self.db.commit()
    await self.db.refresh(task)
    if approval is not None:
        await self.db.refresh(approval)
    return task, approval
```
를 다음으로 교체(원장 append 블록 추가 — best-effort). ⚠️ 전제: `domain_agents_service.py` 상단에 module-level logger가 없으면 `import structlog` + `logger = structlog.get_logger(__name__)`를 먼저 추가(아래 `logger.warning` 사용):
```python
    await self.db.commit()
    await self.db.refresh(task)
    if approval is not None:
        await self.db.refresh(approval)

    # Phase 0 unit d: 산출물 요약을 원장 단일 SSOT에 best-effort 일원화(실패 무중단).
    try:
        from app.services.ledger.ledger_adapters import record_domain_agent_task

        await record_domain_agent_task(
            task={
                "domain": task.domain, "task_type": task.task_type,
                "status": task.status, "confidence_score": task.confidence_score,
                "recommendation": task.recommendation,
                "requires_approval": task.requires_approval,
            },
            tenant_id=str(tenant_id), project_id=str(project_id),
            created_by=None,
        )
    except Exception as e:  # noqa: BLE001 — 원장 적재 실패가 도메인 분석을 막지 않음
        logger.warning("원장 배선 append 실패(domain_agent)", err=str(e)[:160])

    return task, approval
```

- [ ] **Step 2: `feasibility` 커밋 배선 — 호출처에서 `await db.commit()` 이후 (고아 레코드 방지)**

⚠️ `version_control_db.commit()`은 `self.db.flush()`만 하고 실제 트랜잭션 commit은 라우터의 `get_db`가 핸들러 반환 후 수행한다(파일 전체 `self.db.commit` 0회 — 실측). 원장 append를 `commit()` **내부**에 넣으면 별도 세션으로 즉시 commit된 원장행이 외부 트랜잭션 롤백 시 **고아**(존재하지 않는 sha를 가리킴 = SSOT 모순)가 된다. 그러므로 `commit()` 본문은 **불변**으로 두고, 호출처에서 외부 커밋이 확정된 뒤 배선한다.

호출처를 찾는다:
```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && grep -rn "vcs\.commit\|\.commit(" apps/api/app/routers/v2_feasibility.py --include="*.py"'
```
호출처(예: `v2_feasibility.py`의 vcs commit 핸들러)에서 `result = await vcs.commit(...)` 직후, 외부 트랜잭션을 명시 확정한 뒤 best-effort append(⚠️ 핸들러 파일에 logger 없으면 추가):
```python
    result = await vcs.commit(req.snapshot, req.message)
    await db.commit()                                  # 외부 트랜잭션 확정 — 이후에만 원장 적재(고아 방지)
    try:
        from app.services.ledger.ledger_adapters import record_feasibility_commit

        await record_feasibility_commit(
            commit=result,
            tenant_id=str(current_user.tenant_id),     # 실측: 핸들러엔 current_user.tenant_id뿐(bare tenant_id 없음)
            project_id=str(project_id),                # path param — 정합
            created_by=None,                           # 실측: 핸들러/요청에 author 변수 없음(commit 기본값 "")
        )
    except Exception as e:  # noqa: BLE001 — 원장 적재 실패가 커밋을 막지 않음
        logger.warning("원장 배선 append 실패(feasibility_vcs): %s", str(e)[:160])  # ⚠️ stdlib logger(:53) — err= kwarg 금지
```
> ⚠️ **실측 정합(시뮬레이션 재검증)**: `v2_feasibility.py:862` `vcs_commit` 핸들러엔 `current_user.tenant_id`만 있고 bare `tenant_id`·`author` 변수는 **없다**(NameError 방지). logger는 **stdlib**(`logging.getLogger`, :53)라 `err=` kwarg가 아니라 `%s` 포맷이어야 한다(TypeError 방지). `project_id`는 path param이라 정합.
> ⚠️ **rollback도 쓰기 경로다**: `vcs_rollback`(`v2_feasibility.py:875`)은 `vcs.rollback()`→내부 `self.commit()`로 **신규 FeasibilityCommit row를 생성**하고 `get_db`가 영구 커밋한다 → rollback 핸들러에도 동일 best-effort append(after-commit)를 추가해야 한다(누락 시 rollback로 생긴 feasibility 커밋이 원장에서 빠진다). 'rollback=flush-only·미커밋'은 **사실이 아니다**(실측 정정). branch 등 신규 commit row를 만들지 않는 경로만 제외.

- [ ] **Step 3: design_audit 직접 호출 경로 2곳 배선 (grep 스코프에 `services` 포함)**

시뮬레이션 확정: 직접 호출 경로는 **2곳**이며 기존 plan grep 스코프(`routers`·`api`만)는 ②를 누락했다 — ① `apps/api/app/routers/design_audit.py`(`/run`), ② `apps/api/app/services/collaboration/document_audit_service.py`(`orch.run`, 호출처 `v2_collaboration.py`의 `run_design_document_audit`). 스코프에 `services`를 포함해 탐색:
```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && grep -rn "design_audit_orchestrator\|run_design_audit\|run_design_document_audit\|orch\.run\|orchestrator\.run" apps/api/app/routers apps/api/app/api apps/api/app/services --include="*.py"'
```
계층1 오케스트레이터 코어는 **불변**으로 두고, 각 호출처에서 raw result dict를 얻은 직후 best-effort 삽입(⚠️ logger 없으면 추가):
```python
    # Phase 0 unit d: design_audit 결과를 원장 단일 SSOT에 best-effort 일원화(실패 무중단).
    try:
        from app.services.ledger.ledger_adapters import record_design_audit

        await record_design_audit(
            result=result,                 # 8엔진 raw dict(요약 전) — 호출처 변수명에 맞출 것
            tenant_id=str(tenant_id), project_id=str(project_id),   # 경로별 가용 변수만(pnu 필드 없으면 전달 금지)
            created_by=user_id,
            audit_id=audit_id,             # Task 5.5 backlink — _save_audit 반환값(없으면 생략/None)
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("원장 배선 append 실패(design_audit): %s", str(e)[:160])  # logger 종류에 맞춰(stdlib: %s / structlog: err=)
```
> ⚠️ **경로① (`design_audit.py /run`)**: `_save_audit` 직후(`audit_id` 보유) 삽입. **`pnu=` 인자 금지** — RunRequest(`design_audit.py:256-274`)에 pnu 필드가 없어 `pnu=pnu` 리터럴은 NameError. pnu 변수가 실제 있는 경우만 전달.
> ⚠️ **경로② (`run_design_document_audit`, `document_audit_service.py:67`)**: 함수에 project_id/tenant_id/created_by 인자가 **부재** → 함수 내부 `orch.run` 직후(summarize 전, raw result 보유) 삽입하되, 호출처 `upload_project_document`(`v2_collaboration.py:209-282`)에서 `project_id`(path)·`member.organization_id`·`user.id`를 **함수로 thread-through**(additive 키워드 추가 + caller에서 명시 전달)해야 한다. 미명시 시 ②는 tenant/project=None으로만 적재되어 project-keyed 체인 컨텍스트가 빈다(Task 2.5 NULL-safe 전제와 맞물림).
> ⚠️ `pipeline.py:425`는 `analysis_type=stage`(interpreter sections)만 적재하고 **design_audit raw는 적재하지 않는다** → 본 2곳을 생략하면 design_audit 원장 흡수가 **0건**(생략 시 커밋에 정직 명시).

- [ ] **Step 4: 회귀 — 도메인/피저빌리티 기존 테스트 확인**

해당 모듈의 기존 테스트 파일을 찾아 실행:
```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && ls apps/api/tests | grep -iE "domain_agent|version_control|feasibility"'
```
존재하는 파일을 명시 실행:
`INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest <위 파일들> -q`
Expected: 기존 테스트 전부 PASS(배선이 기존 동작 불변임을 확인). 원장 append는 best-effort라 DB 미가용에도 예외 전파 없음.

- [ ] **Step 5: Commit**

```
printf '%s\n' 'feat(ledger): wire output adapters — domain_agent/feasibility_vcs/design_audit (Phase 0 unit d)' '' 'run_domain·feasibility commit+rollback 호출처(외부 commit 후)·design_audit 직접경로 2곳에' 'best-effort 원장 append(except→logger.warning, 실패 무중단·기존 동작 불변). pipeline.py:425는' 'interpreter stage 적재라 design_audit raw 미적재 → 2경로 배선이 유일 흡수 경로.' '' 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>' > /tmp/msg.txt
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git add -A && git commit -q -F /tmp/msg.txt && git log -1 --oneline'
```

---

## Task 7: Phase 0 완결 검증 게이트 (수용기준 + 회귀 + 푸시)

**근거**: 메모리 규약 "모든 구현 후 코드리뷰·린트·빌드/테스트 필수 완결". Phase 0 수용기준 3개를 코드로 확인.

- [ ] **Step 1: 신규 원장 테스트 전체 PASS + 통합테스트 skip 0 (🔴 필수-DB 게이트)**

⚠️ skip은 '검증됨'이 아니다. 수용기준 2/3(전 체인 변조 없음·재시작 후 영속)은 실 DB에서 실행돼야 인정된다. 인프라 기동 후 DATABASE_URL을 compose와 일치시켜 실행:
```
docker compose -f infra/docker-compose.yml up -d           # Postgres 5444
export DATABASE_URL='postgresql+asyncpg://propai_user:propai_pass_dev@localhost:5444/propai_db'
INTERP_REDIS_CACHE=0 .venv/bin/python -m pytest tests/ledger tests/test_architecture_doc.py tests/test_audit_service.py -q -rs
```
Expected: **실패 0 AND skipped 0**(ledger 통합테스트가 실제 실행·PASS). `-rs`로 skip 사유를 출력 — skip이 1건이라도 있으면 수용기준 2/3을 '미검증'으로 표기하고 **게이트 미통과**(거짓-초록 금지). DB를 띄울 수 없는 환경이면 그 사실을 정직 기재하고 미검증으로 남긴다.

- [ ] **Step 2: 수용기준 1 — "모든 산출물이 단일 원장 체인에 append"(+ 실 배선 존재 강제)**

audit(b2)·design_audit/feasibility_vcs/domain_agent(d)가 모두 `append_analysis`(analysis_type별)로 적재됨을 확인하되, **'경로 존재'가 아니라 '실 호출처 존재'까지** 본다:
- 감사: `grep -rln "append_audit" apps/api --include=*.py | grep -v /tests/` 가 `app/core/audit.py`·`services/audit_service.py` 출력(≥2) AND (DB 기동 시) admin/legal 감사 1건 발생 후 `verify_audit_chain(...).length > 0`.
- 산출물: `record_domain_agent_task`/`record_feasibility_commit`/`record_design_audit` 호출처가 Task 6 grep으로 ≥1씩 확인(design_audit 직접경로 2곳·feasibility 호출처 누락 0).

- [ ] **Step 3: 수용기준 2 — "verify_chain이 전 프로젝트 변조 없음 반환"**

`test_verify_all.py::test_all_clean_chains_verified` 통과(DB) = 전 체인 일괄검증 정상. 변조 주입 시 탐지(`test_tampered_payload_detected`).

- [ ] **Step 4: 수용기준 3 — "감사로그 재시작 후 0건 소실"**

`test_migration_031.py::test_append_persists_across_sessions` + `test_audit_ledger.py::test_append_audit_persists_and_verifies` 통과(DB) = 별도(재오픈) 세션에서 읽힘 = 영속.

- [ ] **Step 5: 린트(있으면) + import 무결성**

```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform/apps/api && .venv/bin/python -c "import app.services.ledger.audit_ledger, app.services.ledger.ledger_adapters, app.services.ledger.analysis_ledger_service, app.routers.analysis_ledger; print(\"imports ok\")"'
```
프로젝트에 ruff/flake 설정이 있으면 변경 파일에 한해 실행(없으면 생략).

- [ ] **Step 6: 코드리뷰 — requesting-code-review 스킬로 자체 점검**

superpowers:requesting-code-review로 본 브랜치 변경분(Phase 0)을 점검. additive·하위호환·정직표기·결정론 불변 위반 0 확인.

- [ ] **Step 7: 푸시(이 세션 범위의 끝 — 머지·alembic 적용·prod는 배포 담당)**

```
wsl.exe -d Ubuntu -- bash -lc 'cd /home/kangjh3kang/My_Projects/Development_AI_trust_infra/propai-platform && git push origin feature/trust-infra-2026-06-11 && git log --oneline -8'
```

---

## Self-Review (작성자 점검 — v2 시뮬레이션 반영)

**1. Spec 커버리지(§8 Phase 0 unit a~d + 수용기준)**
- unit(a) 아키텍처 문서 → Task 1(+ payload·read 계약·정규화 규약 보강). ✅
- unit(b) 감사 원장 흡수 → Task 2(스키마 정식화) + Task 2.5(NULL-safe 정합) + Task 4(흡수 + **10개 실호출처 배선**). ✅
- unit(c) 무결성 검증 노출 → Task 3(단건 `/verify` 기존 + 신규 `verify-all` 일괄, `duplicate_version` 탐지 포함). ✅
- unit(d) 산출물 원장 일원화 → Task 5(어댑터) + Task 5.5(payload 규약·backlink·findings_brief) + Task 6(배선 3경로). ✅
- 수용기준 1/2/3 → Task 7(필수-DB 게이트, `skipped==0` 강제). ✅
- 프라이버시 가드(§6)는 Phase 1 cross-project read 사안 — Phase 0 범위 외(명시).

**2. 시뮬레이션 28건 반영 매트릭스**(38-에이전트 · 적대적 검증 · 3건 기각)
- 🔴 break: pytest-asyncio 미설치→**Task 0 Step 0**; `_chain_where` NULL/''→**Task 2.5**; 라우터 import→**Task 3 Step 6 PYTHONPATH**; feasibility read-키 충돌→**Task 5 `feasibility_vcs`**.
- 🟠 bottleneck: verify_all N+1→**Task 3 단일패스 재작성**; 핫패스 `_ensure`/세션→**§4 성능노트(Phase 1 TODO)**.
- 통합/연동: 감사 미배선→**Task 4 Step 4b/4c**; design_audit ② 누락→**Task 6 Step 3(`services` 스코프)**; bare except→**Task 6 `logger.warning`**; 트랜잭션 가시성→**Task 6 Step 2 caller-after-commit**; verify_all 키 비동형→**Task 3 `_chain_where` 동형 키**.
- loop/품질: schema_version·backlink·findings_brief→**Task 5.5**; get_latest 계약·정규화→**Task 1 문서**; data_quality 메트릭·`get_prior_context`·dedup 카운터→**Phase 1 이관**.
- 검증 건전성: skip 거짓-초록·DATABASE_URL·testpaths→**Task 7 Step 1·작업환경 규약**.

**3. Placeholder 스캔**: 코드 step은 완전 코드 수록. 기존 코드베이스 배선(Task 4 4b/4c, Task 6 Step 2/3)은 삽입 코드 완전 명시 + 위치·변수명만 실행 시 호출처에서 확정(불가피 — "없으면 생략·정직 명시" 규칙).

**4. 위험 0 점검 + 성능 노트**
- 기존 함수·라우트·모델·테이블 불변(신규/멱등 마이그레이션/best-effort 배선). **예외 1건**: Task 2.5 `_chain_where` 버그픽스 carve-out(불변규칙2 예외 — backward-compatible·정직 명시).
- 회귀 step: Task 0 Step 0(d)·Task 2.5 Step 5·Task 3 Step 7·Task 4 Step 5·Task 6 Step 4.
- **성능(차단 아님, Phase 1 TODO)**: best-effort append는 호출자 세션과 별개로 새 커넥션을 풀에서 체크아웃하고 `_ensure`로 멱등 DDL 4건을 재실행 → 핫패스(run_domain/commit)에 await·커넥션 1회씩 추가. 031 적용 환경에서 `_ensure`를 모듈 1회 가드(`_ensured` 플래그) 또는 `LEDGER_SKIP_RUNTIME_DDL`로 단축하는 최적화를 Phase 1로 남긴다. quota 검사(count→insert 무잠금)는 soft-limit이라 경쟁이 무결성 break 아님(정직 기록). 동시 append version 경쟁은 Task 3 `duplicate_version` 탐지까지(예방은 Phase 1).

**5. 타입/이름 일관성**: `append_analysis`·`verify_all_chains`(반환 키 + `duplicate_version`)·`audit_ledger.*`·`ledger_adapters.*`(analysis_type: design_audit/**feasibility_vcs**/domain_agent/audit) 전 task 정합. 마이그레이션 031 `revision`/`down_revision` 일치. payload에 `schema_version`+`kind` 일관(Task 5.5).
