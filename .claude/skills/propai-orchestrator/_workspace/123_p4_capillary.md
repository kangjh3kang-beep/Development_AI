# P4 — 모세혈관(단계 간 데이터 전파) 일반화

루트: `/home/kangjh3kang/My_Projects/Development_AI` · 프론트: `propai-platform/apps/web`
무목업 · push/배포 없음 · additive · 회귀안전(중앙 store SSOT 보존).

## 배경(감사 확정)
- MODULE_UPSTREAM(6노드)와 LIFECYCLE_STAGES(10단계) 분리, finance/legal/bim/construction/permit/report는 staleness 그래프 밖.
- isStale 소비처는 2/6(CadCompliancePanel·InvestmentFeasibilityClient)만. design/cost/esg는 인프라만 있고 미소비.
- getNextRecommendedStage는 completedStages만 보고 데이터 준비도 무시.

## 구현(전부 additive·회귀안전)

### 1. finance 노드 추가 (`store/useProjectContextStore.ts`)
- `ModuleKey`에 `"finance"` 추가(기존 6키 불변, 추가만).
- `MODULE_UPSTREAM.finance = ["feasibility", "cost"]` 추가(기존 키 불변).
- `markFinanceUpdated()` 액션 신설: 별도 데이터 필드 없이 `updatedAt.finance`만 stamp.
  - 별도 FinanceData 영속 필드를 만들지 않은 이유: 회귀안전(ProjectSnapshot shape 변경=hydrate 호환 리스크 회피) + finance 화면은 자체 result state로 충분. staleness 추적만 활성화하면 목표 달성.
- 이로써 `isStale("finance")`가 수지·공사비 갱신 후 finance 미갱신을 정확히 판정.

### 2. 공통 자동재계산 훅 (`hooks/useStageAutoRecalc.ts` 신설)
InvestmentFeasibilityClient(:214-228)의 isStale→1회 recalc→stamp로 stale해소→무한루프가드 패턴을 추출:
```ts
useStageAutoRecalc(moduleKey, recalcFn, { enabled?, hasResult? })
```
- 게이트: `enabled && hasResult && isStale(moduleKey)` 충족 시에만 호출.
- 무한루프 가드: `busyRef`(진행중 재진입 차단) + effect 의존성을 `stale` 단일값으로 제한. recalcFn 성공 시 store update*Data가 moduleKey updatedAt을 stamp → 다음 렌더 isStale=false로 자동 종료.
- 과도호출 방지: `hasResult`(최초 산출은 사용자/자동로드에 위임), `enabled`(loading/미인증 게이트).

### 3. design/cost/esg 적용
| 클라이언트 | moduleKey | recalcFn | enabled | hasResult | 비고 |
|---|---|---|---|---|---|
| `components/cad/AutoDesignPanel.tsx` | design | handleGenerate | `!loading` | `!!result` | 로컬 엔진(백엔드X), 부지 갱신 시 설계 재생성. 입력값 현 state 사용=보존 |
| `components/analytics/CostEstimationClient.tsx` | cost | calc | `!loading` | `!!result` | `/cost/estimate-overview` 백엔드. 부지·설계 갱신 시 공사비 재산정 |
| `components/projects/ProjectEsgWorkspaceClient.tsx` | esg | runLca(신설 추출) | `canUseLiveApi && !isSubmittingLca` | `!!lcaResult` | `/esg/lca/calculate` 백엔드. 설계 갱신 시 LCA 재산출. 자재·연면적 입력 보존 |

- ESG는 `handleLcaSubmit`(FormEvent 의존)을 무인자 `runLca`로 핵심 추출하고 제출 핸들러가 호출(동작 동일). 백엔드 과도호출은 hasResult/enabled 3중 게이트로 차단.
- finance도 staleness 트래킹 활성화: `DevelopmentFinancePanel.tsx`가 compute 성공 시 `markFinanceUpdated()` 호출(기존 자체 ref-가드 자동재계산 로직은 불변, stamp만 추가).

### 4. getNextRecommendedStage 개선 (`store/useProjectContextStore.ts`)
- 반환타입/시그니처 불변(`() => string | null`), 로직만 개선.
- 미완료 단계 중 "업스트림 데이터 준비된" 첫 단계 우선 반환, 없으면 순서상 첫 미완료(막다른길 방지).
- `isStageDataReady(state, stage)` 헬퍼 신설: 실데이터(부지면적/주소/용도지역, 설계 GFA, 공사비, 수지매출) 유무로 판정. 업스트림 없는 단계(site-analysis/permit/report)는 항상 ready.
- 기존 호출처(NextStageCta·LifecycleProgressRail·ProjectLifecyclePipeline) 전부 반환값 `as LifecycleStage` 캐스팅만 하므로 호환. NextStageCta는 currentStage 기반 nextOf 우선, 폴백으로만 이 함수 사용 → 개선 효과는 폴백 경로에 적용.

## 회귀 점검 결과
- 기존 isStale 소비처(CadCompliancePanel·InvestmentFeasibilityClient): diff 0(미변경) 확인.
- MODULE_UPSTREAM 기존 6키 불변, finance만 추가.
- getNextRecommendedStage 반환타입 호환(string|null), pending 0이면 null 동일.
- 무한루프 가드: stamp로 stale 해소 + busyRef + stale 단일 의존성.
- import 보존: 3개 클라이언트 모두 `useStageAutoRecalc` import 잔존 확인(린터 트랩 회피).
- 신규 의존성 0.

## 제외(위험)항목 — 후속 권고
- `as never` 타입 전면치환: 이번 범위 외. VerificationBadge/ExpertPanelCard의 `as unknown as Record` 캐스팅은 컨텍스트 직렬화용으로 잔존 — 별도 PR에서 제네릭 타입화 권고.
- GFA SSOT 단일참조 전면 리팩토링: cost는 designData.totalGfaSqm 우선·부지×용적률 폴백, design은 자체 산출 등 다출처. 단일 selector(예: `selectEffectiveGfa(state)`)로 통합 권고(전 화면 소비처 동시 수정 필요=고위험, 별도 계획).
- finance를 LIFECYCLE_STAGES staleness UI(stale 배너)에 노출: 현재 markFinanceUpdated로 추적만 활성화. finance 화면은 자체 ref-가드 자동재계산을 이미 보유하므로 useStageAutoRecalc 미적용(중복 회피). 필요 시 통합 권고.

## 검증
- `cd propai-platform/apps/web && npx tsc --noEmit` → EXIT 0.
- `npx vitest run components/projects/__tests__/ProjectFinanceWorkspaceClient.test.tsx` → 2 passed.
- 디버그코드 스캔(console.log/debugger/TODO/HACK) → 0건.

## 변경 파일
- `store/useProjectContextStore.ts` (수정: finance 노드·markFinanceUpdated·isStageDataReady·getNextRecommendedStage)
- `hooks/useStageAutoRecalc.ts` (신규)
- `components/cad/AutoDesignPanel.tsx` (design 적용)
- `components/analytics/CostEstimationClient.tsx` (cost 적용)
- `components/projects/ProjectEsgWorkspaceClient.tsx` (esg 적용·runLca 추출)
- `components/analytics/DevelopmentFinancePanel.tsx` (finance stamp)
