# 168 · 인허가 버튼 + 7단계 파이프라인 스톨 근본수정

작업일: 2026-06-07 · 담당: Debugger · 범위: 프론트(permit·pipeline) 2파일, 백엔드 무변경

---

## 버그1 — 인허가 분석/시나리오 버튼 "무반응"

### 라이브 재현 (agent-browser, 비로그인 /ko/permits)
- "🤖 인허가 분석" 버튼(`@e9`)은 onClick=run으로 정상 배선됨(미배선 아님).
- 주소 미선택 클릭 → `if (!target)` 조기 반환 → API 0건. 에러문구 "주소를 먼저 선택하거나 입력하세요."는 실제로 DOM에 렌더됨(작은 회색 텍스트라 테스터가 "무반응"으로 인지).
- 주소 입력 후 클릭 → 엔드포인트 도달 확인(브라우저 fetch 실측): `POST /api/v1/permits/ai-analysis` → **HTTP 403** (비로그인).
- "시나리오 분석"(DevelopmentScenarioCard): `POST /api/v1/development-methods/scenarios` → **HTTP 200** (인증 불필요, 정상 동작).

### 근본원인
- 버튼은 정상 배선. 진짜 결함은 **403/401(인증 필요)·402(코인)가 단일 vague 메시지로 뭉뚱그려져** 사용자가 원인(로그인 필요)을 알 수 없고, 시각적으로 "무반응"처럼 보이는 것.
- 백엔드 `routers/permits.py:248-251` `/ai-analysis`는 `RequirePermission("permits","read")` + `enforce_llm_quota` 게이트. `auth/rbac.py:257` `("viewer","permits","read")` 존재 → **로그인한 구독자는 통과**. 즉 비로그인일 때만 403.
- (참고) 현재 라이브 로그인 자체가 인프라 이슈로 실패: `POST /auth/login` → asyncpg `DuplicatePreparedStatementError`(pgbouncer prepared statement). 이는 제미나이 인프라 영역 — 본 수정 범위 밖.

### 수정 (무목업·최소 diff)
`components/operations/PermitAiWorkspaceClient.tsx`
- `ApiClientError` import 추가.
- `run()` catch에서 상태코드 분기: 401·403="로그인이 필요합니다", 402="사용량(코인) 필요", 기타=기존 메시지. → 버튼이 더 이상 원인불명 "무반응"이 아니라 행동지침을 제시.
- 시나리오 버튼은 결함 없음(라이브 200) → 무변경.

---

## 버그2 — 7단계 파이프라인 "2/7(공사비 이후) 정지"

### 라이브 재현 (백엔드 직접 호출)
- `POST /api/v2/pipeline/run` (전체, no stop_after):
  - 강남 역삼동: **HTTP 200, 42s, status=completed**, 7단계 전부 completed (site 41.6s, design~report 합계 <30ms).
  - 파주 운정동: 콜드 40s / 웜 0s, 7단계 전부 completed.
- 즉 **백엔드는 스톨하지 않음**: 오케스트레이터(`project_pipeline.py:169-198`)는 단계별 try/except로 예외를 FAILED로 격리하고 항상 끝까지 진행 후 반환. Cloudflare 100s 한도 내 안정 완료.

### 근본원인 (프론트)
- "전체 7단계 분석 계속"(projectMode) → `runRemainingStages`는 `/pipeline/run`을 **단일 동기 호출**(폴링 아님)로 실행하고 한 번에 응답을 받음.
- 이 호출에 **명시 `timeoutMs` 누락 → 기본 120s**. 전체 재실행은 부지분석 재수집(~40s)+이후 단계를 포함하는 가장 무거운 호출이라, 콜드 캐시/프록시 지연 시 클라이언트가 중도 abort.
- abort/네트워크 실패 시 기존 catch는 에러 문자열만 세팅하고 **`stages` 표시는 직전 `runSiteAnalysis`의 부분상태(부지분석만 완료)로 그대로 고정** → 사용자에게 "공사비 이후 정지·진행바 무변화"로 보임.

### 수정 (무목업·최소 diff)
`components/pipeline/ProjectPipelinePanel.tsx` · `runRemainingStages`
- `timeoutMs: 170000` 명시(= runSiteAnalysis와 동일). 가장 무거운 호출을 끝까지 수신.
- 실패 시 네트워크/타임아웃 메시지를 사람친화적으로 변환 + **미완료(대기/진행 중) 단계를 'failed'로 전이**(이미 completed/skipped 단계는 보존) → "멈춘 듯한" 프리즈 상태 해소(runSiteAnalysis의 기존 패턴과 동일).
- 의존성 배열에 `siteAnalysis` 추가(이미 본문에서 참조 중이라 정합).
- 백엔드는 정상이므로 무변경(skip_stages로 site_analysis를 건너뛰면 `site_to_design`가 기본값으로 떨어져 오답 → 채택 안 함).

---

## 검증
- 프론트 `npx tsc --noEmit` → **EXIT 0**.
- `git diff --stat`: PermitAiWorkspaceClient +10/-3, ProjectPipelinePanel +16/-2 (2파일, 26 insertions). import 보존 확인(`apiClient`/`ApiClientError`).
- 라이브 백엔드 실측: `/pipeline/run` 42s 7/7 completed, `/development-methods/scenarios` 200, `/permits/ai-analysis` 403(비로그인)·코드상 viewer 통과.
- 백엔드 무변경 → py_compile 불요.

## 후속(범위 밖, 핸드오프)
- 라이브 로그인 500/asyncpg DuplicatePreparedStatement(pgbouncer) — 인프라(제미나이). 이게 해소돼야 인증 필요 화면 E2E 완결.
- `/permits` 운영 페이지는 인증 게이트 없이 렌더되나 `/ai-analysis`는 인증 필요 → 페이지에 비로그인 안내 배너를 두는 UX 정합은 별도 티켓 권장.

## 변경 파일
- `apps/web/components/operations/PermitAiWorkspaceClient.tsx`
- `apps/web/components/pipeline/ProjectPipelinePanel.tsx`
