# PropAI 플랫폼 자가성장 엔진 + 자가치유 시스템 — 상세 설계서

- **문서 버전**: v1.0 (설계 단계, 구현 전)
- **작성일**: 2026-06-14
- **작성 주체**: 시스템 아키텍트
- **대상 코드베이스**: `/home/kangjh3kang/My_Projects/Development_AI_market_upgrade/propai-platform` (최신 워크트리)
- **상태**: 설계서. 본 문서는 구현·코드수정을 포함하지 않으며, Phase별 실행계획을 정의한다.

---

## 0. 한눈에 보기 (Executive Summary)

이용자·구독자의 플랫폼 이용현황·패턴·문제·오류를 **실시간 기록·저장**하고, 이를 근거로 다음 4종 능력을 갖춘 "성장엔진"을 구축한다.

1. **자가치유(Self-Healing)** — 장애·지연·폴백을 무인 자동 복구 (저위험만)
2. **자가수정(Self-Correction)** — 프롬프트·임계값·설정·피처플래그를 데이터 기반 자동 보정 (저위험만)
3. **자가개선(Self-Improvement)** — 텔레메트리 진단 → 코드 수정안 **PR 초안 생성 → 사람 승인 머지** (코드변경은 반드시 사람 승인)
4. **자가학습(Self-Learning)** — 교정·검증판정·사용자 피드백을 축적해 프롬프트/few-shot/파인튜닝셋을 성장

> **안전 제1원칙**: 완전자율 코드 자기수정은 **금지**한다. 코드를 바꾸는 모든 행위는 자동화의 종착점이 "사람이 머지하는 PR 초안"이어야 한다. 무인 자동 실행은 데이터/설정 레벨의 저위험 조치로 한정한다.

본 설계는 **새 인프라를 짓지 않는다.** 기존 자산(`llm_usage_log`, `analysis_ledger`, `CircuitBreaker`, `VerifierService`, LangSmith, Celery Beat, `admin_audit_log`)을 신경계로 연결하고, 그 위에 얇은 수집·분석·조치 계층만 신설한다.

---

## 1. 목표 · 범위 · 비범위

### 1.1 목표
- 모든 사용자 상호작용/오류/성능/LLM호출/검증결과/폴백을 **append-only 이벤트 스트림**(`platform_events`)으로 통합 수집.
- 주기 배치로 **인사이트**(`platform_insights`)를 산출: 사용패턴·퍼널·이탈·오류군집·폴백률·품질저하.
- 인사이트를 트리거로 **등급별 자율 조치**를 수행.
- 사용자 피드백(`ai_feedback`)과 검증판정(`VerifierService`), 원장 변조탐지(`analysis_ledger.verify_chain`)를 학습 신호로 재사용.

### 1.2 범위 (In Scope)
- 프론트(`apps/web`) 이벤트 수집 훅: 페이지뷰/클릭/API실패/`window.onerror`/`unhandledrejection`/Web Vitals.
- 백엔드(`apps/api`) 미들웨어 계측: 요청/예외/지연/LLM토큰/검증결과/폴백률.
- 비동기 적재 + 보존정책 + 분석 배치 + 관리자 성장 대시보드.
- 자가치유 룰 엔진, 자가수정(설정/프롬프트/플래그), 개선제안 PR 초안 봇, 학습 데이터셋 성장 루프.

### 1.3 비범위 (Out of Scope, 안전경계)
- **완전자율 코드 자기수정 금지**: 엔진은 `apps/**/*.py|*.tsx` 등 소스코드를 **직접 commit/merge/deploy 하지 않는다.** 코드변경은 GitHub PR 초안까지만 생성한다.
- **무인 DB 스키마 변경 금지**: Alembic 마이그레이션은 사람이 생성·리뷰·적용한다.
- **무인 배포 금지**: api(Micro)·web(A1) 배포는 기존 수동 SSH 절차를 유지(메모리: `project_oracle_deploy`).
- **무인 과금/요율 변경 금지**: `billing` 요율·`service_fees`는 관리자 승인 경로(`admin_audit_log`)를 거친다.
- PII 원본 저장 금지: 주소·이름·연락처 등은 수집 시점 익명화/해시.
- 파인튜닝 자동 실행 금지: Phase 5에서도 데이터셋 "생성"까지만 자동, 실제 튜닝 잡 트리거는 사람 승인.

---

## 2. 데이터 모델

### 2.1 설계 원칙
- 기존 관용구를 따른다: **DDL 멱등 보장 패턴**(`CREATE TABLE IF NOT EXISTS ...`)이 `billing_service.py`의 `llm_usage_log`/`admin_audit_log`에서 이미 정착. 신규 핵심 테이블도 동일하게 `app.startup`에서 멱등 보장하되, **정식 Alembic 마이그레이션을 정본으로 동시 제공**(이중 안전).
- `TenantMixin`(tenant_id UUID NOT NULL INDEX) + `TimestampMixin`(created_at/updated_at)은 `database/models/base.py`에 존재 → ORM 모델은 이를 상속.
- append-only(이벤트·원장·감사): UPDATE/DELETE는 보존정책 prune 외 금지.
- 비로그인/익명 허용: `analysis_ledger`처럼 `tenant_id` nullable 허용 컬럼(이벤트는 익명 세션 가능).

### 2.2 신규 테이블 (3종)

#### (A) `platform_events` — 원시 이벤트 스트림 (append-only)
모든 수집 이벤트의 단일 적재처. 고볼륨 → 파티셔닝/보존정책 적용.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `id` | bigserial PK | 고볼륨 → bigserial(`llm_usage_log` 선례) |
| `event_id` | uuid | 클라이언트 멱등키(중복전송 dedup) |
| `tenant_id` | uuid NULL | 익명 허용. INDEX |
| `user_hash` | text NULL | user_id의 HMAC-SHA256(원본 미저장, PII 익명화) |
| `session_id` | text | 프론트 세션 식별(브라우저 sessionStorage UUID) |
| `event_type` | text NOT NULL | `page_view`/`click`/`api_call`/`api_error`/`js_error`/`web_vital`/`llm_call`/`verify_result`/`fallback`/`heal_action` |
| `surface` | text | `web`/`api`/`worker` |
| `route` | text NULL | 프론트 라우트 또는 API 경로(쿼리스트링 제거·정규화) |
| `status_code` | int NULL | API/HTTP 상태 |
| `latency_ms` | int NULL | 지연 |
| `severity` | text NULL | `info`/`warn`/`error`/`critical` |
| `service` | text NULL | LLM service명(`base_interpreter.name`과 정합) |
| `payload` | jsonb | 익명화된 상세(스택트레이스 정규화·입력요약). PII 키 마스킹 |
| `app_version` | text NULL | web sw 버전/ api 빌드 식별 |
| `created_at` | timestamptz DEFAULT now() | INDEX (시계열 분석) |

**인덱스**:
```
idx_pe_type_created   (event_type, created_at DESC)
idx_pe_tenant_created (tenant_id, created_at DESC)
idx_pe_route_status   (route, status_code)          -- 오류/퍼널 분석
idx_pe_service_created(service, created_at DESC)     -- 품질저하 추적
UNIQUE(event_id)                                     -- 멱등(중복전송 차단)
```
**파티셔닝**: `created_at` 월 단위 RANGE 파티션 권장(고볼륨). Phase 1은 단일 테이블 + 인덱스로 시작, 볼륨 증가 시 파티션 전환(보존정책과 연계).

#### (B) `platform_insights` — 분석 결과 (배치 산출물)
주기 배치가 생성하는 집계·진단 결과. 조치 트리거의 입력.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `id` | uuid PK | gen_random_uuid() |
| `tenant_id` | uuid NULL | 전체집계는 NULL, 테넌트별은 값 |
| `insight_type` | text NOT NULL | `usage_pattern`/`funnel`/`churn_risk`/`error_cluster`/`fallback_rate`/`quality_drop`/`latency_regression` |
| `window_start` | timestamptz | 분석 윈도우 |
| `window_end` | timestamptz | |
| `metrics_json` | jsonb | 정량지표(예: error_rate, p95_latency, fallback_pct) |
| `severity` | text | `info`/`warn`/`critical` (조치 등급 결정) |
| `narrative` | text NULL | LLM/규칙 기반 요약(대시보드 표시) |
| `recommended_action` | text NULL | 권고 조치(`heal`/`correct`/`propose_pr`/`none`) |
| `status` | text DEFAULT 'open' | `open`/`acknowledged`/`acted`/`dismissed` |
| `created_at` | timestamptz DEFAULT now() | INDEX |

**인덱스**: `(insight_type, created_at DESC)`, `(severity, status)`.
**관계**: `phase_f_*` 모델의 `metrics_json` + `narrative` + `composite_score` 패턴을 그대로 차용(코드베이스 일관성).

#### (C) `ai_feedback` — 사용자 교정/평가
👍/👎 + 자유 교정 텍스트 + 어떤 분석/LLM출력에 대한 피드백인지 연결.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `id` | uuid PK | |
| `tenant_id` | uuid NULL | INDEX |
| `user_hash` | text NULL | PII 익명화 |
| `target_type` | text NOT NULL | `llm_output`/`analysis`/`recommendation` |
| `service` | text NULL | LLM service명 |
| `analysis_type` | text NULL | `analysis_ledger.analysis_type`와 정합(원장 연결) |
| `content_hash` | text NULL | **`analysis_ledger.content_hash`와 조인키** — 어떤 버전 분석에 대한 피드백인지 정확 추적 |
| `verdict` | text | `up`/`down` |
| `correction` | text NULL | 사용자 교정 텍스트(학습 신호) |
| `rating` | int NULL | 1~5 선택 |
| `payload` | jsonb NULL | 추가 컨텍스트(익명화) |
| `created_at` | timestamptz DEFAULT now() | |

**인덱스**: `(service, verdict, created_at)`, `(analysis_type, content_hash)`.

### 2.3 기존 자산과의 관계 (재사용·정합)

```
[수집원]
 base_interpreter._invoke()  ──(usage_metadata)──► llm_usage_log (정통 LLM 계측 DB; bigserial)
        │                                              ▲ 기존: billing_service.record_usage_usd() 경유
        └──(신규 훅)──► platform_events(event_type=llm_call)  ◄── 엔진은 여기서 service별 품질 신호 수집
 VerifierService.verify() ──► verdict(pass/warn/fail) ──► platform_events(verify_result)
 CircuitBreaker(base_client) ──► OPEN/폴백 발생 ──► platform_events(fallback / heal_action)
 analysis_ledger.verify_chain() ──► broken[] (변조탐지) ──► platform_events(severity=critical) + 학습신호

[분석]
 platform_events ──(Celery Beat 배치)──► platform_insights

[조치 입력]
 platform_insights + ai_feedback + analysis_ledger(content_hash) ──► 조치/학습 루프

[감사]
 모든 자동 조치 ──► admin_audit_log (audit_admin_action, append-only, best-effort)
```

- **LLM 계측의 정본은 `llm_usage_log`**(DDL: bigserial PK, user_id/service/model/input_tokens/output_tokens/cost_usd/cost_krw/created_at — `billing_service.py` 확인). 엔진은 이를 **중복 INSERT하지 않고**, 품질·지연·실패 신호만 `platform_events`에 별도 기록한다. (집계 시 두 테이블 JOIN/UNION).
- `AIUsageLog` ORM 모델은 현재 `base_interpreter`에 미연결(메모리/in-process). 엔진은 ORM이 아닌 **`llm_usage_log` raw 테이블**을 사실의 원천으로 삼는다.
- `ai_feedback.content_hash` ↔ `analysis_ledger.content_hash` 조인으로 "어떤 분석 버전이 사용자 만족/불만을 받았는가"를 정밀 추적 → 학습 신호.

### 2.4 Alembic 마이그레이션 방침
- **정본 위치**: `apps/api/database/migrations/versions/` (`alembic.ini`의 `script_location=database/migrations`가 가리킴).
- ⚠️ **주의**: `apps/api/alembic/versions/`에 별도 레거시 버전세트(001~019)가 병존. 신규 마이그레이션은 **정본(`database/migrations/versions/`)에만** 추가하고, env 헤드 충돌을 사전 확인(`alembic heads`).
- 네이밍: 기존 `{NNN}_{동작}_{대상}.py` 패턴 준수 (예: `020_add_self_growth_tables.py`).
- 멱등 안전망: 마이그레이션과 별도로, `billing_service`의 `_ensure_*` 선례처럼 `app/services/growth/schema_guard.py`에 `CREATE TABLE IF NOT EXISTS`를 두어 마이그레이션 미적용 환경(개발/신규배포)에서도 부팅 시 자동 보장. 단 **운영 스키마 변경은 마이그레이션이 정본**.

---

## 3. 수집 (Capture)

### 3.1 프론트 (`apps/web`)

**마운트 지점 (탐색 확정)**:
- 전역 훅: `apps/web/lib/providers.tsx`의 `AppStateBridge` useEffect (Provider 트리 최하단, hydration 완료 보장, locale·online 컨텍스트 완비).
- API 계측: `apps/web/lib/api-client.ts`의 `executeFetch` try/finally (모든 v1/v2 호출 커버).
- 에러: `apps/web/app/global-error.tsx` + `apps/web/app/[locale]/(dashboard)/error.tsx`(외 8개 error.tsx).

**신규 파일**:
- `apps/web/lib/growth/event-collector.ts` — 수집 코어. 링버퍼 + 배치 flush.
  - `trackEvent(type, props)` 공개 API.
  - `window.onerror` / `window.addEventListener('unhandledrejection')` 등록.
  - `web-vitals`(이미 Next에 내장된 `reportWebVitals` 또는 PerformanceObserver)로 LCP/CLS/INP 수집.
  - **샘플링**: `page_view`·`web_vital`은 10~20% 샘플, `js_error`·`api_error`는 100% 수집(오류는 전수).
  - **배치 전송**: 5초 또는 20건 단위로 묶어 `navigator.sendBeacon('/api/v1/growth/events')` (언로드 안전). 폴백 fetch keepalive.
  - **프라이버시**: 전송 전 클라이언트단 1차 마스킹(이메일/전화/주소 정규식 치환). user_id는 보내되 서버가 HMAC 해시.
- `apps/web/hooks/useGrowthEvents.ts` — `AppStateBridge`에서 1회 마운트하는 훅(세션ID 생성·라우트 변경 감지·세션 종료 flush).

**수집 항목**:
| 카테고리 | 이벤트 | 비고 |
|----------|--------|------|
| 행동 | page_view, click(주요 CTA만 data-track 속성), funnel_step | 샘플링 |
| 오류 | js_error(onerror), promise_rejection(unhandledrejection) | 전수 |
| API | api_call(성공), api_error(4xx/5xx) — route·status·latency | 4xx/5xx 전수 |
| 성능 | web_vital(LCP/CLS/INP/TTFB) | 샘플링 |

### 3.2 백엔드 (`apps/api`)

**미들웨어 등록 지점 (탐색 확정)**: `apps/api/main.py`의 `setup_middlewares(app)` 다음, `_inject_user_context` 미들웨어 패턴을 따라 `@app.middleware("http")` 또는 `app.add_middleware(GrowthTelemetryMiddleware)` 추가.

**신규 파일**:
- `apps/api/app/middleware/growth_telemetry.py` — `GrowthTelemetryMiddleware`
  - 요청 시작/종료 시각 → `latency_ms`, `status_code`, 정규화 `route`(path 파라미터 `{id}` 치환), `tenant_id`(contextvar에서).
  - 5xx/처리되지 않은 예외 → `severity=error/critical`로 이벤트화(스택트레이스 정규화·해시).
  - **오버헤드 최소화**: 미들웨어는 이벤트를 **동기 INSERT하지 않고** in-memory 큐에 push만(논블로킹). 적재는 Celery로 위임(§4).
  - 헬스체크/메트릭 경로(`/health`, `/metrics`) 및 고빈도 폴링 경로는 수집 제외 화이트리스트.
- `apps/api/app/services/growth/capture_service.py` — `record_event(event)` (큐 push) + `flush_batch()` (Celery 태스크가 호출, COPY/배치 INSERT).
- LLM 계측 후킹: `base_interpreter._invoke()`의 기존 `_record_llm_billing()` 인접 지점에 `capture_service.record_event(llm_call, {service, latency, tokens, cache_hit, retry_count})` 1줄 추가(기존 빌링 경로 불변, 부가 신호만).
- 검증/폴백 후킹: `VerifierService.verify()` 반환부 + `CircuitBreaker.record_failure()/폴백 반환부`에 이벤트 기록 1줄.

**신규 라우터**:
- `apps/api/app/routers/growth.py`
  - `POST /api/v1/growth/events` — 프론트 배치 수신(인증 선택적, 익명 허용). 페이로드 검증·PII 익명화·`event_id` 멱등.
  - (관리자) `GET /api/v1/growth/insights` — 대시보드 데이터(§5).
  - 라우터 등록은 `main.py`의 조건부 등록 패턴(try/except ImportError) 사용.

**프라이버시·샘플링·배치**:
- user_id → `HMAC-SHA256(secret_store['GROWTH_HMAC_KEY'], user_id)` → `user_hash`. 원본 user_id는 이벤트에 저장 안 함.
- `payload` jsonb 저장 전 PII 키 마스킹 함수 적용(주소/이름/연락처/주민번호 패턴).
- 프론트 배치(5s/20건) + 서버 큐(논블로킹) → 요청경로 지연 추가 < 1ms 목표.

---

## 4. 저장 · 적재

- **비동기 적재 엔진**: 기존 **Celery + Celery Beat** 사용(`apps/api/app/tasks/celery_app.py`, broker=Redis). (arq는 미사용 — 탐색 확정. 본 설계는 Celery 관용구를 따른다.)
  - Celery 미배포 환경(개발) 대응: `main.py`의 `_presale_monitor_loop` 인프로세스 asyncio 폴백 패턴을 차용해, Celery 부재 시 `asyncio.create_task(_growth_flush_loop())`로 주기 flush.
- **신규 태스크**: `apps/api/app/tasks/growth_tasks.py`
  - `flush_growth_events` — 5초 주기(또는 큐 임계), in-memory 큐 → `platform_events` 배치 INSERT.
  - `analyze_growth` — 주기 배치(§5), `platform_insights` 산출.
  - Beat 스케줄에 추가:
    ```
    "flush-growth-events":  매 5초 (또는 큐기반 트리거)
    "analyze-growth-hourly": crontab(minute=10)   # 매시 10분 — 단기 오류군집/폴백/지연
    "analyze-growth-daily":  crontab(hour=5, minute=0)  # 매일 05:00 — 퍼널/이탈/패턴/품질
    ```
- **보존정책 (Retention)**:
  - `platform_events`: 원시 90일 보존 → 이후 일별 집계로 롤업 후 prune. `analysis_ledger`의 `prune_old_versions` 패턴 참조.
  - `platform_insights`: 1년 보존(저볼륨).
  - `ai_feedback`: 영구 보존(학습 자산).
  - prune 잡: `analyze_growth_daily` 말미에 90일 초과 이벤트 DELETE(파티션이면 DROP PARTITION).
- **용량 추정**: 이벤트당 ~0.5KB. DAU 1,000 · 사용자당 100이벤트/일 = 10만 건/일 ≈ 50MB/일 ≈ 90일 4.5GB. 샘플링·롤업으로 관리 가능. 고성장 시 월파티션 + 콜드스토리지(예: 일집계만 보존).

---

## 5. 분석 (Analyze)

### 5.1 배치 알고리즘 (규칙 우선, LLM 보조)
`analyze_growth` 태스크가 윈도우별로 `platform_events`를 스캔해 `platform_insights` 생성. **규칙 기반을 1차로 하고 LLM은 narrative 요약·군집 명명에만 보조 사용**(비용·결정론성).

| 인사이트 | 알고리즘 | 트리거 임계(초기값, 자동보정 대상) |
|----------|----------|-----------------|
| `error_cluster` | js_error/api_error를 정규화 스택해시·route·status로 group by, top-N 빈발군 | 동일 시그니처 ≥ 20건/시간 → warn, ≥ 100건 → critical |
| `fallback_rate` | service별 `fallback` 이벤트 ÷ 총 llm_call (시간윈도우) | service 폴백률 > 15% → warn, > 30% → critical |
| `latency_regression` | route/service별 p95 latency, 직전 7일 baseline 대비 편차 | p95 > 1.5× baseline → warn |
| `quality_drop` | service별 verify_result(fail/warn 비율) + ai_feedback(down 비율) 결합 | down율 > 20% 또는 fail율 > 15% → warn |
| `funnel` | 정의된 단계열(예: 부지분석→수지→사업모델→완성) 단계별 도달률·이탈지점 | 정보성(트리거 없음) |
| `usage_pattern` | 기능별 사용빈도·재방문·세션길이(user_hash 단위) | 정보성 |
| `churn_risk` | 활성→비활성 전이(최근 N일 무활동 + 직전 오류경험) | 정보성/마케팅 신호 |

- baseline(이동평균/p95)은 `platform_insights`에 저장해 다음 배치가 참조(자가보정 기반).
- 군집 명명·요약은 `VerifierService`/`base_interpreter` 패턴의 LLM 1콜로 narrative 생성(선택적, 비용 가드).

### 5.2 관리자 성장 대시보드 (프론트)
**배치 위치 (탐색 확정)**: `apps/web/app/[locale]/(dashboard)/settings/page.tsx`의 `TABS` 배열에 `{ id: 'growth', label: '성장 분석' }` 추가 (관리자 `useIsAdmin()` 조건부). 또는 `analytics/growth/page.tsx` 신설.

**신규 파일**:
- `apps/web/components/settings/GrowthDashboard.tsx` — `GET /api/v1/growth/insights` 소비.
  - 카드: 실시간 오류율·폴백률(service별)·p95 지연 추이·품질 스코어(verify+feedback)·퍼널 깔때기·이탈 위험·열린 인사이트 목록(severity 정렬).
  - 인사이트 행에서 관리자가 `acknowledge`/`dismiss`/`approve action` 가능.
  - 기존 `AiTokenUsageDashboard.tsx`(billing/token-usage) 패턴·API 호출 관용구 재사용.

---

## 6. 조치 (Act) — 등급별 자율성

> **자율성 등급표** (안전경계의 핵심)

| 등급 | 무인 실행 | 대상 | 승인 |
|------|-----------|------|------|
| L0 자가치유 | ✅ 자동 | 재시도/캐시/폴백/circuit 복구/stale 재분석 | 불필요(감사 기록) |
| L1 자가수정 | ✅ 자동(저위험) | 임계값/설정/프롬프트버전/피처플래그 | 불필요(감사 + 롤백가능) |
| L2 자가개선 | ❌ 제안만 | 코드/스키마 변경 | **사람 PR 머지 필수** |
| L3 자가학습 | ❌ 데이터셋 생성만 | 파인튜닝/few-shot 갱신 | **사람 승인 후 적용** |

모든 등급의 조치는 `admin_audit_log`(`audit_admin_action`, append-only)에 `actor='growth_engine'`로 기록한다.

### 6.1 L0 자가치유 (무인 자동)
신규 파일: `apps/api/app/services/growth/healing_rules.py` (룰 엔진) + `heal_actions.py` (실행기).

| 룰 | 트리거 | 조치 | 가드레일 |
|----|--------|------|----------|
| 외부API 재시도 | base_client 일시 5xx | (기존 tenacity 유지) + 재시도 후에도 실패 시 캐시 폴백 | 이미 구현됨 — 엔진은 이벤트화·관측만, 재시도 횟수 캡(3) |
| Circuit 자동복구 | CircuitBreaker OPEN | recovery_timeout 후 HALF_OPEN 자동 전이(기존) | ⚠️ Circuit 상태는 **process-local**(워커별 독립). 다중워커면 Redis 공유 상태 검토(개선항목) |
| 캐시 워밍 | 특정 service 폴백률 급등 + 캐시 미스율 높음 | 인기 키 사전 캐시 재생성 잡 트리거 | 워밍 빈도 캡(시간당 1회), 부하 가드 |
| stale 재분석 | `analysis_ledger.verify_chain` broken 또는 입력 staleness 감지(기존 useStageAutoRecalc 패턴) | 해당 분석 재실행 제안 큐잉(자동 재실행 금지 — 메모리 `project_analysis_cache` 원칙 준수) | **자동 재실행 안 함**, 사용자/관리자 1클릭 제안만 |
| 임계값 일시 완화 | 외부API 전면 장애 | rate-limit/timeout 일시 상향(플래그) | TTL 자동 만료(예: 30분 후 원복), 감사기록 |

- **무한루프 방지**: 모든 자동조치는 (a)시간당 실행횟수 캡 (b)동일 트리거 쿨다운 (c)조치→재측정→효과없으면 에스컬레이션(사람 알림). `circuit breaker for the healer` 메타가드.

### 6.2 L1 자가수정 (자동, 저위험만)
신규 파일: `apps/api/app/services/growth/feature_flags.py` + 테이블 `platform_settings`(key/value/scope/ttl, DDL IF NOT EXISTS).

> ⚠️ 탐색 결과 **현재 피처플래그 인프라 없음** → 경량 신설 필요.

| 자동수정 대상 | 근거 인사이트 | 안전장치 |
|---------------|---------------|----------|
| 프롬프트 버전 전환 | `base_interpreter`의 `_PROMPT_VERSION` — A/B 중 품질↑ 버전 자동 채택 | 버전은 **사전 등록된 후보군 내에서만** 선택(임의 생성 금지). 롤백 1클릭 |
| 임계값 보정 | error_cluster/fallback 임계값을 baseline 분포로 자동 재계산 | 변경폭 상한(±20%/회), 감사 |
| 피처플래그 토글 | 특정 기능 오류율 급등 시 자동 비활성(degrade gracefully) | 화이트리스트 기능만 자동토글, critical 기능 제외 |
| 캐시 TTL 조정 | 폴백률·신선도 트레이드오프 | 범위 캡(60s~6h) |

- 모든 L1 변경은 `platform_settings`에 기록 + `admin_audit_log` + 대시보드 노출 + **즉시 롤백 API** 제공.

### 6.3 L2 자가개선 (제안 → 사람 승인)
신규 파일: `apps/api/app/services/growth/improvement_agent.py` (LLM 에이전트) + `apps/api/app/tasks/growth_pr_task.py`.

흐름:
1. `analyze_growth_daily`가 `recommended_action='propose_pr'`인 critical 인사이트 생성(예: 반복 NPE 스택, 특정 라우터 5xx 군집).
2. `improvement_agent`가 인사이트 + 관련 스택트레이스 + 해당 소스파일(읽기)로 **진단 + 패치 제안** 생성.
3. **PR 초안 생성**: 브랜치 `growth/auto-fix/{insight_id}` 생성 → 변경 diff 커밋 → **Draft PR** 오픈 (`gh pr create --draft`, 라벨 `auto-proposed`).
4. PR 본문: 근거 인사이트 링크·재현 이벤트·영향범위·테스트 제안·리스크.
5. **사람이 리뷰·수정·머지.** 엔진은 절대 머지/배포하지 않음.
- 가드: PR은 항상 Draft, `main`·운영 브랜치 직접 push 금지, CI 통과 전 머지 불가(기존 정책), 변경 파일 화이트리스트(예: 마이그레이션/배포스크립트/시크릿 제외).
- `phase_f` `DomainAgentTask`(confidence_score, requires_approval) 승인 게이팅 패턴을 PR 제안 메타에 재사용.

### 6.4 L3 자가학습
신규 파일: `apps/api/app/services/growth/learning_loop.py`.

- 학습 신호 소스: `ai_feedback`(👍/👎/correction) + `VerifierService` verdict(pass/warn/fail) + `analysis_ledger`(content_hash로 버전별 결과).
- **few-shot 성장**: `verdict=up`·고평가 사례 → service별 few-shot 예시 풀에 후보 등록(`base_interpreter` 프롬프트에 주입할 큐레이션 셋). 사람 검수 후 활성화.
- **파인튜닝 데이터셋 생성**: (입력요약, 좋은출력) 페어를 JSONL로 적재(`.omc/`가 아닌 운영 스토리지/Supabase). **생성까지만 자동**, 튜닝 잡은 사람 트리거.
- **프롬프트 자가튜닝(Phase 5)**: down율 높은 service의 실패 사례를 LLM이 분석 → 프롬프트 개선안 **후보** 생성 → §6.2 A/B 후보군에 등록(자동 채택은 L1 안전장치 하에서만).

---

## 7. 5단계 Phased 로드맵

각 Phase는 독립 배포 가능하며, 앞 Phase가 다음의 전제. **api=Micro(Caddy), web=A1(nginx)** 영향 호스트를 각 Phase에 표기(메모리 `project_oracle_deploy`).

---

### Phase 1 — 수집 토대 (Capture Foundation)
**(a) 산출물**: 이벤트가 `platform_events`에 실시간 적재되고, 프론트/백엔드 핵심 신호 전수 수집.

**(b) 생성/수정 파일**:
- 신규: `apps/api/database/models/platform_event.py` (+ insights, feedback ORM)
- 신규: `apps/api/database/migrations/versions/020_add_self_growth_tables.py`
- 신규: `apps/api/app/services/growth/schema_guard.py` (멱등 DDL)
- 신규: `apps/api/app/services/growth/capture_service.py`
- 신규: `apps/api/app/middleware/growth_telemetry.py`
- 신규: `apps/api/app/routers/growth.py` (POST /events)
- 신규: `apps/api/app/tasks/growth_tasks.py` (flush_growth_events)
- 수정: `apps/api/main.py` (미들웨어·라우터 등록, 부팅 시 schema_guard)
- 수정: `apps/api/app/tasks/celery_app.py` (beat: flush 5s)
- 수정: `apps/api/app/services/ai/base_interpreter.py` (llm_call 이벤트 1줄 — 빌링 경로 불변)
- 신규 프론트: `apps/web/lib/growth/event-collector.ts`, `apps/web/hooks/useGrowthEvents.ts`
- 수정 프론트: `apps/web/lib/providers.tsx`(AppStateBridge), `apps/web/lib/api-client.ts`(executeFetch), `apps/web/app/global-error.tsx`, `apps/web/app/[locale]/(dashboard)/error.tsx`

**(c) 신규 API**: `POST /api/v1/growth/events`

**(d) DB 변경**: `platform_events`, `platform_insights`, `ai_feedback` 생성(마이그레이션 020 + schema_guard 멱등).

**(e) 라이브 검증**: 스테이징에서 페이지 이동·강제 에러 발생 → `SELECT count(*), event_type FROM platform_events GROUP BY event_type` 로 수집 확인. API 오버헤드 p95 증가 < 5ms 측정. `sendBeacon` 언로드 전송 확인.

**(f) DoD**: 4종 surface(web behavior/web error/api/llm) 이벤트가 멱등 적재. PII 미저장(샘플 100건 검사). 요청경로 지연 영향 무시가능. 마이그레이션·롤백 검증.

**영향 호스트**: api(Micro) 배포 + web(A1) 재빌드 둘 다.

---

### Phase 2 — 분석 + 성장 대시보드 (Analyze & Observe)
**(a) 산출물**: 주기 배치가 인사이트 산출, 관리자 성장 대시보드에서 가시화.

**(b) 파일**:
- 신규: `apps/api/app/services/growth/analyzer.py` (§5.1 규칙엔진)
- 수정: `apps/api/app/tasks/growth_tasks.py` (analyze_growth)
- 수정: `apps/api/app/tasks/celery_app.py` (beat: hourly/daily)
- 수정: `apps/api/app/routers/growth.py` (GET /insights, 관리자 RBAC)
- 신규 프론트: `apps/web/components/settings/GrowthDashboard.tsx`
- 수정 프론트: `apps/web/app/[locale]/(dashboard)/settings/page.tsx` (TABS에 growth 추가)

**(c) 신규 API**: `GET /api/v1/growth/insights` (관리자), `POST /api/v1/growth/insights/{id}/ack`

**(d) DB 변경**: 없음(2.2 테이블 사용). baseline 저장은 insights 활용.

**(e) 라이브 검증**: 1일 수집 후 `analyze_growth` 수동 트리거 → 대시보드에 오류군집·폴백률·p95·퍼널 표시. 실제 알려진 오류(메모리상 알려진 5xx)와 군집 일치 확인.

**(f) DoD**: 7종 인사이트 중 최소 error_cluster/fallback_rate/quality_drop 동작. 관리자만 접근(RBAC `RequirePermission`). 대시보드 라이브 데이터.

**영향 호스트**: api(Micro) + web(A1).

---

### Phase 3 — 자가치유 (Self-Healing, 무인 L0)
**(a) 산출물**: 저위험 장애 자동 복구·관측, 무한루프 가드.

**(b) 파일**:
- 신규: `apps/api/app/services/growth/healing_rules.py`, `heal_actions.py`
- 수정: `apps/api/integrations/base_client.py` (Circuit/폴백 이벤트 기록 1줄 — 로직 불변)
- 수정: `apps/api/app/services/verification/verifier_service.py` (verdict 이벤트 1줄)
- 수정: `apps/api/app/tasks/growth_tasks.py` (heal 평가 잡)
- 신규: `platform_settings` 테이블(임계값 일시조정용) — 마이그레이션 021
- 수정 프론트: `GrowthDashboard.tsx` (heal_action 로그·복구 현황)

**(c) 신규 API**: `GET /api/v1/growth/heal-log`, `POST /api/v1/growth/heal/{action}/rollback`

**(d) DB 변경**: `platform_settings` (마이그레이션 021 + schema_guard).

**(e) 라이브 검증**: 외부API 강제 장애 주입(circuit OPEN) → 캐시 폴백·자동 HALF_OPEN 복구 이벤트 확인. 캐시 워밍 트리거·쿨다운 동작. 무한루프 가드(동일 트리거 연속발화 시 캡) 테스트.

**(f) DoD**: 4개 치유룰 동작 + 모든 조치 `admin_audit_log` 기록 + 횟수캡/쿨다운/에스컬레이션 검증 + 롤백 가능. **자동 재분석은 제안만**(자동 재실행 안 함) 확인.

**영향 호스트**: api(Micro) 중심. web(A1)은 대시보드 갱신.

---

### Phase 4 — 개선제안 + 피드백 (Self-Correction L1 + 피드백 수집)
**(a) 산출물**: 👍/👎 피드백 수집, 저위험 자동수정, PR 초안 봇.

**(b) 파일**:
- 신규: `apps/api/app/services/growth/feature_flags.py`
- 신규: `apps/api/app/services/growth/improvement_agent.py`
- 신규: `apps/api/app/tasks/growth_pr_task.py` (gh draft PR)
- 수정: `apps/api/app/routers/growth.py` (POST /feedback, 설정 토글 API)
- 수정: `apps/api/app/services/ai/base_interpreter.py` (`_PROMPT_VERSION` A/B 후보 스위치 — L1 안전장치)
- 신규 프론트: `apps/web/components/growth/FeedbackWidget.tsx` (👍/👎/교정) — LLM 출력 카드에 부착
- 수정 프론트: 주요 분석 결과 카드들에 FeedbackWidget 연결

**(c) 신규 API**: `POST /api/v1/growth/feedback`, `POST /api/v1/growth/settings` (관리자), `POST /api/v1/growth/settings/{key}/rollback`

**(d) DB 변경**: `ai_feedback` 활성 사용(Phase1 생성됨), `platform_settings` 확장.

**(e) 라이브 검증**: 분석 카드에서 👎+교정 입력 → `ai_feedback` 적재 + `content_hash` 조인으로 원장 연결 확인. A/B 프롬프트 자동채택(품질↑ 버전) + 롤백 검증. 의도적 critical 인사이트로 Draft PR 1건 자동 생성 확인(머지 안 됨).

**(f) DoD**: 피드백 수집 + L1 자동수정 화이트리스트 내 동작 + 롤백 + Draft PR 자동생성(절대 자동머지 안 함, 라벨/Draft 확인) + 전 조치 감사기록.

**영향 호스트**: api(Micro) + web(A1). PR봇은 CI 환경 `GH_TOKEN`(시크릿) 필요.

---

### Phase 5 — 프롬프트 자가튜닝 + 학습 (Self-Learning L3)
**(a) 산출물**: 교정·verdict·피드백을 학습셋으로 성장, 프롬프트 개선 후보 자동 생성.

**(b) 파일**:
- 신규: `apps/api/app/services/growth/learning_loop.py`
- 신규: `apps/api/app/tasks/growth_learning_task.py` (주간 배치)
- 수정: `apps/api/app/services/growth/improvement_agent.py` (프롬프트 개선안 후보 생성 → A/B 후보군 등록)
- 신규: few-shot 큐레이션 스토리지(Supabase 테이블 또는 `learning_examples` 테이블, 마이그레이션 022)

**(c) 신규 API**: `GET /api/v1/growth/learning/dataset` (관리자 다운로드), `POST /api/v1/growth/learning/promote` (few-shot 후보 활성 — 사람 승인)

**(d) DB 변경**: `learning_examples` (input_summary, good_output, service, source_feedback_id, status). 마이그레이션 022.

**(e) 라이브 검증**: 축적 피드백으로 데이터셋 JSONL 생성 확인. down율 높은 service의 프롬프트 개선후보 생성 → A/B 등록 → 품질지표 개선 측정(전후 verify pass율·feedback up율 비교).

**(f) DoD**: 학습셋 자동성장 + 프롬프트 개선후보가 §6.2 안전장치 하에서만 채택 + 파인튜닝 잡 자동실행 안 함(생성까지만) + few-shot 활성화는 사람 승인.

**영향 호스트**: api(Micro) 중심.

---

## 8. 위험 · 완화 · 성공지표

### 8.1 위험 및 완화
| 위험 | 영향 | 완화 |
|------|------|------|
| 프라이버시(PII 유출) | 법적/신뢰 | user_id HMAC 해시·payload 키 마스킹·원본 미저장·90일 보존·테넌트 격리 |
| 성능 오버헤드 | 응답지연 | 미들웨어 논블로킹 큐·프론트 배치/샘플링·헬스경로 제외·p95 영향 <5ms 게이트 |
| 무한루프(치유가 장애유발) | 가용성 | 횟수캡·쿨다운·메타 circuit·효과없으면 사람 에스컬레이션·즉시 롤백 |
| 오탐(false positive) | 불필요 조치 | baseline 대비 편차+지속시간 이중조건·critical만 자동·warn은 알림만 |
| 보안(자동 코드변경 악용) | 치명적 | **L2 무인 머지 금지**·Draft PR만·파일 화이트리스트·CI 게이트·시크릿/마이그레이션/배포 제외 |
| Circuit 상태 워커별 독립 | 치유 비일관 | (개선) Redis 공유 CircuitState 검토(다중 uvicorn 워커 환경) |
| Alembic 이중 버전세트 | 마이그레이션 충돌 | 정본(`database/migrations`)에만 추가·`alembic heads` 사전확인·schema_guard 멱등 안전망 |
| LLM 비용 폭증(분석/제안) | 운영비 | 규칙 1차·LLM은 narrative/critical만·일일 토큰캡(기존 billing 게이트 재사용) |

### 8.2 성공지표 (KPI)
- **MTTR↓**: 외부API 장애 평균 복구시간(치유 전/후).
- **폴백률↓**: service별 폴백 비율 추세.
- **오류율↓**: 5xx·js_error/세션 추세.
- **품질↑**: verify pass율 + feedback up율 결합 스코어.
- **자동조치 안전성**: L0/L1 조치 중 롤백 발생률(낮을수록 정확), 무한루프 발화 0건.
- **개선 채택률**: 자동생성 Draft PR 중 사람 머지 비율(유효성).
- **학습 효과**: 프롬프트 개선후보 채택 전후 down율 감소폭.
- **오버헤드**: 요청경로 p95 지연 증가(목표 <5ms), 이벤트 적재 지연.

---

## 9. 배포 주의 (Deploy Notes)

- **api = Oracle Micro (134.185.104.167)** — 무중단 블루그린(`ssh 'bash ~/deploy.sh'`). 미들웨어·라우터·Celery·마이그레이션 변경은 여기 영향. Celery worker/beat 재기동 필요.
- **web = Oracle A1 (158.179.174.207)** — 재빌드(`docker-compose build web` + 컨테이너 교체, `sw.js` CACHE_NAME 올림). event-collector/대시보드/FeedbackWidget 변경은 여기 영향.
- GitHub push만으로는 어느 쪽도 자동반영 안 됨(둘 다 SSH 수동). (메모리 `project_oracle_deploy`)
- 마이그레이션은 사람이 적용(무인 금지). schema_guard는 부팅 시 멱등 안전망일 뿐 정본 아님.
- PR봇(`growth_pr_task`)은 CI/실행환경에 `GH_TOKEN` 시크릿 필요 — `secret_store`(platform_secrets, Fernet)에 등록.
- nginx(web)/Caddy(api) 분리 — 신규 라우트 `/api/v1/growth/*`는 Caddy(api) 프록시 대상.

---

## 10. 부록 — 핵심 코드 연결점(탐색 확정)

| 연결점 | 절대경로 | 역할 |
|--------|----------|------|
| LLM 계측 정본 | `apps/api/app/services/billing/billing_service.py` (`record_usage_usd`, `llm_usage_log` DDL) | 토큰/비용 사실원천 |
| LLM 단일경유 | `apps/api/app/services/ai/base_interpreter.py` (`_invoke`, `_record_llm_billing`) | llm_call 이벤트 후킹 |
| 해시체인 원장 | `apps/api/app/services/ledger/analysis_ledger_service.py` (`verify_chain`, content_hash/prev_hash) | 변조탐지 학습신호·feedback 조인키 |
| Circuit/폴백 | `apps/api/integrations/base_client.py` (`CircuitBreaker`, Prometheus, Slack alert) | 자가치유 토대 |
| 검증/할루시네이션 | `apps/api/app/services/verification/verifier_service.py` (pass/warn/fail) | 품질 신호 |
| 관측 | `apps/api/core/observability.py` (LangSmith on/off) | LLM 추적 보강 |
| 워커/배치 | `apps/api/app/tasks/celery_app.py` (Celery+Beat) | 적재·분석 배치 |
| 미들웨어/라우터 등록 | `apps/api/main.py` (`setup_middlewares`, `_inject_user_context`, include_router) | 수집 미들웨어 마운트 |
| RBAC | `apps/api/auth/rbac.py`(`RequirePermission`), `auth/jwt_handler.py`(`CurrentUser`) | 관리자 게이트 |
| 감사 | `apps/api/app/core/audit.py` (`audit_admin_action`, `admin_audit_log`) | 자동조치 감사 |
| 시크릿 | `apps/api/app/services/secrets/secret_store.py` (Fernet, platform_secrets) | HMAC키·GH_TOKEN |
| ORM Mixin | `apps/api/database/models/base.py` (TenantMixin/TimestampMixin/SoftDeleteMixin) | 신규 ORM 상속 |
| 프론트 전역 훅 | `apps/web/lib/providers.tsx` (`AppStateBridge`) | event-collector 마운트 |
| 프론트 API 계측 | `apps/web/lib/api-client.ts` (`executeFetch`) | api_call/api_error 후킹 |
| 프론트 에러 | `apps/web/app/global-error.tsx`, `.../(dashboard)/error.tsx` | js_error 수집 |
| 프론트 대시보드 | `apps/web/app/[locale]/(dashboard)/settings/page.tsx`, `components/settings/AiTokenUsageDashboard.tsx` | 성장 대시보드 배치/패턴 |

---

## 11. 미결정 사항 · 질문 (Open Questions)

1. **다중 uvicorn 워커 환경 여부** — CircuitBreaker 상태가 process-local이라, 워커가 2개 이상이면 치유 비일관. Redis 공유 CircuitState 도입 필요? (현 배포 워커 수 확인 필요)
2. **이벤트 적재량/샘플링율 확정** — 실제 DAU·이벤트 빈도에 따라 90일 보존·파티셔닝 시점 결정. 초기 샘플링율(behavior 10%? 20%?) 확정 필요.
3. **PR봇 권한 범위** — 자동 Draft PR을 어느 레포/브랜치에, 어떤 파일 화이트리스트로 제한할지 정책 확정. `GH_TOKEN` 권한 최소화.
4. **few-shot/파인튜닝 스토리지** — `learning_examples`를 Postgres 테이블 vs Supabase Storage JSONL 중 선택. 파인튜닝 대상 모델(Claude는 파인튜닝 미지원 → few-shot 중심? OpenAI 미설치 상태 고려).
5. **`AIUsageLog` ORM과 `llm_usage_log` raw 테이블 단일화 여부** — 본 설계는 raw를 사실원천으로 채택했으나, 장기적으로 ORM 통합 정리 권장(별도 리팩토링 과제).
6. **테넌트별 vs 전역 인사이트 노출 정책** — 구독자(viewer)에게 자기 테넌트 인사이트 일부 노출할지, 관리자 전용으로 할지(RBAC 정책).
7. **LLM narrative 비용 예산** — 분석 배치에서 LLM 요약 사용 빈도·일일 토큰캡 수치 확정.

---

*본 설계서는 구현 전 검토용이다. Phase 1 착수 전 §11 미결정사항 중 1·2·3을 우선 확정할 것을 권고한다.*
