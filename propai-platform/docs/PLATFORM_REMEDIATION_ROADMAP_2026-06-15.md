# PropAI 플랫폼 개선·보완·보강 로드맵

작성: 2026-06-15 · 브랜치 `feature/trust-infra-2026-06-11` · 성격: 플랫폼 전체 코드리뷰 산출물
방법: 객관 게이트(ruff/tsc/eslint 실측) + 37-에이전트 위험우선 리뷰 → critical/high 적대적 검증 → 종합. 모든 항목 실코드 file:line 확인.

> **검증 환경 한계(정직 표기):** 이 환경은 Docker 미연동(Postgres 불가) + 일부 런타임 의존 미설치(prometheus_client/shapely)로 **백엔드 통합테스트 실행 불가** → 본 리뷰는 정적 분석 + 객관 lint/typecheck 기반. DB 실행 검증이 필요한 항목은 그렇게 명시.

## 1. 요약 대시보드

| 객관 게이트 | 수치 | 평가 |
|---|---|---|
| 백엔드 ruff | 3248건 (1722 자동수정 가능) | 대부분 스타일/UP/SIM — 버그성은 소수(B007/E712/E741) |
| 프론트 tsc --noEmit | 0 에러 | 타입 클린 |
| 프론트 eslint | 168건 (에러 35 · 경고 133 · 24 자동수정) | 경고 위주 |
| 백엔드 pytest (CI) | `pytest tests/`만 수집 — apps/api/tests(~78%) 미실행 | **게이트가 허위 green** |

**축별 confirmed 발견 수:** security 16 · concurrency 6 · integrity 7 · test_gap 8 · dependency 5 · tech_debt 8 · deadcode 4 · correctness 3 · perf 2.

**전반 건강도:** 결정론 코어·정직표기·해시체인 등 *설계 불변규칙은 견고*하나, **경계(인증·테넌트 스코프)와 운영 인프라(테스트 수집·의존성 SSOT·스키마 출처)에 구조적 구멍**. "코어는 신뢰 가능, 가장자리는 미봉" 상태. 코드 품질보다 *게이트의 진실성*(CI가 위험을 못 잡음)이 최대 리스크.

---

## 2. 🔴 P0 — 보안/정합/무결성 차단 (즉시)

### P0-1. arq 미선언으로 worker 부팅 크래시 — 모든 스케줄 작업 죽음 · effort S
- `apps/worker/main.py:15-22` (`from arq import cron`). `requirements.txt`·`pyproject.toml`·`requirements.oracle.txt` 어디에도 `arq` 없음.
- worker가 import 단계 ImportError로 사망 → rate/cost auto-update 등 백그라운드 전무(조용히 무동작).
- 수정: `arq>=0.25`를 requirements + oracle + pyproject `[optional-dependencies].worker`에 추가. CI에 `python -c "import apps.worker.main"` import-smoke 추가.

### P0-2. requirements ↔ pyproject SSOT drift — 부팅 임포트 크래시 · effort M
- `requirements.txt`에 prometheus-client 부재(oracle:72에만). unguarded import `main.py:18` + `metrics.py:6`.
- mlflow 전이의존에만 의존 → 전이 끊기면 API 부팅 실패.
- 수정: `prometheus-client>=0.20.0` 직접의존 추가. 장기: pip-compile/uv로 requirements를 pyproject에서 생성(declared==installed) + deptry CI.

### P0-3. CI가 apps/api/tests(~78%) 미수집 — 게이트 허위 green · effort M
- `.github/workflows/cicd.yml:42`(`pytest tests/`), `pytest.ini:3`(`testpaths = tests`), `apps/api/pyproject.toml:182`(`testpaths=["../../tests"]`).
- ledger 무결성·8엔진·billing·coordinator 등 **불변규칙-critical 테스트가 머지를 게이트 못함**(red여도 green).
- 수정: `pytest tests/ apps/api/tests/ --cov=apps/api`로 양 트리 수집. CI Postgres 서비스 하 triage. 장기 단일 루트.

### P0-4. cost(기성/해시체인) 라우트 무인증 — 임의 project_id 영속·체인 적재 · effort M
- mount `main.py:548-549`(`include_router(cost_router)` — `dependencies=` 없음), 미들웨어 `main.py:319-333`(best-effort, except→pass), `app/routers/cost.py:585`(register_billing_d2 무 auth), `app/services/cost/billing_service.py:204-280`(INSERT progress_billings + commit + analysis_ledger.append_analysis 해시체인).
- 인증·소유권 없이 임의 project_id로 기성 데이터 영속 + 무결성 체인 적재 → **무결성 대상이 무인증 오염**.
- 수정: include 시 `dependencies=[Depends(get_current_user)]` 또는 쓰기 라우트에 current_user + project_id tenant 소유권 가드(`v2_review_comments._require_commenter`/`_load_scoped_document` 패턴).

### P0-5. require_role 의존성 폴스루 — `request=None → return True` · effort M
- `app/core/rbac.py:106-108`(`if request is None: return True`), 사용 `app/routers/auth.py:14`(`require_admin = require_role(Role.ADMIN)`), `test_rbac.py:101-105`.
- require_role이 (a) request 미주입 시 무조건 통과, (b) `x-user-role` 헤더 신뢰 → 인증 무력화. admin/users(auth.py:115)가 이 게이트를 거침.
- 수정: require_role을 JWT 기반(`get_current_user`의 role/tier)으로 재구현, 헤더 신뢰·None 폴스루 제거. test를 실제 인증요구 검증으로 교체.

---

## 3. 🟠 P1 — 고위험·신뢰성 (단기)

- **P1-1. project_dashboard 조회·시뮬 무인증·무테넌트 (IDOR/BOLA)** · M — `app/routers/project_dashboard.py:90,122,290` + `_fetch_project_lite:7-26`(untenanted SQL). 세 라우트에 `get_current_user`/`require_project_member` + tenant 조건.
- **P1-2. 에이전트 오케스트레이터 tenant 소유권 미검증 (교차 테넌트)** · S — `agents/propai_orchestrator.py:113-155, 477-525`, `routers/agents.py:35-110`. run() 시작 단일 게이트(`SELECT 1 FROM projects WHERE id=:pid AND tenant_id=:tid`) + WS 경로.
- **P1-3. g2b 분석 히스토리 DELETE 무인증·무스코프 — 전 테넌트 삭제** · S/M — `g2b_bid.py:266-273`, `g2b_bid_service.py:769-778`, 모델에 소유자 컬럼 없음. 인증 + tenant where + (소유자 컬럼 마이그레이션) + 소프트삭제 검토.
- **P1-4. set_secret 하드코딩 폴백 마스터키로 조용히 암호화 저장** · S — `secrets/secret_store.py:227,429`. _encrypt 직전 `master_key_status()` 확인, hardcoded-fallback이면 logger.warning(운영 raise) + key_stability 플래그.
- **P1-5. analysis_ledger 동시 append → version 중복(체인 분기)** · M — `analysis_ledger_service.py:209-245`, `031_analysis_ledger.py`(UNIQUE 없음). (1)체인키 UNIQUE 제약 마이그레이션 (2)`pg_advisory_xact_lock`/`FOR UPDATE` 직렬화 (3)UniqueViolation 1회 재시도. *(Phase 0와 인접하나 동시성 결함은 별개 — Phase 0에서 탐지(duplicate_version)만, 예방은 여기.)*
- **P1-6. record_usage_usd 충전잔액 lost-update** · M — `billing/billing_service.py:240-263`(절댓값 read-modify-write). 단일 원자 UPDATE(컬럼 표현식) 또는 `FOR UPDATE`.
- **P1-7. 이중 SQLAlchemy Base — alembic autogenerate가 app.models를 못 봄** · L — `app/core/database.py:36` vs `database/models/base.py:14`, env target은 후자만(`migrations/env.py:21,31`). 단일 Base 통합 후 target_metadata 통합.
- **P1-8. 런타임 lazy-DDL 광범위 산재(요청경로 CREATE TABLE IF NOT EXISTS)** · L — 20+ 파일(cost/*, core/audit, sales/referral, secrets, ai/interpretation_cache 등). 테이블군별 alembic 이관, IF NOT EXISTS는 env-게이트 shim으로만.
- **P1-9. BankReadyReportBuilder PDF 미이스케이프 document.write (DOM XSS)** · S — `apps/web/components/report/BankReadyReportBuilder.tsx:403-446`. 동적 문자열 HTML 이스케이프 또는 textContent DOM.
- **P1-10. 25× try/except ImportError 이중 import 루트(app.* vs apps.api.app.*)** · L — `main.py:111-205` 등. import 루트 `apps.api.app` 단일화 codemod + banned-import 린트.
- **P1-11. 헤드라인 통합테스트 빈 `pass` 스텁 — false-green** · L — `tests/integration/test_full_pipeline.py`, `test_multi_tenant.py`(RLS 스텁). `test_esg_flow.py` 실-assertion 패턴으로 구현 + meta-test로 빈본문 실패.
- **P1-12. 13개 테스트 파일 양 트리 중복·발산 — CI는 stale 실행** · M — diff 후 union canonical 머지, 중복 삭제, 단일 루트.

---

## 4. 🟡 P2 — 기술부채·테스트·성능 (중기)

- **P2-1. 라우터 import 실패 시 무로그 None — 엔드포인트 묵음 소실** · M — `main.py:111-208` 상단 import 블록 except 무로그(하단 등록 블록은 logger.warning 적용). 통일 + 필수/선택 라우터 구분(필수 fail-fast).
- **P2-2. comprehensive_analysis 무인증·무쿼터 LLM — 미과금 비용남용** · M — `comprehensive_analysis.py:23,37`, 이중 마운트 `main.py:659,661`. get_current_user + enforce_llm_quota + 모델 allowlist.
- **P2-3. charge_service 무료 토지분석 TOCTOU** · M — `billing_service.py:503-542`. 원자 `UPDATE ... WHERE count<quota RETURNING` 또는 FOR UPDATE.
- **P2-4. PDF 발급 async 라우트 blocking urllib+reportlab — 이벤트루프 점유** · S — `sales/termination_cert.py:434-511`. `anyio.to_thread.run_sync` + httpx 비동기 + 미사용 db 제거.
- **P2-5. 동시성/RLS를 SQLite 프록시로 검증 — Postgres+asyncpg 미검증** · M — `tests/test_unit_concurrency.py`, `test_multi_tenant.py`(RLS skip). PROPAI_INTEGRATION_TEST 하 실 asyncpg 2세션 검증.
- **P2-6. coverage --cov-fail-under 부재 — vanity 80% 침식** · S — `cicd.yml:42`. P0-3 후 실측 재측정 → 임계 고정.
- **P2-7. escrow/blockchain money-path 실로직 커버리지 부재** · M — `test_blockchain_service.py`(아티팩트 없으면 skip). web3 RPC mock + 상태전이 검증.
- **P2-8. 정규식 SVG 정화기 — DOMPurify 미사용 우회 가능** · M — `apps/web/components/cad/ReferenceAssemblyCard.tsx:44-65`. DOMPurify 또는 Blob `<img>`.
- **P2-9. 보안 헤더 전무(CSP/X-Frame-Options/HSTS)** · M — `apps/web/next.config.mjs`. headers()에 CSP(nonce)/nosniff/Referrer-Policy/HSTS.
- **P2-10. project_pipeline 종합분석 실패 silent pass(정직표기 위반)** · S — `pipeline/project_pipeline.py:677-681,818`. logger.warning + skipped_reason.
- **P2-11. 빌링 설정 로드 실패 except: pass(silent-failure 위반)** · S — `billing_service.py:453-454`. logger.warning + 78건 except 로깅 CI 게이트.
- **P2-12. AgentCoordinator 빈 스텁 — 회로차단/백오프가 무동작 감싸는 죽은코드** · S — `core/coordinator.py:6-17`. 삭제 또는 NotImplementedError(silent success 제거). 탄력성 정본은 orchestrator(P2-13).
- **P2-13. orchestrator 타임아웃/재시도/병렬화 부재 + terminal 요약 이벤트 미yield** · M — `agents/propai_orchestrator.py:476-525`, 소비부 `routers/agents.py:40-101`. `asyncio.wait_for` + 재시도/백오프 + gather + terminal summary yield + 실패단계 data_source/degraded.
- **P2-14. 에이전트 WebSocket rate limit 미적용 + 소유권 미검증** · S — `routers/agents.py:50-99`. ai_limiter 동등 + 소유권 검증.
- **P2-15. material_unit_prices.material_code 런타임 UNIQUE vs ORM plain index 불일치** · M — `app/models/v61_cost.py:38` vs `cost_tables_bootstrap.py`. ORM/DDL 합의 단일 마이그레이션.
- **P2-16. 고아 alembic 트리(apps/api/alembic/versions) — 자체 env·도달불가 리비전** · S — `apps/api/alembic.ini:5`, `alembic/versions/004,005`. active chain 반영 확인 후 삭제/아카이브. 루트 1개.
- **P2-17. users/auth 001_initial 수기관리 — User ORM과 발산** · M — `app/models/auth.py:22-31` vs `001_initial_schema.py:35-41`. Base 통합 후 autogenerate --compare. `is_active String(10)`→Boolean.
- **P2-18. 불변-critical 서브시스템 CI-수집 트리에 테스트 0** · M(P0-3 종속) — ledger/design_audit/billing/coordinator. P0-3로 해소.
- **P2-19. project_pipeline.py 2203줄 god module** · L — schemas 분리 + 스테이지 핸들러 추출(결정론 코어 불변·additive).
- **P2-20. ruff 버그성 린트(자동수정 외)** · M — `version_control_db.py:59`(E712), `finance_cost_engine.py:237,241`(E741), `ifc_generator_service.py:127,245`(B007). 개별 수정.

---

## 5. ⚪ P3 — quick-win·스타일 (별도 PR 일괄)

- **P3-1. ruff --fix 일괄(1722건)** · M — CI 1회 적용 후 ruff 게이트 고정. 개별 나열 금지.
- **P3-2. eslint --fix(24건)** · S
- **P3-3. weak default secrets 운영 가드** · S — `config.py:209` JWT 가드 패턴을 minio/hasura/emqx로 확장(prod insecure default raise).
- **P3-4. CI Python 3.11→3.12** · S — `cicd.yml:32,116`.
- **P3-5. root docker-compose `ENVIRONMENT=production` 강제** · S — `docker-compose.yml:30`(prod 가드 발화).
- **P3-6. data_integrity 진단 무인증** · S — `routers/data_integrity.py:11-39`. is_super_admin 또는 내부소스명 제외.
- **P3-7. FeasibilityVCS project_id 소유권** · S — `version_control_db.py:74-150`, `v2_feasibility.py:861-945`. require_project_member.
- **P3-8. accept_invite IntegrityError 미처리** · S — `v2_collaboration.py:144-158`. UniqueViolation→409 또는 FOR UPDATE.
- **P3-9. verify_chain 스키마 통일** · S — `analysis_ledger_service.py:343-345` 예외분기에 `verified:False`+`error:True`.
- **P3-10. g2b sync POST 무인증** · S — `g2b_bid.py:47`. 관리자 인증 + arq 큐잉.
- **P3-11. g2b iterations 무제한** · S — `g2b_bid.py:300` `Field(10000, ge=1000, le=50000)`.
- **P3-12. AuditTrailService 데드코드 제거** · S — `app/services/audit/audit_service.py`. record_audit 경로로 테스트 재작성(Deprecation shim 후 삭제).
- **P3-13. esg/auth/avm/finance 중복 라우터 등록** · S — `main.py:448 + 577-582`. SSOT 1개만.
- **P3-14. DocumentViewerModal javascript: 스킴** · S — `DocumentViewerModal.tsx:55,90`. safeHref(http/https/blob/mailto).
- **P3-15. expert_panel _GRAPH lazy-init 비원자** · S — `expert_panel_graph.py:184,202-205`. import 시점 빌드 또는 lru_cache.
- **P3-16. installed venv가 pin 위반(bcrypt 5.0.0 vs <5)** · M — `requirements.txt:62`. clean venv 재빌드 + bcrypt/passlib 결정.

---

## 6. 보강 — 신규 역량 (구조적 보완)

1. **멀티에이전트 성숙** — coordinator(P2-12)는 죽은 추상화. 탄력성을 orchestrator(P2-13)에 일급 구현; 분산조정이 로드맵이면 coordinator를 실 transport+진짜 회로차단기로. 둘 중 하나로 SSOT 정직화.
2. **테스트 인프라** — CI Postgres + asyncpg DB 픽스처 표준화, PROPAI_INTEGRATION_TEST 게이트, 단일 테스트 루트, --cov-fail-under, 빈본문 integration meta-test. (P0-3·P1-11·P1-12·P2-5·P2-6·P2-18 통합 트랙)
3. **관측성** — prometheus-client 직접의존 고정(P0-2), `/metrics` 미인증 점검, import-smoke + deptry CI, 78건 except 로깅 게이트.
4. **의존성 pin 정합** — requirements↔pyproject SSOT 1개(pip-compile/uv), worker extra 분리, bcrypt/passlib 결정, Python 3.12 정렬.
5. **스키마 출처 단일화** — Base 통합(P1-7) + 런타임 DDL→마이그레이션(P1-8) + alembic 루트 1개(P2-16) → "마이그레이션이 유일한 스키마 진실".
6. **스케줄러 정합** — celery beat 작업이 어떤 배포에서도 안 뜸. celery beat 서비스 추가 또는 arq cron 포팅. 모든 스케줄 작업에 launching process 검증.
7. **인증 경계 강화(프론트)** — JWT localStorage→HttpOnly+Secure+SameSite 쿠키, Next.js middleware 서버경계 가드, CSP(P2-9) 병행.

---

## 7. 권장 실행 순서·묶음 (PR 단위)

| 순서 | PR 묶음 | 포함 | 근거 |
|---|---|---|---|
| **PR-1** | 부팅·게이트 복구(blocker) | P0-1 · P0-2 · P0-3 · P3-4 | 부팅/CI가 안 서면 이후 검증 무의미 |
| **PR-2** | CI 진실화 후속 | P1-11 · P1-12 · P2-6 · P2-18 | 수집 켜지면 드러나는 red/스텁/중복 triage |
| **PR-3** | 인증·테넌트 경계(라우터) | P0-4 · P0-5 · P1-1 · P1-3 · P2-2 · P3-6·7·10 | 동일 패턴 일괄, 보안 최우선 노출면 |
| **PR-4** | 에이전트 경계+탄력성 | P1-2 · P2-13 · P2-14 · P2-12 | orchestrator 영역 응집 |
| **PR-5** | 동시성 정합 | P1-5 · P1-6 · P2-3 · P3-8·9 | DB 원자성 공통. ledger UNIQUE 선행 |
| **PR-6** | secrets·config 강화 | P1-4 · P3-3 · P3-5 | 작고 독립적 |
| **PR-7** | 프론트 보안 | P1-9 · P2-8 · P2-9 · P3-2 · P3-14 · 보강#7 | 백엔드와 병렬 가능 |
| **PR-8** | 스키마 출처 단일화(대공사) | P1-7 → P1-8 → P2-16·17·15 | Base 통합이 autogenerate 선결 |
| **PR-9** | 패키지 구조 단일화 | P1-10 · P2-1 | codemod 대규모, 다른 PR 후 충돌 최소화 |
| **PR-10** | 정직표기·데드코드 위생 | P2-10·11 · P3-12·13·15 · P2-19 | 동작 무변경 리팩터 |
| **PR-11** | ruff/스타일 일괄 | P3-1(--fix 1722) · P2-20 · P3-16 | **최후 단독 PR** — diff 노이즈 격리 |

**병렬:** PR-7(프론트)은 PR-3~6과 병렬. **직렬 필수:** PR-1→PR-2(수집 선행), P1-7→P1-8/P2-17(Base 선행), P1-5 UNIQUE 마이그레이션→append 직렬화. **마지막 고정:** PR-11(ruff)은 항상 끝.

---

*검증 메모: ① admin/users는 select(User) 직전 require_admin을 거침(auth.py:118) — 근본문제는 rbac.py:107의 `request=None→True` 폴스루(P0-5로 격상). ② 031 migration에 UNIQUE 부재를 인덱스 정의에서 직접 확인(P1-5). ③ Base 이중성은 두 DeclarativeBase + env target이 후자만 가리킴 확인(P1-7). 나머지 발견은 인용 file:line에서 코드 일치 확인.*
