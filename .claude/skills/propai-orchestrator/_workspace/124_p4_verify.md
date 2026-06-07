# P4 모세혈관 일반화 — 회귀검증 보고서

검증자: Verifier (코드 수정 없음, 검증·보고 전용)
루트: `/home/kangjh3kang/My_Projects/Development_AI` · 프론트: `propai-platform/apps/web`
검증일: 2026-06-07

## 종합 판정

**상태: PASS** · 신뢰도: 높음 · Critical 차단 이슈: 0건
**배포 가부: 가능(APPROVE)** — 무한루프/API폭주/막다른길/persist깨짐 모두 미발견. 단 WARN 2건은 후속 권고.

| 검사 | 결과 | 명령/근거 | 출력 |
|------|------|-----------|------|
| 타입체크 | PASS | `npx tsc --noEmit` | EXIT 0 |
| 단위테스트 | PASS | `npx vitest run ...ProjectFinanceWorkspaceClient.test.tsx` | 2 passed, EXIT 0 |
| 기존 isStale 소비처 diff | PASS | `git status --porcelain` | 미변경(0 diff) |
| 신규 의존성 | PASS | git status | 0 (훅 1개 신규 .ts만) |

---

## 항목별 검증

### 1. 무한루프 위험 (Critical) — PASS

`hooks/useStageAutoRecalc.ts:55-65`

- 게이트: `stale = enabled && hasResult && isStale(moduleKey)` (`:55`). 셋 중 하나라도 false면 effect 본문 미실행.
- 재진입 가드: `busyRef`(`:53,58-62`). 비동기 recalc 진행 중 재렌더 시 `busyRef.current===true`로 재호출 차단.
- 의존성 배열 `[stale]` 단일값(`:65`). recalcFn 참조 변동으로는 트리거되지 않음.
- **루프 종단 메커니즘(핵심)**: recalcFn 성공 → store `update*Data`가 해당 moduleKey의 `updatedAt`을 `Date.now()`로 stamp(`store:485-532`, `stampedAt:331-337`) → 다음 렌더 `isStale(moduleKey)`가 false(`store:570-580`: 자신의 updatedAt ≥ 모든 업스트림) → `stale=false` → effect 미재실행. 루프 확실히 끊김.
- **API폭주 차단(ESG/cost 백엔드 호출)**:
  - cost(`CostEstimationClient.tsx:195`): `enabled:!loading, hasResult:!!result`. 결과 없으면(최초) 자동호출 안 함, 로딩 중 차단. `calc`가 `/cost/estimate-overview` 성공 시 `updateCostData`(`:182-187`)로 cost stamp → stale 해소.
  - esg(`ProjectEsgWorkspaceClient.tsx:356-359`): `enabled:canUseLiveApi && !isSubmittingLca, hasResult:!!lcaResult`. 미인증/제출중/결과없음 3중 차단. `runLca` 성공 시 `updateEsgData`(`:317-321`)로 esg stamp.
  - 따라서 각 업스트림 1회 변경당 다운스트림 백엔드 호출 정확히 1회.
- **stale=false 초기상태 보강**: `isStale`은 자신의 `updatedAt`이 null이면 항상 false(`store:575`). 최초 산출 전 자동트리거 원천 차단.
- **캐스케이드 무한루프 여부**: MODULE_UPSTREAM은 DAG(site→design→cost→feasibility→finance, esg←design, compliance←site+design). 사이클 없음(`store:170-179`). design 갱신 → cost stale → cost 재계산·stamp → feasibility stale … 각 단계가 자기 키만 1회 stamp, 상류를 다시 stale화하지 않음 → 캐스케이드는 유한·1패스. **무한루프 없음.**

근거상 Critical 무한루프/과금폭주 위험 없음.

### 2. getNextRecommendedStage 하위호환 — PASS

`store/useProjectContextStore.ts:231,556-568`

- 시그니처 `() => string | null` 불변(`:231`).
- 호출처 3곳 전부 `as LifecycleStage(|null)` 캐스팅만 사용:
  - `NextStageCta.tsx:51,56` — `nextOf(currentStage)` 우선, 폴백으로만 사용(`:48-57`). 기존 우선경로 보존.
  - `LifecycleProgressRail.tsx:55`, `ProjectLifecyclePipeline.tsx:51` — 반환값 그대로 시각화.
- **막다른길 방지 검증**: `pending` 비면 `null`(완료, 기존동일), 아니면 `find(isStageDataReady)` → 없으면 `?? pending[0]`(`:565-567`). 항상 미완료 단계 또는 null 반환 → 추천불가(undefined·막힘) 없음.
- `isStageDataReady`(`:306-329`): 업스트림 없는 site-analysis/permit/report 및 default는 항상 true. 데이터 없어도 폴백 `pending[0]`로 진행 보장.

### 3. MODULE_UPSTREAM / ModuleKey 추가 — PASS

- `ModuleKey`에 `"finance"` 추가, 기존 6키(siteAnalysis/design/cost/feasibility/esg/compliance) 불변(`:160-167`).
- `MODULE_UPSTREAM.finance = ["feasibility","cost"]` additive, 기존 항목 불변(`:170-179`).
- `markFinanceUpdated`(`:534-538`): `updatedAt`만 stamp, **ProjectSnapshot shape 미변경**.
  - `ProjectSnapshot.updatedAt: Partial<Record<ModuleKey, number>>`(`:153`). finance는 선택키이므로 구 hydrate 스냅샷(finance 키 없음)도 호환. 신규 데이터 필드 미추가 → persist 역호환 안전.
  - `setProject` 복원경로 `updatedAt: snap.updatedAt ?? {}`(`:440`)로 구 스냅샷 폴백 보장.
- **persist 깨짐 없음.**

### 4. 기존 isStale 소비처 동작 불변 — PASS (diff 0)

- `git status --porcelain`: 변경 파일은 `store/useProjectContextStore.ts`(M)와 신규 `hooks/useStageAutoRecalc.ts`(??)뿐.
- `CadCompliancePanel.tsx`(`:88,203-204`), `InvestmentFeasibilityClient.tsx`(`:143,218-220`) **미변경(diff 0)** 확인.
- 추가 소비처 `FeasibilityEditorV2.tsx:44,92-94`도 미변경. isStale 로직(`store:570-580`) 동작 동일.

### 5. design/cost/esg 적용 — 입력보존·과도호출 방지 PASS

- **design**(`AutoDesignPanel.tsx:97-137`): `editedArea`/`editedZone` 플래그로 사용자 수정값 보존(`:62-63,78-83`), 자동주입은 미편집시만. recalc는 현재 state 사용 → 입력 보존. `enabled:!loading, hasResult:!!result`로 과도호출 차단. 로컬엔진(백엔드X)이라 비용 무관.
- **cost**(`CostEstimationClient.tsx:159-195`): `editedGfa` 플래그로 수정 GFA 보존(`:162,164`). 설계 GFA 우선·부지×용적률 폴백. 백엔드 호출은 hasResult/enabled 게이트.
- **esg**(`ProjectEsgWorkspaceClient.tsx:290-359`): `handleLcaSubmit`(FormEvent)을 무인자 `runLca`로 추출(`:290-351`), 제출핸들러가 `runLca` 호출(`:348-351`)로 동작 동일. recalc는 현재 `lcaMaterials`/`floorArea` state 사용(`:295-310`) → 자재·연면적 입력 보존. 3중 게이트로 백엔드 과도호출 차단.
- **finance**(`DevelopmentFinancePanel.tsx:71-104`): 기존 `lastComputedCostRef` 가드 불변(`:69,89,102`), compute 성공 시 `markFinanceUpdated()` stamp만 추가(`:91`). useStageAutoRecalc 미적용(자체 ref가드 중복회피) — 설계대로.

### 6. 빌드/테스트 — PASS

- `cd propai-platform/apps/web && npx tsc --noEmit` → **EXIT 0** (재확인).
- `npx vitest run components/projects/__tests__/ProjectFinanceWorkspaceClient.test.tsx` → **2 passed, EXIT 0**.
- 신규 로직(useStageAutoRecalc·getNextRecommendedStage·isStageDataReady) 전용 단위테스트는 **부재**(store 대상 .test 0건) — WARN 참조.

---

## Gaps / WARN

- **WARN-1 (테스트 커버리지 중간 리스크)**: 신규 핵심 로직(무한루프 가드 훅·getNextRecommendedStage 데이터준비 분기·isStageDataReady·MODULE_UPSTREAM.finance 캐스케이드)에 대한 단위테스트 없음. 코드 정독으로 루프종단·DAG무사이클을 확증했으나 회귀 자동방어선 부재. 후속 권고: useStageAutoRecalc(stale→1회→stamp→종료) + isStale 캐스케이드 + getNextRecommendedStage 막다른길 케이스 vitest 추가. 위험: 중.
- **WARN-2 (저위험)**: cost 재계산 시 `calc`가 `gfa`(local state)에 의존하나, GFA 자동주입 useEffect(`CostEstimationClient.tsx:160-170`)와 recalc가 별개 트리거. 루프 종단은 cost stamp로 보장되어 영향 없음(설계 GFA 변경→effect가 gfa 갱신→stale로 recalc 1회). 동작상 문제 없으나 GFA 다출처(설계/부지폴백)는 산출물 123이 명시한 후속(selectEffectiveGfa SSOT 통합) 권고 유효. 위험: 저.

## 권고

**APPROVE** — Critical 4종(무한루프·API폭주·막다른길·persist깨짐) 모두 미발견, tsc EXIT 0, 기존 소비처 diff 0, additive 보존 확인. 배포 가능. 단 WARN-1(신규 로직 단위테스트)은 다음 PR에서 보강 권고.
