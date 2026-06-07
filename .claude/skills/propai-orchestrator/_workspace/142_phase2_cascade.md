# 142 — Phase2: 자동 캐스케이드 완결 (업스트림 지연 채움 → 다운스트림 자동 최초산출)

담당 파일: `store/useProjectContextStore.ts`, `hooks/useStageAutoRecalc.ts`, `components/feasibility/FeasibilityEditorV2.tsx`
원칙: 무목업 · 회귀안전 최우선(additive) · push/배포 금지 · 무한루프 절대금지.

## 문제(감사 131 확정)
1. `isStale(downstream)`은 다운스트림이 한 번도 산출 안 됨(`own==null`)이면 `false`를 반환(무한 트리거 방지). 부작용: **부지가 늦게 채워져도** 수지·설계 등 다운스트림이 **자동 최초산출되지 않고** 사용자 진입을 대기.
2. `useStageAutoRecalc`는 `enabled && hasResult && isStale`라 `hasResult=false`(최초)면 자동산출 경로 자체가 없음.
3. `FeasibilityEditorV2`의 `baselineTriedRef`(boolean)는 **1회만** baseline 시도 → 진입 후 면적이 늦게 채워져도 재시도 안 함.

## 설계 — 최초 자동산출 허용(별도 경로, isStale 정책 보존)

### A. store: `isReadyForFirstCompute(downstream)` 신규 셀렉터 (additive)
- 반환 조건: **모든 직접 업스트림이 준비됨(실데이터 존재)** `&&` **다운스트림이 아직 미산출(`updatedAt[downstream]==null`)**.
- `isStale`의 "최초제외(`own==null→false`)" 정책은 **그대로 보존** → 기존 소비처(CadCompliancePanel:203, InvestmentFeasibilityClient:218, FeasibilityEditorV2 내부 memo) 동작 불변.
- 업스트림이 없는 모듈(`siteAnalysis`)은 `false`(최초산출 강제 안 함, 사용자/로드 담당).
- 업스트림 준비 판정은 신규 `isModuleReady(s, key)` 단일 진실원:
  - site=`hasSiteData`(면적>0 또는 주소 또는 zoneCode), design=`hasDesignData`(GFA>0), cost=`hasCostData`(공사비>0), feasibility=`hasFeasibilityData`(매출>0), finance=`updatedAt.finance` stamp, esg=탄소>0, compliance=판정값 존재. (이미 store에 있던 `has*Data`/완성도 판정 로직과 동일 기준 재사용 — 신규 가정 없음.)
- DAG 유한성: `MODULE_UPSTREAM`는 순환 없는 DAG(site→design→{cost,esg,compliance}, cost→feasibility, {feasibility,cost}→finance). 캐스케이드는 위상순으로 유한 종료 보장.

### B. hooks: `useStageAutoRecalc` 옵션 2개 추가 (additive·기본 off)
- `allowFirstCompute?: boolean`(기본 **false** → 기존 소비처 동작 보존). true면 `isReadyForFirstCompute(moduleKey)`도 트리거로 사용.
- `inputSignature?: string|number|null`. 백엔드 호출 다운스트림(cost/esg) 과금·폭주 방지: **동일 시그니처면 skip**(`lastSigRef` 비교, P4 DevelopmentFinancePanel:102 `lastComputedCostRef` 패턴 동형).
- 트리거 = `stale(기존) || firstCompute(신규)`. 둘 다 `enabled` 게이트 하.

### C. FeasibilityEditorV2: baseline 면적변경 재시도
- `baselineTriedRef`(boolean) → `baselineTriedSigRef`(string|null)로 교체.
- 시그니처 = `address|landAreaSqm|pnu`. 동일 시그니처면 skip, **면적/주소/PNU가 늦게 채워지면(시그니처 변경) baseline 1회 재호출**.
- 422 게이트와 정합: 면적이 생기면 시그니처 변경 → baseline 자동 재호출 → `baselineNeedsInput` 해제.

## 무한루프 가드(3중) 근거
1. **시그니처 동일 skip**: baseline=`baselineTriedSigRef`, 훅=`lastSigRef`(inputSignature 지정 시), P4=`lastComputedCostRef`. 동일 입력이면 재호출 없음.
2. **busy 가드**: 훅=`busyRef`, FeasibilityEditorV2 baseline=`isCalculating` 체크. 진행 중 재진입 차단.
3. **산출 후 stamp로 신호 해소**: `update*Data`/`markFinanceUpdated`가 `updatedAt[downstream]` stamp → `isReadyForFirstCompute`는 즉시 `false`(own!=null), `isStale`도 own 갱신으로 해소. firstCompute가 1회로 종료.
- 추가: `firstCompute`는 `updatedAt[downstream]==null`에서만 true → 산출 즉시 영구 off(시그니처 미지정이어도 1회 보장).

## 회귀 점검(불변)
- `isStale` 시그니처/반환·정책 **불변**. 기존 3개 소비처 그대로.
- `useStageAutoRecalc` 신규 옵션은 기본값으로 기존 호출(인자 0~1개) 동작 동일. 기존 호출처 코드 변경 0.
- `ProjectSnapshot`/persist shape **불변**(`snapOf`·`withSnap` 미변경, name `propai-project-context` 유지).
- import 보존: `git diff` import 라인 변경 0(store/hook). FeasibilityEditorV2 `useRef` 계속 사용. 린터 트랩 없음.
- 디버그 잔재 0(console.log/debugger/HACK/FIXME grep clean).

## 검증
- `npx tsc --noEmit` → **EXIT 0**.
- `npx vitest run lib/useProjectContextStore.cascade.test.ts` → **8 passed** (최초산출 허용 6 + isStale 정책보존 2). 산출 후 firstCompute=false(무한루프 차단), isStale own==null→false 보존 회귀검증 포함.
- 신규 테스트: `lib/useProjectContextStore.cascade.test.ts`(vitest include가 `lib/**`라 store/가 아닌 lib/에 배치).

## 잔여(후속 가능, 본 작업 범위 외)
- 다운스트림 컴포넌트(DesignStudio/CostEstimationClient/ProjectEsgWorkspaceClient 등)에서 `useStageAutoRecalc(..., { allowFirstCompute: true, inputSignature })`를 실제로 켜는 배선은 각 패널 소유자와 충돌 회피 위해 미적용(인프라만 추가). FeasibilityEditorV2는 baseline 경로로 최초산출 자체 처리.
