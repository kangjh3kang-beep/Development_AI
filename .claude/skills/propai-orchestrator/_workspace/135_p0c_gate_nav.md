# P0-C(프론트): 수지 baseline 422 graceful 게이트 + 진행레일/NextStageCta 렌더 복구

## 근본원인(라이브 확정)
- **A3**: `runBaseline` catch가 422를 사일런트 처리(result=null)해 빈 0 표시·사용자 신호 없음.
- **B**: `LifecycleProgressRail`·`NextStageCta`가 store `projectId`에만 게이트 → 바인딩 레이스/일부 진입에서 projectId=null이면 미렌더.

## 구현

### 1) 422 게이트 (A3) — 무목업
- `store/use-feasibility-v2-store.ts`
  - 상태에 `baselineNeedsInput: boolean` 추가(초기 false, `reset`에서 false).
  - `import { apiClient, ApiClientError }`로 변경(상태코드 판별용).
  - `runBaseline` catch: `ApiClientError.status === 422`이면 `baselineNeedsInput=true`(error는 null로 비움, 빨간 에러 대신 입력유도). 그 외 실패는 기존대로 `error`만 노출. 성공/시작 시 `baselineNeedsInput=false`.
  - `calculate` 시작 시에도 `baselineNeedsInput=false`로 초기화(직접 계산 경로 진입 시 게이트 해제).
- `components/feasibility/FeasibilityEditorV2.tsx`
  - store에서 `baselineNeedsInput` 구독.
  - Auto Recommend CTA 위에 422 안내 배너(`baselineNeedsInput && !result`): "부지면적 또는 정확한 주소(시·구·동·번지)를 입력하면 추정 수지가 자동 산출됩니다." + 입력탭 아닐 때 "입력 탭 →" 버튼.
  - 결과 탭: `!result && baselineNeedsInput`이면 `FeasibilityResultView`(빈 0) 대신 액션 게이트 카드(경고 아이콘 + 동일 문구 + "입력 탭으로 이동 ↗" → `setActiveTab("input")`). 그 외에는 기존 `FeasibilityResultView` 렌더.

### 2) 진행레일·CTA 렌더 복구 (B) — props 우선, store 폴백
- `components/lifecycle/LifecycleProgressRail.tsx`: optional `projectId?: string` prop 추가. `projectIdProp ?? storeProjectId`로 해석(props 우선). 나머지 게이트/네비 로직 보존.
- `components/projects/NextStageCta.tsx`: optional `projectId?: string` prop 추가. 동일하게 props 우선·store 폴백. `currentStage` prop은 기존 유지.
- `app/[locale]/(dashboard)/projects/[id]/layout.tsx`: `<LifecycleProgressRail locale={locale} projectId={id} />`로 route param 전달 → 바인딩 레이스와 무관하게 항상 렌더.

### 3) ProjectContextBinder 레이스 점검 — 변경 불필요(검증완료)
- 기존 `ProjectContextBinder`가 effect 본문에서 `setProject(...)`를 **동기 호출**(비동기 meta 로딩 블록 이전)하고, store `setProject`도 동기 `set`이라 projectId가 마운트 즉시 store에 반영됨. 레이스는 props 우선(2) + 동기 set으로 해소. 로직 보존을 위해 미수정(diff 0).

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0**.
- `git diff` import 보존 확인: `import { apiClient, ApiClientError } from "@/lib/api-client"` 유지(린터 import 삭제 트랩 없음).
- 무한루프 없음: 신규 effect/상태 추가 없음. 게이트는 기존 `baselineTriedRef` 1회 가드 하의 422 결과를 표시만 함.
- 변경 5파일(+77/-7): store, FeasibilityEditorV2, LifecycleProgressRail, NextStageCta, layout.

## 미진(범위 외)
- `NextStageCta`는 layout이 아닌 각 서브페이지(site-analysis/finance/design/... 14곳)에서 렌더됨. 해당 page.tsx들은 본 작업 범위 밖이라 `projectId` prop 미전달(현재는 store 동기 set 폴백으로 동작). 후속: 각 페이지에서 route param `id`를 `projectId`로 전달하면 폴백 의존 제거 가능.
- push/배포 금지 준수(미수행).
