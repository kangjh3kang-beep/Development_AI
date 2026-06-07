# 143 — Phase2 자동 캐스케이드 회귀검증 보고서

검증 대상: 142_phase2_cascade.md 산출물
검증 일시: 2026-06-07 / 검증자: Verifier (코드 무수정, 검증·보고 전용)
대상 파일: `store/useProjectContextStore.ts`, `hooks/useStageAutoRecalc.ts`, `components/feasibility/FeasibilityEditorV2.tsx`, `lib/useProjectContextStore.cascade.test.ts`(신규)

---

## 판정 요약

**최종 verdict: PASS — 배포 가(可)**
신뢰도: high · Critical 블로커: 0건

| # | 검증 항목 | 판정 | 핵심 근거 |
|---|-----------|------|-----------|
| 1 | 무한루프(Critical) | **PASS** | firstCompute는 `updatedAt[downstream]==null`에서만 true, 산출 즉시 영구 off |
| 2 | isStale 정책 보존 | **PASS** | isStale 함수 본문 diff에 미등장(바이트 불변), 3소비처 회귀 0 |
| 3 | baseline 재시도 | **PASS** | 시그니처 가드+busy(isCalculating)+422게이트 정합, 무한 재호출 없음 |
| 4 | persist/hydrate·DAG | **PASS** | snapOf/withSnap/name/ProjectSnapshot 불변, MODULE_UPSTREAM 순환無 |
| 5 | tsc EXIT 0 / vitest 8 passed | **PASS** | TSC_EXIT=0, vitest 8 tests passed |

---

## 증거 테이블 (fresh, 검증 시점 실행)

| 검사 | 결과 | 명령 | 출력 |
|------|------|------|------|
| 타입 | PASS | `npx tsc --noEmit` (apps/web) | TSC_EXIT=0 (에러 0) |
| 테스트 | PASS | `npx vitest run lib/useProjectContextStore.cascade.test.ts` | 8 passed (1 file) |
| 디버그 잔재 | PASS | grep console/debugger/HACK/FIXME (4파일) | CLEAN |
| diff 범위 | PASS | `git diff --stat` | 3파일 +94/-9, 테스트는 신규(untracked) |

---

## 항목별 상세

### 1. 무한루프 (Critical) — PASS

**(a) firstCompute 영구 off 메커니즘 확인**
- `store/useProjectContextStore.ts:654-663` `isReadyForFirstCompute`: 첫 줄
  `if (s.updatedAt[downstream] != null) return false;` — 한 번이라도 산출되면(stamp) 즉시 false.
- 산출 액션(`updateDesignData:566`, `updateCostData:583`, `updateFeasibilityData:576`,
  `updateEsgData:592`, `updateComplianceData:601`, `markFinanceUpdated:608`)이 전부
  `stampedAt(state, key)`로 `updatedAt[key]`를 채움 → firstCompute 신호 1회 후 영구 해소.
- 테스트 검증됨: cascade.test.ts:51-64 "design 산출 후엔 design 최초산출 불허" PASS.

**(b) 훅 3중 가드 실재 확인** (`hooks/useStageAutoRecalc.ts`)
1. 시그니처 동일 skip — `:86` `if (inputSignature != null && lastSigRef.current === inputSignature) return;`
2. busy 가드 — `:84` `if (!shouldRun || busyRef.current) return;`, `:87` set true, `:90` finally false.
3. useEffect 의존성 `:94` `[shouldRun, inputSignature]` — recalcFn 참조변동 재실행 차단(주석 :92-93).
- `shouldRun = stale || firstCompute` (`:81`), 둘 다 `enabled` 게이트 하(`:77,:80`).

**(c) cost/esg 과금폭주 위험 — 영향범위 PASS(현재 미배선)**
- 실 소비처 3곳 모두 `allowFirstCompute` **미전달** = 기본 false:
  - `components/cad/AutoDesignPanel.tsx:134` `useStageAutoRecalc("design", ...)`
  - `components/projects/ProjectEsgWorkspaceClient.tsx:363` `useStageAutoRecalc("esg", runLca, ...)`
  - `components/analytics/CostEstimationClient.tsx:195` `useStageAutoRecalc("cost", calc, { enabled: !loading, hasResult: !!result })`
- 따라서 신규 firstCompute(백엔드호출) 경로는 **런타임에서 비활성** — 인프라만 추가됨
  (142 "잔여(후속)" 노트와 일치). 현 배포분에서 cost/esg 자동 최초호출로 인한 과금폭주 **불가**.
- 회귀안전: CostEstimationClient는 기존 인자(enabled/hasResult)만 사용 → 동작 불변.

### 2. isStale 정책 보존 — PASS
- `git diff` 결과 `isStale: (downstream)` **함수 본문이 diff에 전혀 등장하지 않음**(신규 주석/타입 라인만).
  즉 `:642-652` 본문(`own == null → return false`, 업스트림 `upAt > own` 비교) 바이트 불변.
- 시그니처 `isStale: (downstream: ModuleKey) => boolean` 불변(`:233`).
- 기존 3소비처 회귀 0:
  - `CadCompliancePanel.tsx:203` `!!checkResult && isStale("compliance")` — own 가드(checkResult) 동일.
  - `InvestmentFeasibilityClient.tsx:218` `isStale("feasibility")` — memo deps 불변.
  - `FeasibilityEditorV2.tsx:98` `isStale("feasibility")` memo — 동일 사용.
- 회귀 테스트 포함: cascade.test.ts:108-133 (own==null→false / 산출후 업스트림 최신→true) PASS.

### 3. baseline 재시도 — PASS
- `FeasibilityEditorV2.tsx:53` `baselineTriedRef(boolean)` → `baselineTriedSigRef(string|null)` 교체(diff 확인).
- 시그니처 `:81` `${address}|${landAreaSqm||0}|${pnu}` — 면적이 늦게 채워지면 sig 변경 → 1회 재호출.
- 동일 sig skip — `:82` `if (baselineTriedSigRef.current === sig) return;`
- busy 가드 — `:78` `if (result || isCalculating) return;` (진행 중·결과존재 시 차단).
- **무한 재호출 불가 근거**: `runBaseline`(use-feasibility-v2-store.ts:219-249)은 성공 시
  `result`만 set(`:231`)하고 `useProjectContextStore.siteAnalysis`를 **건드리지 않음** →
  effect 의존성 `siteAnalysis`(`:91`)가 재변동하지 않음. 성공 후 `result` 채워져 `:78` 가드로 영구 종료.
- 422 게이트 정합: 입력부족 시 `:241-242` `baselineNeedsInput=true`(에러표시 대신 입력유도). 면적
  채워지면 sig 변경 → baseline 재호출 → `:233` `baselineNeedsInput=false` 해제. 정합 확인.
- 보조: feasibility 산출 후 `updateFeasibilityData`(`:63`)가 feasibility stamp → 별도 stale 경로(`:95-108`)도
  costAtCalc 갱신으로 자기종료.

### 4. persist/hydrate·DAG — PASS
- `ProjectSnapshot` shape 불변(`:143-154`), `snapOf`(`:301`)·`withSnap`(`:412`) diff 미등장 = 불변.
- persist `name: "propai-project-context"`(`:751`) 불변 → hydrate 키 동일, 기존 저장분 호환.
  setProject 복원 경로(`:497-513`)는 모든 필드 `?? 폴백` 유지 → 구 스냅샷 shape 안전.
- `MODULE_UPSTREAM`(`:170-179`) DAG 무순환:
  site→design→{cost,esg,compliance}, cost→feasibility, {feasibility,cost}→finance.
  역방향 간선 없음 → `isReadyForFirstCompute`의 `ups.every(isModuleReady)`는 위상순 유한 종료.
- `isModuleReady`(`:343-372`)는 순수 읽기 판정(set 없음) → 호출 부작용 0.

### 5. tsc / vitest — PASS
- `npx tsc --noEmit` → **EXIT 0** (apps/web 전체, 신규 셀렉터/옵션 타입 정합).
- `npx vitest run lib/useProjectContextStore.cascade.test.ts` → **8 passed** (firstCompute 6 + isStale 보존 2).

---

## Gap / 잔여 (배포 차단 아님)
- (Low) firstCompute 인프라는 추가됐으나 다운스트림 패널 3곳에서 미배선(allowFirstCompute=false).
  → 의도된 단계적 적용(142 "잔여"). 향후 배선 시 inputSignature 필수 지정으로 cost/esg 과금가드 확인 필요.
- (Info) cascade.test.ts는 untracked(신규 파일) — 커밋 시 포함 필요. tsc/vitest는 정상 인식.
- (Info) FeasibilityEditorV2 CRLF 경고(git) — 기능 무관, 기존 줄끝 정책.

## Recommendation
**APPROVE — 배포 가(可).** Critical 4종(무한루프·과금폭주·persist깨짐·기존소비처 회귀) 전부
실증적으로 해소 확인. firstCompute 백엔드 경로는 현 배포에서 미활성(과금 위험 없음),
isStale·persist·DAG 불변, tsc EXIT 0 / vitest 8 passed.
