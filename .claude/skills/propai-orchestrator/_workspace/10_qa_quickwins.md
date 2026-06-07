# QA 검증 보고 — Journey 완성 Quick wins 4종

- **검증일**: 2026-06-05
- **검증자**: PropAI QA Verifier (읽기 검증·코드 무수정)
- **대상 커밋**: `573c5dd`(api-client 폴백 단일화) + `2ff40c2` 중 Quick wins 변경분만
- **제외**: `components/auth/AuthWorkspaceClient.tsx`(타 세션 소셜로그인, 본 검증 무관)
- **프론트 루트**: `propai-platform/apps/web`

## 종합 판정: **정상 (GO)** — 후속 수정 커밋 불필요

- `tsc --noEmit` 전체 프로젝트 **EXIT 0** (타입 오류 0)
- 신규 3개 컴포넌트 ESLint **0 problems** (clean)
- ESLint 잔여 5건(2 error/3 warning)은 **전부 본 변경과 무관한 기존 코드**(diff 미포함 라인)에서 발생 — 회귀 아님
- 신규 파일 하드코딩 hex/팔레트색 **0건**(디자인 토큰 전용). 기존 카드의 `blue-*/indigo-*/slate-*` 하드코딩을 토큰 카드로 치환 → 토큰 규율 **순개선**
- 작업 트리 무변경(읽기 검증만 수행)

---

## 항목별 판정표

| # | 검증 항목 | 판정 | 근거(file:line) |
|---|----------|------|----------------|
| 1 | api-client 폴백 회귀 0 | **PASS** | `lib/api-client.ts:31-44, 88, 290-291` |
| 2 | 라이프사이클 레일 | **PASS** | `LifecycleProgressRail.tsx` 전체 / 스토어 `useProjectContextStore.ts:125,372,388` |
| 3 | 데이터 계보 툴팁 | **PASS** | `DataLineageTooltip.tsx` 전체 / 스토어 `:76-77` |
| 4 | AnalysisVerdict 통합 | **PASS** | `AnalysisVerdict.tsx:41` / 적용 2곳 데이터 손실 0 |
| 5 | 회귀/품질(tsc·eslint·토큰) | **PASS** | tsc EXIT 0, 신규파일 eslint 0, 토큰 전용 |

---

## 1. api-client 폴백 회귀 0 — **PASS**

`resolveApiOrigin()` 단일 헬퍼(`lib/api-client.ts:31-44`)로 v1·v2 화이트리스트 이중 유지 제거. 경로별 출력 보존 검증:

| 입력 상황 | 출력 | 비고 |
|----------|------|------|
| `NEXT_PUBLIC_API_BASE_URL` 존재 | 정규화된 오리진(우선) | `:16-20` 끝슬래시·`/api/v[12]` 꼬리 제거 후 우선. **v2도 이제 동일 적용**(이전 v2 무시 결함 해소) |
| SSR(window undefined) | `http://api:8000` | `:36` Docker 내부 DNS — 기존 보존 |
| 브라우저 localhost/127.0.0.1/[::1] | `http://localhost:8000` | `:24,39` 기존 보존 |
| 4t8t.net / *.pages.dev / propai.kr | `https://api.4t8t.net` | `:43` PROD 폴백으로 **동일 결과 보존**(기존 명시 화이트리스트와 일치) |
| 화이트리스트 밖 브라우저 호스트(프리뷰·커스텀·스테이징) | `https://api.4t8t.net` | `:41-43` **핵심 개선** — 이전 `localhost:8000` 직타격으로 전 API 실패하던 결함 제거 |

- `apiBaseUrl = resolveApiOrigin()/api/v1`(`:47`)로 일원화, `getRuntimeConfig()`(`:327`)에서 그대로 노출 — 시그니처 보존.
- `export const apiClient`(`:294`), `getRuntimeConfig`(`:327`) 시그니처 무변경. `@/lib/api-client` import 사용처 **126개 파일 전부 보존**(import 삭제 회귀 0).
- `tsc EXIT 0`로 타입 회귀 없음.

검증 정확성 주의 1건(비차단): 기존 화이트리스트는 4t8t.net 계열을 **명시적으로** PROD로 보냈고, 신규 코드는 "화이트리스트 밖 전부 PROD 폴백"이라 동일 결과를 산출하나, 만약 미래에 다른 백엔드를 쓰는 추가 호스트가 생기면 `NEXT_PUBLIC_API_BASE_URL` 주입이 필요(현재 운영엔 무영향).

## 2. 라이프사이클 레일 — **PASS**

- 스토어 자산 올바른 재사용: `LIFECYCLE_STAGES`(store `:125`, export `:388`), `getNextRecommendedStage`(store `:372`), `LifecycleStage` 타입(store `:138`). 컴포넌트 `LifecycleProgressRail.tsx:18-23`에서 정확 import.
- 상태 산정 정확(`statusOf`): completed(`completedStages.includes`) → current(`currentStage===id`) → next(`nextStage===id`) → pending. 우선순위·진행률(`completedCount/10`) 정확.
- 타입 정합: 스토어 `completedStages:string[]`/`currentStage:string|null`/`getNextRecommendedStage:()=>string|null` vs 컴포넌트 `LifecycleStage` 비교 — `LifecycleStage`가 string 부분타입이라 비교/`includes` 모두 타입 안전(tsc EXIT 0).
- 단계 클릭 네비: `navigable`(=non-pending)일 때만 `Link href=/${locale}/projects/${projectId}/${meta.route}`. STAGE_META route 세그먼트 10개 매핑 완비.
- `StageIcon` 아이콘 키 7종(site_analysis/legal_compliance/design_ai/construction/feasibility/esg_dashboard/permit_portal) **전부 ICONS에 존재**(`StageIcon.tsx:11-23`), 미존재 시에도 graceful fallback(`:29`).
- **활성 프로젝트 없을 때 안전**: `if (!projectId) return null`(`:79`) — 대시보드 무파괴. 대시보드 적용부 `page.tsx:151` 주석대로 조건부 미표시.

## 3. 데이터 계보 툴팁 — **PASS**

- 타입 실제 바인딩: `DataLineageTooltip(dataSource?, fetchedAt?)`가 스토어 `SiteAnalysisData.dataSource?:string`(`:76`)·`fetchedAt?:string|null`(`:77`)과 정합. 적용부에서 `ctxSite?.dataSource/fetchedAt`(`projects/[id]/page.tsx`), `site?.dataSource/fetchedAt` 및 `cost.source`(`ProjectAnalysisSummary.tsx`) 실값 전달.
- 값 없을 때 graceful: `if (!dataSource && !rel) return null`(`:71`) — 아이콘 미표시. 한쪽만 있어도 동작.
- 접근성: `aria-label`·`aria-describedby`(open시)·`aria-expanded`·`role="tooltip"`·`focus-visible:ring`·hover/focus/blur/click 모두 바인딩(`:75-101`). SVG `aria-hidden`.
- 상대시간 계산 정확: 미래=방금, <60s=방금 전, 분/시/일/개월/년 단계별 반올림(`:25-41`). 보조로 절대시각 ko-KR 병기.

## 4. AnalysisVerdict 통합 — **PASS**

- `VerificationBadge`(`AnalysisVerdict.tsx:13,41`) **래핑 재사용** — 중복 구현 아님. props(`analysisType/context/autoRun`)가 `VerificationBadge.tsx:42-48` 시그니처와 정확 일치.
- `interpretation` 정규화: 문자열/`{label,text}[]`/레코드 모두 수용, 빈 텍스트 필터(`normalize`/`:23-44`). 검증·해석 한쪽만 있어도 동작, 둘 다 없으면 `return null`(`:73`).
- **적용 2곳 데이터 손실 0**:
  - `SiteAnalysisDetail.tsx:328-334`: 기존 하단 "8. AI 부지분석 해석" 중복 카드 제거, 동일 소스(`aiInterp`+`AI_SECTIONS`, store `:294-307`)를 상단 AnalysisVerdict로 단일화. 섹션 라벨·본문 동일 → **손실 없음**. 미사용된 `IconSparkle`도 함께 제거(정리).
  - `ProjectFinanceWorkspaceClient.tsx:626-643`: 기존 `AvmNarr` 5필드(추정근거/비교사례/시장포지셔닝/가치전망/투자의견)를 1:1 `interpretation` 배열로 이전, `AvmNarr` 함수 제거. **5필드 전부 보존**. 빈 필드는 `?? ""`→normalize 필터로 기존 `AvmNarr` null 반환과 동일 동작. (투자의견 `emphasis` 강조 스타일은 균일 카드 스타일로 흡수 — 시각만 변경, 데이터 무손실)

## 5. 회귀/품질 — **PASS**

| 점검 | 결과 | 명령/근거 |
|------|------|----------|
| 타입 체크 | **EXIT 0** | `npx tsc --noEmit` (전체 프로젝트) |
| 신규 3파일 ESLint | **0 problems** | `npx eslint LifecycleProgressRail/DataLineageTooltip/AnalysisVerdict` |
| 신규파일 하드코딩색 | **0건** | 토큰(`var(--*)`) 전용, hex/팔레트 없음 |
| 토큰 규율 | **순개선** | 기존 `blue/indigo/slate` 하드코딩 카드 → 토큰 카드 치환 |

ESLint 잔여 5건은 **전부 기존 코드**(본 diff 미포함 라인)에서 발생 — 회귀 아님:
- `page.tsx:24,35` `Term/TERM_DEFINITIONS` 미사용(warn): diff 0매치, 본 변경은 `:148` 컴포넌트 삽입뿐.
- `projects/[id]/page.tsx:20` display-name(error): 기존 dynamic-import `_loading` 헬퍼, diff 미포함.
- `SiteAnalysisDetail.tsx:52` `resolve` 미사용(warn): 기존 헬퍼, diff 미포함.
- `ProjectAnalysisSummary.tsx:78` set-state-in-effect(error): 기존 `useEffect`(76-81) 블록, diff 미포함(diff는 `Section` 시그니처+호출부만 수정).

다크/라이트 저대비: 신규 UI 전부 `--accent-strong/--line/--surface-*/--text-*` 토큰 사용 → globals.css 다크 보정 라인 자동 적용, 저대비 신규 발생 없음.

---

## 후속(비차단) 권고
- (선택) ESLint 기존 error 2건(`projects/[id]/page.tsx:20` display-name, `ProjectAnalysisSummary.tsx:78` set-state-in-effect)은 본 작업 범위 밖이나 별도 클린업 권장.
- (선택) api-client: 향후 4t8t.net 외 별도 백엔드 호스트 추가 시 `NEXT_PUBLIC_API_BASE_URL` 명시 주입 필요(현 운영 무영향).

**결론: 이미 푸시·Cloudflare 자동배포된 Quick wins 4종은 회귀·데이터손실·타입오류 없이 검증 통과. 수정 커밋 불필요.**
