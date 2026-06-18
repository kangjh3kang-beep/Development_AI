# PropAI Phase B 구현 블루프린트 — 분석 오케스트레이션 (가이드 기본 + 자유 조합)

> 승자 설계 = **B-클린레지스트리**(4레이어 분리 + 레지스트리 lint), graft = A(charge_service `pipeline.py:130` 선례·정확 파일경로·provenance 한계 정직고지) + C(프로필 `order`/`defaultMode`·RunProgressTimeline·ModeSwitcher·프로젝트별 복원).
> 베이스: `/home/kangjh3kang/My_Projects/Development_AI_feature/propai-platform` (프론트 `apps/web`, 백엔드 `apps/api`)
> 원칙: **무목업 / 무회귀(additive) / 코드 미수정(이 문서는 설계) / 과금=관리자설정·미설정시무료 / 한국어**
> 작성일: 2026-06-18

---

## 0. 설계 골격 — 4레이어 + 핵심 결정

```
[L0 레지스트리(SSOT·정적)]  apps/web/lib/orchestration/node-registry.ts
   NODES: AnalysisNode[]  — 9노드 정적 선언(불변 메타). 단 하나의 진실 출처.
        │ (소비)
[L1 그래프 엔진(순수함수)]  apps/web/lib/orchestration/dependency-graph.ts
   computeClosure / topoSort / nodeStale / currentSignature / moduleKeyOf / guidedOrder.
   store·React 비의존 순수 TS → 단위테스트 100%, 무회귀 0.
        │
[L2 실행 슬라이스(별도 store)]  apps/web/store/useOrchestrationStore.ts
   runMode·picked·plan·nodeResult·runPlan·runNode·resolveInputs.
   useProjectContextStore는 **데이터 SSOT로 불변** — "읽기 구독 + update*Data 호출"만.
   자체 persist 키 "propai-orchestration"(version 1). 데이터 store(propai-project-context, version 1) 미접촉.
        │
[L3 소비 UI]  components/orchestration/* + 리팩토링된 LifecycleStageViews / 13페이지
   OrchestratorPanel(ModeSwitcher + AnalysisModuleSelector + PlanPreview + RunProgressTimeline).
```

### 검증 완료 사실(소스 대조 — load-bearing)

| 사실 | 위치 | 내용 |
|------|------|------|
| `ModuleKey`(7) | `useProjectContextStore.ts` L244-252 | siteAnalysis/design/cost/feasibility/finance/esg/compliance |
| `MODULE_UPSTREAM`(7키 DAG) | L255-264 | finance:["feasibility","cost"], cost:["siteAnalysis","design"], compliance:["siteAnalysis","design"] |
| `isStale` 최초미산출=false | L1132-1142 | `own==null → return false`(무한루프 방지) |
| `isReadyForFirstCompute` | L1144-1153 | 자체 미산출 && 모든 직접 업스트림 `isModuleReady` |
| persist `version:1` + `purifyPersistedContextState` migrate | L1246-1254 | **계정격리·오염정화 보안 민감경로 → 미접촉** |
| `useStageAutoRecalc` 게이트 | `useStageAutoRecalc.ts` L77-94 | `shouldRun = stale||firstCompute`, `busyRef`, `inputSignature` |
| `AnalysisModuleSelector` controlled·leaf집계·3-state | `AnalysisModuleSelector.tsx` L22-95 | `coinCost`/`required`/`locked`/`children`. 실행·과금·closure 안 함 |
| selector 채택 2곳 | `components/operations/MarketInsightsWorkspaceClient.tsx`, `components/analytics/OperationsIntelligenceWorkspaceClient.tsx` | `fee("key")` = `balance.module_fees?.[k] ?? 0` (하드코딩 금지) |
| `charge_service` stage 디스패치 | `services/billing/billing_service.py` L508-509 | `action.startswith("stage:") → service_fee_stage(name)` |
| `service_fee_stage` 미설정=0 | `core/billing.py` L161-162 | `service_fees.stages.get(stage, 0)` |
| `analysis_module_fees()` | `core/billing.py` L173-175 | 미설정 빈dict=무료 |
| charge_service `stage:` **실배선 선례** | `routers/pipeline.py` L130 | `await billing_service.charge_service(_db, uid, f"stage:{stage_name}")` ← 노드 과금은 **신규가 아니라 기존 패턴 복제** |
| LifecycleStageViews StageType(8)·목업 3탭 | `components/projects/LifecycleStageViews.tsx` L30-38 / L269,L362,L399 | legal_compliance/permit_portal/operations 하드코딩 |
| LIFECYCLE_STAGES(11) | `useProjectContextStore.ts` L186-201 | site-analysis,legal,design,bim,construction,feasibility,finance,esg,permit,report,operations |

**핵심 결정**: `ModuleKey`(7) 유니온은 **절대 미접촉**. Phase B의 9노드는 `ModuleKey`보다 세분화된 **오케스트레이션 노드(NodeId)** 레이어다. 각 노드는 자신이 stamp하는 `ModuleKey`(`moduleKey`)로 store의 `isStale`/`MODULE_UPSTREAM`/`useStageAutoRecalc`와 결합한다. 노드 그래프=UX/실행 레이어, `MODULE_UPSTREAM`=staleness/폐포 SSOT — **두 그래프를 어댑터로 매핑**하되 store DAG는 불변.

---

## 1. 분석 DAG 노드 레지스트리 — 최종 스키마

### 1-A. 타입 (신규 `apps/web/lib/orchestration/types.ts`)

```ts
import type { ModuleKey, LifecycleStage } from "@/store/useProjectContextStore";

/** 노드가 읽고/쓰는 SSOT 데이터 슬롯 — useProjectContextStore 데이터 슬롯명에 정합 */
export type SsotSlot =
  | "siteAnalysis" | "designData" | "costData"
  | "feasibilityData" | "esgData" | "complianceData"
  | "financeStamp";   // finance는 데이터필드 없이 markFinanceUpdated() stamp만

/** 노드 식별자 — 9개 실무 스토리라인 노드(ModuleKey 7개와 별개 집합) */
export type NodeId =
  | "land" | "legal" | "recommend" | "design" | "audit"
  | "sales" | "qto" | "feasibility" | "finance";

/** 전문가 패널 관점(다관점 협업 렌즈) */
export type Lens =
  | "site" | "legal" | "market" | "design"
  | "feasibility" | "esg" | "construction";

/** [graft B] 보고서 참여 계약 — bank-report/generate·report 단계가 수집하는 섹션 */
export interface ReportContract {
  sectionKey: string;          // 보고서 섹션 키(미참여면 "")
  fields: string[];            // 이 노드가 채우는 보고서 필드(없으면 비참여)
  unavailableLabel: string;    // unavailable 시 정직 표기 라벨(0 강제 금지)
}

/** 입력 슬롯 자동해소 스펙 (standalone 모드 핵심) */
export interface SsotInputSpec {
  slot: SsotSlot;                          // 읽을 store 슬롯
  field?: string;                          // 세부 필드(예: "landAreaSqm"). 없으면 슬롯 존재로 판정
  readyCheck: (s: ProjectContextSnapshot) => boolean;   // store isModuleReady 기준 재사용
  resolution: ("ssot" | "upstream-suggest" | "manual")[];  // 자동해소 우선순위
  manualPrompt?: string;                   // SSOT 미확보 시 수동입력 라벨
  /** [graft A] feasibility/finance/compliance는 ProvenanceModule 밖 → 수동입력 merge가드 없음 정직표기 */
  provenanceGuarded: boolean;
}

/** 산출 후 store 환류 매핑 */
export interface SsotOutputSpec {
  updateAction:
    | "updateSiteAnalysis" | "updateDesignData" | "updateCostData"
    | "updateFeasibilityData" | "updateEsgData" | "updateComplianceData"
    | "markFinanceUpdated";
  source: "auto";              // 노드 산출은 항상 auto(머지가드가 user값 보존)
  partial?: boolean;           // true=부분패치(예: sales→feasibilityData 매출만)
}

export interface AnalysisNode {
  id: NodeId;
  label: string;                        // 한국어 노드명
  storyOrder: number;                   // 스토리라인 위상순(가이드 기본 정렬)
  storylineStage: LifecycleStage;       // LIFECYCLE_STAGES 11단계 매핑(가이드 진행레일)
  moduleKey: ModuleKey | null;          // staleness/폐포 매핑. null=파생/보조(legal·recommend·audit·sales·qto 중)
  upstream: NodeId[];                   // 노드 DAG(폐포 SSOT). MODULE_UPSTREAM의 노드레벨 정밀화

  ssotInputs: SsotInputSpec[];          // 사실근거 입력(모세혈관 상류 컨텍스트)
  ssotOutputs: SsotOutputSpec[];        // 산출 슬롯(하류 사실근거). [] = store 비기록(표시노드)

  runner: { method: "GET" | "POST"; path: string; bodyBuilder: string };  // 분석 엔드포인트
  expertInterpreter: string | null;    // 노드 전담 해석 LLM interpreter id(백엔드)
  expertPanel: boolean;                 // true → /expert-panel/analyze 다관점 협업
  verify: { crossValidate: boolean; verifyAnalysis: boolean };  // (d) 가드 계약
  billingKey: string | null;            // charge_service action. "stage:<name>" 규약. null=과금없음
  reportContract: ReportContract;       // [graft B] 보고서 참여
  lens: Lens;
  groundingSources: string[];           // (a) 사실기반 그라운딩 출처(unavailable 정직 대상)
  available: boolean;                    // false면 selector locked(audit=심의엔진 미머지 시)
  icon: string;
}
```

> `ProjectContextSnapshot`/`ProjectContextState`는 `useProjectContextStore`에서 export된 타입. `node-registry.ts`는 store를 **타입만 import**(런타임 의존 0).

### 1-B. 9개 노드 정의표

| id | label | storyOrder / storylineStage | moduleKey | upstream | ssotInputs(slot) | ssotOutputs(action) | runner | expertInterpreter | expertPanel | verify | billingKey | lens |
|----|-------|---------|-----------|----------|------------------|---------------------|--------|-------------------|:-----------:|:------:|-----------|------|
| **land** | 토지·부지분석 | 1 / `site-analysis` | `siteAnalysis` | — | (주소/PNU 직접입력) | `updateSiteAnalysis` | `POST /zoning/analyze` (+`/zoning/special-parcels`,`/zoning/nearby-map`) | `SiteAnalysisInterpreter` (`_attach_site_ai`) | ✕ | cross✓ verify✓ | `stage:land` | site |
| **legal** | 법률·규제검토 | 2 / `legal` | `compliance` | land | `siteAnalysis` | `updateComplianceData` | `POST /regulation/analyze` (+`/permits/ai-analysis` 보조) | `RegulationInterpreter` | ✓ (상위법령↔조례 충돌) | cross✓ verify✓ | `stage:legal` | legal |
| **recommend** | 개발방식·사업모델 추천 | 3 / `permit` | `null`(파생) | land, legal | `siteAnalysis`,`complianceData` | `[]` (표시·선택지) | `POST /development-methods/optimal-recommend` (+`/scenarios`,`/evaluate`) | `DevelopmentMethodInterpreter` | ✓ (15모델 다관점) | cross✓ verify✓ | `stage:recommend` | legal |
| **design** | 건축개요·설계 AI | 4 / `design` | `design` | land, recommend | `siteAnalysis`,`complianceData` | `updateDesignData` | `POST /design/{id}/bim/generate` (+`/design/{id}/mass`) | `DesignInterpreter` | ✕ | cross✓ verify✓ | `stage:design` | design |
| **audit** | AI 설계심의 (핵심1) | 5 / `design` | `null`(검증) | design, legal | `designData`,`complianceData` | `[]` (검증결과) | `POST /design-audit/run` → (엔진 main머지 후) `POST /deliberation/analyze` BFF 어댑터 | (외부 엔진 소유 — 미접촉) | n/a (엔진내부) | 엔진자체 | `stage:audit` | design |
| **sales** | 분양성·분양가 | 6 / `feasibility` | `null`(피드) | land, design | `siteAnalysis`,`designData` | `updateFeasibilityData`(partial: 매출만) | `POST /market/report` (+`pricing_band`) | `MarketInterpreter` | ✓ (거래사례비교↔지불여력) | cross✓ verify✓ | `stage:sales` | market |
| **qto** | BIM적산·공사비 (핵심2) | 7 / `construction` | `cost` | design | `designData` | `updateCostData` | `POST /cost/estimate-overview` (+BOQ/QTO) | `CostInterpreter` | ✕ | cross✓ verify✓ | `stage:qto` | construction |
| **feasibility** | 사업수지·ROI | 8 / `feasibility` | `feasibility` | sales, qto, land, design | `siteAnalysis`,`designData`,`costData`,`feasibilityData`(매출) | `updateFeasibilityData` | `POST /api/v2/feasibility/calculate` (+`compare`,`cashflow`) | `FeasibilityInterpreter` | ✓ (ROI 분기·할루시네이션) | cross✓ verify✓ | `stage:feasibility` | feasibility |
| **finance** | PF·개발금융 | 9 / `finance` | `finance` | feasibility, qto | `feasibilityData`,`costData` | `markFinanceUpdated` | `POST /api/v2/feasibility/development-finance` (+`/bank-report/generate`) | `FinanceInterpreter` | ✓ (PF구조·금리 분기) | cross✓ verify✓ | `stage:finance` | feasibility |

### 1-C. 노드 DAG(폐포 SSOT) — `MODULE_UPSTREAM`(7키)을 9노드로 정밀화

```
land:        []
legal:       [land]
recommend:   [land, legal]
design:      [land, recommend]
audit:       [design, legal]
sales:       [land, design]
qto:         [design]
feasibility: [sales, qto, land, design]
finance:     [feasibility, qto]
```

**정합 검증·주의사항(소스 대조)**:
- `MODULE_UPSTREAM` 일관성: `feasibility`의 store 업스트림 `["siteAnalysis","design","cost"]` ⊆ 노드 폐포(`land`/`design`/`qto`). `finance`의 store 업스트림 `["feasibility","cost"]` = 노드 `[feasibility, qto]`. dev-time assert로 드리프트 감지(§8 R-드리프트).
- **sales↔feasibility 동일 슬롯(`feasibilityData`) 경합** [graft C→B R3]: `sales`는 `updateFeasibilityData`로 **매출(salesPriceWon/totalRevenueWon)만 부분패치**(`partial:true`), `moduleKey` stamp 안 찍음. `feasibility`가 ROI 최종 산출 + `feasibility` stamp. `updateFeasibilityData`는 merge 패치라 충돌 없음. 노드 엣지 `sales→feasibility`로 topoSort가 sales를 먼저 실행하게 강제.
- `recommend`/`audit`는 `moduleKey=null` → store staleness 미참여. L2 `nodeUpdatedAt[NodeId]`로 staleness 파생 + `markStageComplete("permit"/"design")` 신호.

---

## 2. 4실행모드 엔진 — 최종 설계

### 2-A. 배치 위치(어디에 두나)

| 책무 | 위치 | 근거(무회귀) |
|------|------|------|
| 노드 레지스트리(불변 메타) | `lib/orchestration/node-registry.ts`(순수 데이터) | 추측 없는 SSOT, 테스트 용이 |
| 폐포·topoSort·signature·사이클가드·어댑터 | `lib/orchestration/dependency-graph.ts`(순수함수) | store/React 비의존 |
| LifecycleStage↔NodeId↔StageType 어댑터 | `lib/orchestration/stage-node-map.ts` | 식별자 3집합 봉합 |
| runMode·picked·plan·nodeResult·실행·과금 | **별도 store** `store/useOrchestrationStore.ts` | 데이터 SSOT(propai-project-context) 미접촉 |
| 입력 자동해소/수동입력 폴백 | 엔진 메서드 `resolveInputs` + `InputResolveModal` | SSOT read → 없으면 업스트림 제안/수동 |
| isStale/isReadyForFirstCompute 스킵 | **위임** — 기존 셀렉터 그대로 호출 | 신규 staleness 미구현 |
| 모세혈관 자동재계산(마운트 중 stale 1회) | **기존 `useStageAutoRecalc` 무수정** | 노드 runner 환류=update*Data=기존 계약 |
| 선택 UI | `AnalysisModuleSelector`(레지스트리 구동, props 불변) | controlled 그대로 |
| [graft C] 프로젝트별 모드/선택/순서 복원 | **별도 store에 projectId 키 맵**(store migrate 미접촉) | C의 store 수정 회피하며 복원 UX 확보 |

### 2-B. 순수 그래프 엔진 (`dependency-graph.ts`)

```ts
import { NODES } from "./node-registry";
import type { NodeId, AnalysisNode } from "./types";
import type { ModuleKey } from "@/store/useProjectContextStore";

const BY_ID: Record<NodeId, AnalysisNode> =
  Object.fromEntries(NODES.map(n => [n.id, n])) as Record<NodeId, AnalysisNode>;

/** 선택집합 → 의존성 폐포(상류 전부 포함, 전이). DFS, 사이클가드. */
export function computeClosure(picked: NodeId[]): NodeId[] {
  const seen = new Set<NodeId>(); const stack = [...picked];
  while (stack.length) {
    const id = stack.pop()!; if (seen.has(id)) continue; seen.add(id);
    for (const up of BY_ID[id].upstream) stack.push(up);
  }
  return [...seen];
}

/** 폐포 → 위상정렬 실행순서(Kahn). storyOrder tie-break. 사이클이면 throw. */
export function topoSort(ids: NodeId[]): NodeId[] { /* in-degree Kahn over upstream, storyOrder tiebreak */ }

/** [graft B R1] topo 결과를 레벨(rank)별 그룹으로 — 동일 레벨은 병렬 실행 가능. */
export function topoLevels(ids: NodeId[]): NodeId[][] { /* rank = max(upstream rank)+1 */ }

/** 노드→ModuleKey(있으면) — store isStale/isReadyForFirstCompute에 넘길 키 */
export function moduleKeyOf(id: NodeId): ModuleKey | null { return BY_ID[id].moduleKey; }

/** moduleKey=null 노드용 입력 시그니처(ssotInputs 값 안정 직렬화 해시). */
export function currentSignature(id: NodeId, s: ProjectContextSnapshot): string { /* JSON stable hash of ssotInputs slot/field values */ }

/** 가이드 모드 위상순서 = storylineStage(11단계) 인덱스 정렬 후 노드 topo 안정화. */
export function guidedOrder(): NodeId[] { /* sort by storyOrder, then topoSort within ties */ }
```

### 2-C. 실행 슬라이스 (`useOrchestrationStore.ts`)

```ts
type RunMode = "guided" | "standalone" | "selective" | "profile";
type NodeRunState =
  | "idle" | "queued" | "running" | "done"
  | "skipped-fresh" | "skipped-unavailable" | "needs-input" | "error";

interface NodeResult {
  state: NodeRunState;
  verifyStatus: "pass" | "warn" | "fail" | null;     // /verify/analysis 결과
  grounding: Record<string, "ok" | "unavailable">;    // 슬롯별 그라운딩 정직표기
  chargedKrw: number;                                  // charge_service 결과
  inputSignature: string | null;                       // 신선분 판정용(moduleKey=null 노드)
  at: number | null;
}

interface OrchestrationState {
  runMode: RunMode;
  picked: Record<NodeId, boolean>;                     // selective 선택집합(controlled)
  activeProfileId: string | null;                       // profile 모드
  nodeOrder: NodeId[];                                  // [graft C] 가이드/프로필 순서 재배열
  plan: NodeId[];                                       // computeClosure → topoSort 결과(미리보기·실행)
  nodeResult: Record<NodeId, NodeResult>;
  nodeUpdatedAt: Partial<Record<NodeId, number>>;       // moduleKey=null 노드 staleness 파생
  customProfiles: WorkflowProfile[];                    // 영속 대상(§4)

  // [graft C] 프로젝트별 복원 — store migrate 미접촉
  byProject: Record<string, {                           // projectId → 모드/선택/순서 스냅샷
    runMode: RunMode; picked: Record<NodeId, boolean>;
    activeProfileId: string | null; nodeOrder: NodeId[];
  }>;

  // ── 핵심 메서드 ──
  buildPlan: (mode: RunMode, seed?: NodeId[]) => RunStep[];   // 폐포+topo+신선스킵+과금표시
  runPlan: (opts?: { force?: boolean }) => Promise<void>;     // 4모드 공통 실행 코어
  runNode: (id: NodeId, opts?: { signature?: string }) => Promise<NodeResult>;  // 단일 노드(별도/모세혈관 공용)
  resolveInputs: (id: NodeId) => {
    ready: SsotSlot[]; missing: SsotSlot[]; autoCandidates: NodeId[];   // 자동해소 결과
  };
  syncProject: (projectId: string) => void;              // [graft C] byProject ↔ 현재 상태
}

interface RunStep {
  node: NodeId;
  reason: "selected" | "closure" | "guide";
  skipped: boolean;
  skipReason?: "fresh" | "unavailable";
  chargeable: boolean;          // skipped 아니고 billingKey 있을 때만 true
  estimatedKrw: number;         // preview-service-fee 합산용(관리자맵, 미설정 0)
}
```

#### `runPlan` 알고리즘 (4모드 공통 코어)

```
plan = topoSort(computeClosure(seedNodes(mode)))
levels = topoLevels(plan)                               // [graft B R1] 병렬 가능 레벨
for level of levels:                                     // 레벨 순차, 레벨 내 병렬
  await Promise.all(level.map(async id => {
    const mk = moduleKeyOf(id)
    // (1) 신선분 스킵 — 기존 store 셀렉터 위임(무회귀)
    if (!force && mk && hasResult(mk) && !ctx.isStale(mk))   → state="skipped-fresh"; return
    if (mk===null) staleByNode(id) 동일 판정(nodeUpdatedAt vs upstream max + signature)
    // (2) available 가드 — audit 미머지 시
    if (!node.available)                                     → state="skipped-unavailable"; return  // 0강제 금지, 정직고지
    // (3) 입력 자동해소
    const {missing, autoCandidates} = resolveInputs(id)
    if missing.length:
       standalone → InputResolveModal(수동입력 OR "업스트림 N개 자동실행" 동의)
       guided/selective/profile → 폐포가 보장(상류가 큐에서 먼저 실행됨)
       끝내 unavailable → state="skipped-unavailable"        // 0강제 금지, 정직고지
    // (4) 실행 = 노드 불변계약 5단계(§6) runner 래퍼
    res = await runNode(id, {signature})                     // (a)~(e)
    // (5) 과금 — runner 성공 후 단일 호출(중복방지). [선례 pipeline.py:130]
    if res.ok && node.billingKey:
       await charge_service(action: node.billingKey)         // ← 분석모듈 과금 공백 해소
    nodeResult[id]=res; if mk: interpreter가 update*Data로 store stamp
  }))
```

#### 모드별 `seedNodes`

- **가이드(guided)**: `seed = ["finance"]`(최종 출구) → 폐포 = 전노드 → `guidedOrder()`로 11단계 위상 안내. **일괄 강제실행 아님** — 단계별 CTA "다음 단계 실행"만 활성(`getNextRecommendedStage` L1118 + 노드 `nodeStale` 결합). 자동전체는 `onSelectAll`("⚡ 전체 자동분석") 옵션 버튼(MEMORY `feedback_modular_selection_default`: 선택형 기본·자동전체 옵션).
- **별도(standalone)**: `seed=[clickedNode]` → `runNode` 단독. `resolveInputs` 자동해소: (1)store SSOT(`readyCheck`) → (2)미확보 시 최소 업스트림 자동실행 **제안**(자동실행 금지, 동의 버튼) → (3)그래도 없으면 수동입력 폼(`manualPrompt`, provenanceGuarded면 `update*Data(data,{source:"user"})` 머지가드).
- **선택(selective)**: `seed = picked의 leaf` → `computeClosure(picked)` → topoSort. **신선분 스킵** → 실행분만 과금. `AnalysisModuleSelector`의 controlled `selected` 맵 = `picked`.
- **프로필(profile)**: `seed = profile.nodes` → 선택모드와 동일 파이프라인(`profile.order`를 `nodeOrder`로 주입).

#### isStale 신선분 스킵 — store 무수정 보강

```ts
function nodeStale(node: AnalysisNode, ctx): boolean {
  if (node.moduleKey) {
    const base = ctx.store.isStale(node.moduleKey);                 // 기존 SSOT 우선
    const firstReady = ctx.store.isReadyForFirstCompute(node.moduleKey);
    if (base || firstReady) return true;
  }
  // moduleKey=null(recommend/sales/audit) → 입력 시그니처 변화 감지
  const last = ctx.nodeResult[node.id];
  return !last || last.inputSignature !== currentSignature(node.id, ctx.store);
}
```
- `currentSignature` = `useStageAutoRecalc`의 `inputSignature` 게이트와 **동일 패턴**(과금/폭주 방지 재사용).
- moduleKey 매핑 노드는 기존 `isStale` 무한루프 방지 정책(최초 미산출=false) 그대로 상속.

### 2-D. 기존 자산과의 관계(무회귀)

- **`useStageAutoRecalc`**: 변경 없음. 노드 runner 성공 콜백이 `update*Data`를 호출(=훅 기대 계약)하므로 마운트된 다운스트림 컴포넌트는 기존대로 1회 자동재계산. 엔진 `runNode`와 중복방지: **동일 `inputSignature` 공유** → `lastSigRef`(L86)·`busyRef`(L84) 가드. 과금은 runner 성공 후 **엔진만 단일 charge_service**(훅은 과금 안 함).
- **`isStale`/`isReadyForFirstCompute`**: 엔진이 **소비만**. 정책 불변.
- **`snapshots`/persist**: `useProjectContextStore` **미접촉** → `version:1` 유지, migrate 불필요. 오케스트레이션 store는 자체 키 `propai-orchestration`(version 1). `partialize`로 `runPlan`/`nodeResult`/`picked`는 휘발, **영속 대상 = `customProfiles`·`byProject`·`activeProfileId`만**.
- **`charge_service`**: 라우터 `Depends`가 아니라 노드 실행 성공 직후 명시 호출(미배선 공백을 엔진이 메움). `billingKey`는 `stage:<name>` 규약 — 백엔드 **무수정**(L508 디스패치 존재), 단가 미설정=0원=무료. **실배선 선례 `pipeline.py:130`**(노드 과금=기존 패턴 복제, 신규 아님).

---

## 3. AnalysisModuleSelector 일반화·확산

`AnalysisModuleSelector`는 **컴포넌트 무수정**(controlled·leaf집계·3-state 완성형, 실행/과금/closure 안 함). 레지스트리→옵션 변환 **어댑터**와 **얇은 컨테이너**만 신설.

### 3-A. 레지스트리→옵션 빌더 (신규 `lib/orchestration/selector-adapter.ts`)

```ts
import { NODES } from "./node-registry";
import type { AnalysisModuleOption } from "@/components/common/AnalysisModuleSelector";
import type { NodeId } from "./types";

/** 레지스트리 노드 → AnalysisModuleOption. coinCost는 관리자 설정(module_fees) 주입. */
export function nodesToOptions(
  nodeIds: NodeId[],
  feeOf: (billingKey: string) => number,    // = balance.module_fees?.[k] ?? 0  (★하드코딩 금지)
  ctx: { isStale; hasResult; moduleKeyOf; isClosureForced: (id) => boolean },
): AnalysisModuleOption[] {
  // storylineStage로 그룹핑 → 부모(분류)/자식(항목) 3-state
  // key = NodeId
  // coinCost = feeOf(node.billingKey) ?? 0   (analysis_module_fees 맵, 미설정 0=무료)
  // required = "land"(부지=모든 분석 사실근거 루트)
  // locked = !node.available (audit 심의엔진 미머지 시) → lockedCtaLabel:"심의엔진 연동 예정"
  //          OR isClosureForced(id) → 의존 자동포함(체크 불가) lockedCtaLabel:"의존 항목(자동 포함)"
  // description = 신선분이면 "최신(스킵)" / unavailable이면 정직표기
  // estimatedSeconds = 노드 메타(없으면 미표기)
}
```

**매핑 규칙**:
- `coinCost` = `balance.module_fees[billingKey]`(MarketInsights `fee()` L286 패턴 재사용. 미설정 0=무료, 하드코딩 금지 — MEMORY `feedback_billing_admin_default_free`).
- `required` = `land`. `locked` = `audit`(미머지) 또는 폐포 강제 노드.
- `children` = `storylineStage` 그룹(예: feasibility 그룹 = sales/qto/feasibility/finance) → 부모 3-state.

### 3-B. 컨테이너 (신규 `components/orchestration/OrchestratorPanel.tsx`)

```tsx
<RunModeSwitcher value={runMode} onChange={setRunMode} />   {/* 가이드/별도/선택/프로필 */}
<AnalysisModuleSelector
  modules={nodesToOptions(scopeNodes, fee, ctx)}
  selected={picked}                                          {/* controlled */}
  onChange={setPicked}                                       {/* onChange→폐포 재계산→locked 재배지 */}
  onRun={() => runPlan({ force: false })}                    {/* 선택분만, 신선분 스킵 */}
  onSelectAll={() => runPlan({ force: true })}               {/* "⚡ 전체 자동분석" 옵션 */}
  runDisabled={insufficient}
  unlimited={balance?.unlimited}
/>
<PlanPreview plan={buildPlan(runMode, selectedNodes)} />     {/* 폐포·신선스킵·과금합계 미리보기 */}
<RunProgressTimeline nodeResult={nodeResult} plan={plan} />  {/* [graft C] 실행 진행 시각화 */}
```

### 3-C. 확산 전략(무회귀)

- 기존 채택 2곳(MarketInsights·OperationsIntelligence)은 그대로 두고, 신규 컨테이너를 9노드 + LifecycleStageViews에 우선 배선.
- 기존 2곳은 B3에서 **1곳씩** `nodesToOptions` 호출로 점진 교체(빅뱅 금지). `AnalysisModuleOption` 인터페이스 불변 → 회귀 0.
- 신규 워크스페이스 페이지는 처음부터 `OrchestratorPanel` 임베드.

---

## 4. 프로필 모드 데이터모델 (프리셋4 + 커스텀)

### 4-A. 스키마 (신규 `lib/orchestration/profiles.ts`)

```ts
export type ProfileId = string;   // 프리셋="preset:*", 커스텀=uuid

export interface WorkflowProfile {
  id: ProfileId;
  label: string;
  description: string;
  builtin: boolean;                       // 프리셋=true(수정·삭제 불가, 복제만)
  nodes: NodeId[];                         // 선택 시드(폐포는 엔진이 자동 확장)
  order: NodeId[];                         // [graft C] 실행/표시 순서(드래그 재배열 보존)
  defaultMode: "guided" | "selective";    // [graft C] 진입 시 모드
  autoRunUpstream: boolean;                // standalone 폴백 시 업스트림 자동실행 동의 기본
  createdAt: number;
}

export const PRESET_PROFILES: WorkflowProfile[] = [
  { id:"preset:landowner-quick", label:"지주 빠른검토", builtin:true,
    nodes:["land","legal","recommend","sales"], order:["land","legal","recommend","sales"],
    defaultMode:"selective", autoRunUpstream:true,
    description:"토지·법률·개발방식·분양성만 빠르게(수지·금융 제외)" },
  { id:"preset:developer-full", label:"디벨로퍼 풀패키지", builtin:true,
    nodes:["finance"],   // 폐포=전노드 → 가이드 전 스토리라인
    order:["land","legal","recommend","design","audit","sales","qto","feasibility","finance"],
    defaultMode:"guided", autoRunUpstream:true,
    description:"전 스토리라인 가이드(토지→금융+심의+적산)" },
  { id:"preset:pf-finance", label:"PF·금융중심", builtin:true,
    nodes:["feasibility","finance"],   // 폐포=land/design/qto/sales까지 자동충족
    order:["land","design","qto","sales","feasibility","finance"],
    defaultMode:"guided", autoRunUpstream:true,
    description:"수지·PF금융 중심(상류 자동충족)" },
  { id:"preset:architect", label:"설계사", builtin:true,
    nodes:["design","audit","qto"], order:["land","legal","recommend","design","audit","qto"],
    defaultMode:"selective", autoRunUpstream:true,
    description:"설계·심의·적산 중심" },
];
```

### 4-B. persist / 적용 / 복원

- **영속 위치**: 오케스트레이션 store `partialize`. 프리셋은 코드 상수(persist 안 함). `customProfiles`만 영속.
- **적용**: `applyProfile(id)` → `picked = profile.nodes` 시드 + `nodeOrder = profile.order` + `runMode = profile.defaultMode` → `buildPlan`.
- **커스텀 저장**: "현재 선택+순서를 워크플로우로 저장" → 현 `picked` 폐포를 `nodes`로, `nodeOrder`를 `order`로 캡처 → `customProfiles.push`(builtin:false). builtin 복제 후 편집 허용.
- **확장성**: 향후 노드 파라미터(분석옵션)까지 프로필에 넣을 자리 예약. 백엔드 팀공유 프로필은 동일 스키마 `/profiles` CRUD 추가만(B 후속).

---

## 5. 라이프사이클 / 목업 3탭 통합

### 5-A. 단계↔노드 어댑터 (신규 `lib/orchestration/stage-node-map.ts`)

식별자 3집합 봉합 — store `LIFECYCLE_STAGES`(11, kebab), `STAGE_META`(11 재export), `LifecycleStageViews` `StageType`(8, snake):

| LifecycleStage(11) | 노드(들) | StageType(8) 탭 |
|---|---|---|
| site-analysis | land | site_analysis |
| legal | legal, recommend | legal_compliance |
| design | design, audit | design_ai |
| bim | (design의 BIM 산출) | — (design_ai 포함) |
| construction | qto | construction |
| feasibility | sales, feasibility | feasibility |
| finance | finance | feasibility(금융 카드) |
| esg | (esg 노드 = B3 추가) | esg_dashboard |
| permit | recommend(`/permits/ai-analysis`) | permit_portal |
| report | (보고서=reportContract 수집) | — |
| operations | (운영 노드 = B3 이후) | operations |

```ts
export const STAGE_TO_NODES: Record<LifecycleStage, NodeId[]>;   // 진행레일 상태 집계
export const NODE_TO_STAGETYPE: Record<NodeId, StageType | null>; // LifecycleStageViews 탭 배선
// node.storylineStage가 SSOT, 이 맵은 미러(dev-time assert로 일관성 검사)
```

### 5-B. 가이드 모드 = 라이프사이클을 레지스트리로 구동

- **`ProjectLifecyclePipeline.tsx`**: 진행레일(11노드 Link, 네비) **구조 유지**. **추가**: 각 단계 노드 상태(idle/running/done/stale/blocked)를 `STAGE_TO_NODES` + orchestrator `nodeResult`로 읽어 배지 표시(additive, `getStageStatus`/`getNextRecommendedStage` 보존). `next` 판정에 `resolveInputs(nextNode).missing` 없을 때만 활성(막다른길 방지). 라우트 매핑은 `STAGE_META.route` 유지.

### 5-C. 목업 3탭 처리 (무목업 원칙)

| 탭 | 현재(소스) | Phase B 배선 |
|---|---|---|
| `legal_compliance` (L269 하드코딩 체크리스트) | 목업 | `legal` 노드 runner(`/regulation/analyze`) 결과 — store `complianceData` 실값(위반/근거)으로 체크리스트 교체. `recommend` 결과(개발방식 가능성) 카드 추가. 미실행 시 "법규검토 실행" CTA(목업 표시 금지) |
| `permit_portal` (L362 전부 하드코딩) | 목업 | `recommend` 노드의 `/permits/ai-analysis` 보조 산출 + `/development-methods` 결과 배선. 미확보 시 진행률 0 / "인허가 분석 미실행" 정직 placeholder(더미수치 제거) |
| `operations` (L399 하드코딩 KPI/IoT) | 목업 | 운영 노드 B3 전까지 없음 → **"운영 분석 준비중(데이터 없음)" 정직 placeholder**로 교체(하드코딩 KPI/IoT 제거, 0 강제 금지). B3 운영 노드 추가 시 배선 |

탭 결과 소스: 기존 `store siteAnalysis/designData/esgData` + 신규 `useOrchestrationStore.nodeResult[id]`(산출·verifyStatus·grounding). 하단 CTA(L447) 유지. 실위젯(feasibility→FeasibilitySimulationWidget L234, construction→CostAndQuantityDashboard L235) 그대로.

### 5-D. 심의(핵심1) 경계 — 미접촉 어댑터

`audit` 노드는 `services/deliberation/**`·`routers/deliberation.py`·`components/deliberation/**` **미접촉**. 엔진 main머지 전까지 `available:false`(selector locked, `state:"skipped-unavailable"` 정직). 머지 후 runner를 `/deliberation/analyze`(BFF) 얇은 어댑터로 교체 — `MirrorAnalysisInput`에 `design`/`land` SSOT 전달(모세혈관), 결과는 `nodeResult` 기록 + `markStageComplete("design")` 신호만(`engine_run_binding` 계약 준수).

---

## 6. 노드 불변계약 5단계 — 강제 방법

각 노드 실행은 L2 엔진 `runNode()`가 **순서 강제**:

1. **(a) 그라운딩**: `groundingSources`의 공공데이터 실값 수집 → 미확보 슬롯은 `grounding[slot]="unavailable"`(0 강제 **금지**). 입력은 §2-C `resolveInputs`로 SSOT 자동주입(상류 산출이 하류 runner body의 `context` = 모세혈관).
2. **(b) 전담 interpreter**: runner가 `expertInterpreter` 경유(백엔드 `BaseInterpreter` 단일경유 = LLM 계측·과금 자동, MEMORY `project_billing_metering` 정합).
3. **(c) expert-panel**: `expertPanel:true` 노드만 `POST /expert-panel/analyze`(lens 전달) 다관점 협업 — land/recommend/legal/sales/feasibility/finance(audit은 엔진 내부).
4. **(d) 가드**: `verify.crossValidate` → `trust.cross_validate`(상류 사실근거 교차검증), `verify.verifyAnalysis` → `POST /verify/analysis`(`VerificationBadge` autoRun 재사용) → pass/warn/fail을 `nodeResult.verifyStatus`에.
5. **(e) 정직 고지**: 결과를 `update*Data`(provenance `source:"auto"`) 기록 + `grounding`/`verifyStatus`를 `NodeRunCard`에 배지 표시(unavailable·provenance 정직).

### 강제 인프라 — `scripts/lint-node-registry.ts` (B의 결정적 자산, CI 상주)

빌드타임 검사로 노드 추가 시 계약 위반을 **컴파일타임 차단**:
- **사이클 탐지**: `upstream` 순환 → fail(topoSort throw 사전 방지).
- **미정의 upstream**: `upstream`이 존재하지 않는 NodeId 참조 → fail.
- **중복 billingKey**: 동일 `stage:<name>` 중복 → fail.
- **계약 5단계 누락**: `verify.crossValidate`/`verify.verifyAnalysis` 누락, 판단분기 노드인데 `expertPanel:false`, `groundingSources` 빈 배열, `reportContract.unavailableLabel` 빈 문자열 → fail.
- **MODULE_UPSTREAM 드리프트**: `moduleKey` 보유 노드의 노드폐포 ⊉ `MODULE_UPSTREAM[moduleKey]` 폐포 → warn(개발 중 경고).
- **stage-node-map 일관성**: `node.storylineStage` vs `STAGE_TO_NODES` 역매핑 불일치 → fail.

CI 게이트(`package.json` lint 스크립트에 추가) + B1부터 상주.

---

## 7. 신규/변경 파일 목록 + 성장루프(B1..B7)

### 신규 파일 (전부 additive)
```
apps/web/lib/orchestration/types.ts             # AnalysisNode·NodeId·SsotSlot·Lens·ReportContract·SsotInputSpec
apps/web/lib/orchestration/node-registry.ts      # NODES: AnalysisNode[] (9노드 SSOT)
apps/web/lib/orchestration/dependency-graph.ts   # computeClosure·topoSort·topoLevels·nodeStale·currentSignature·moduleKeyOf·guidedOrder
apps/web/lib/orchestration/stage-node-map.ts      # STAGE_TO_NODES·NODE_TO_STAGETYPE 어댑터
apps/web/lib/orchestration/selector-adapter.ts    # nodesToOptions(레지스트리→AnalysisModuleOption)
apps/web/lib/orchestration/profiles.ts            # PRESET_PROFILES·WorkflowProfile
apps/web/store/useOrchestrationStore.ts           # runMode·picked·plan·nodeResult·byProject·runPlan·runNode·resolveInputs
apps/web/hooks/useNodeRunner.ts                   # 단일 노드 실행 캡슐(runner→interpreter→expert-panel→verify→store 환류·입력자동해소)
apps/web/components/orchestration/OrchestratorPanel.tsx    # 모드스위처+Selector+PlanPreview+Timeline 컨테이너
apps/web/components/orchestration/RunModeSwitcher.tsx      # [graft C] 가이드/별도/선택/프로필 탭
apps/web/components/orchestration/PlanPreview.tsx          # 폐포·신선스킵·과금합계 미리보기
apps/web/components/orchestration/RunProgressTimeline.tsx  # [graft C] 실행 진행 시각화(폐포·스킵·과금·verdict)
apps/web/components/orchestration/InputResolveModal.tsx    # standalone 입력 자동해소/수동입력 폴백
apps/web/components/orchestration/ProfileManager.tsx       # 프리셋4 + 커스텀 저장/복제
apps/web/components/orchestration/NodeOrderEditor.tsx      # [graft C] 순서 드래그 재배열
apps/web/components/orchestration/NodeRunCard.tsx          # 노드 결과 카드(provenance/unavailable 정직고지·verify 배지)
scripts/lint-node-registry.ts                     # 사이클·계약5단계·중복billingKey·드리프트 빌드타임 검사(CI)
```

### 변경 파일 (소비 리팩토링 — additive)
```
apps/web/components/projects/ProjectLifecyclePipeline.tsx  # 단계 노드상태 배지(getStageStatus·route 보존)
apps/web/components/projects/LifecycleStageViews.tsx       # legal/permit 탭 노드 배선, operations 정직 placeholder
apps/web/components/operations/MarketInsightsWorkspaceClient.tsx        # 수기옵션→nodesToOptions (B3, ★정확경로)
apps/web/components/analytics/OperationsIntelligenceWorkspaceClient.tsx # 수기옵션→nodesToOptions (B3, ★정확경로)
```

### 미접촉 (경계)
```
apps/web/store/useProjectContextStore.ts          # ModuleKey·MODULE_UPSTREAM·isStale·persist version:1·migrate 불변
apps/web/hooks/useStageAutoRecalc.ts               # 무수정(래핑만)
apps/web/components/common/AnalysisModuleSelector.tsx  # props 불변(래핑만)
apps/api/app/core/billing.py, services/billing/billing_service.py  # stage:<name> 규약 존재 — 관리자 단가 등록만
services/deliberation/**, routers/deliberation.py, components/deliberation/**  # 핵심1 타세션 소유
```

### 성장루프 점증 단계 (각 단계 독립 배포·라이브검증·무회귀 경계 명시)

| 단계 | 산출물 | 검증 | 무회귀 경계 |
|------|--------|------|-------------|
| **B1 — 레지스트리+그래프 골격** | `types.ts`/`node-registry.ts`(9노드)/`dependency-graph.ts`/`stage-node-map.ts`/`lint-node-registry.ts` | 순수함수 단위테스트(폐포 finance→전노드, topo, topoLevels, 사이클 throw, signature) + lint CI 통과 | UI/실행 0 → 무회귀 0. 기존 store/훅 미접촉 |
| **B2 — 실행 슬라이스** | `useOrchestrationStore.ts`(runPlan/runNode/resolveInputs) + `useNodeRunner.ts` + 별도 persist(byProject) | land/feasibility 2노드 E2E 라이브검증(의정부224류 특이부지 그라운딩·정직고지·charge_service `stage:` 1회) | 기존 store **읽기 소비만**. 과금은 백엔드 단일(미설정 0=무료) |
| **B3 — 별도 모드 + selector 일반화** | `OrchestratorPanel`/`RunModeSwitcher`/`PlanPreview`/`NodeRunCard`/`InputResolveModal` + `selector-adapter`. MarketInsights→`nodesToOptions` 교체(1곳) | 선택→폐포→신선스킵→선택분만 과금 라이브검증. 자동해소→업스트림제안/수동폴백 검증 | `AnalysisModuleOption` 불변. MarketInsights 1곳만(빅뱅 금지) |
| **B4 — 가이드 모드 + 라이프사이클 통합** | `ProjectLifecyclePipeline` 노드 배지, `LifecycleStageViews` legal/permit 노드 배선·operations 정직화 | 가이드 단계별 CTA 실행, 목업 3탭 제거 확인(더미수치 0), `getNextRecommendedStage` 정합 | 진행레일 구조·route·CTA 보존. 목업→실행CTA/정직 placeholder |
| **B5 — 프로필 모드** | `profiles.ts`/`ProfileManager`/`NodeOrderEditor` + 커스텀 persist + 프로젝트별 복원(byProject) | 프리셋4 closure·실행 검증(landowner-quick는 finance 폐포 미포함, developer-full=전노드). 순서 드래그·커스텀 저장/복원 | store migrate 미접촉(byProject는 별도 store). OperationsIntelligence 교체(1곳) |
| **B6 — 전모듈 확산 + 노드 확충** | esg/permit/operations 노드 추가(B3 운영탭 배선), recommend/design/sales/qto/feasibility/finance runner+expert-panel/verify 전수 | 9+노드 전수 (그라운딩→interpreter→expert-panel→cross_validate/verify→정직고지) E2E | lint가 신규 노드 계약 강제. 1노드씩 게이트 |
| **B7 — 심의(audit) 승격** | 심의엔진 main머지 후 `audit` runner를 `/deliberation/analyze` BFF 어댑터로 교체(`available:true` unlock) | 심의 노드 동작·`engine_run_binding` 계약 라이브검증 | 얇은 어댑터만. services/routers/components deliberation 미접촉 |

각 단계 종료 게이트: `code-reviewer` 스폰 리뷰 + 린트 + 빌드 + 라이브검증(무목업·무회귀 확인). 레지스트리 lint는 B1부터 CI 상주(MEMORY `feedback_completion_gate`·`feedback_no_mockup_verify`).

---

## 8. 단선·병목 위험과 완화

| # | 위험 | 영향 | 완화 |
|---|------|------|------|
| R1 | 순차 실행 단선 — guided 풀패키지 9노드 직렬 | UX 지연 | `topoLevels` 레벨별 그룹 → 동일 레벨(legal·sales 등 상호 비의존) `Promise.all` 병렬(CLAUDE.md "2+ 독립작업 병렬"). verify는 VerificationBadge 캐싱 재사용 |
| R2 | finance 폐포 과확장 — finance→전노드 | PF중심 프로필이 사실상 풀패키지 | 의도된 동작(금융=상류 사실근거 필수). **신선분 스킵**으로 산출분 재실행·재과금 안 함 |
| R3 | sales↔feasibility 동일 슬롯 경합 | 매출 덮어쓰기 | `updateFeasibilityData` merge 부분패치(sales=매출만, partial:true), feasibility=full ROI. 노드 엣지 `sales→feasibility` 순서 강제. `nodeStale` signature 보강 |
| R4 | 이중 자동재계산 — `useStageAutoRecalc`(마운트) + 엔진 `runPlan` | 중복 호출·이중 과금 | 동일 `inputSignature` 공유 → `lastSigRef`/`busyRef` 가드. 과금은 runner 성공 후 **엔진만 단일 charge_service**(훅은 과금 안 함) |
| R5 | 사이클 유입 — 향후 노드 추가 시 순환 | topoSort throw | `lint-node-registry.ts` 빌드타임 사이클·미정의upstream·중복billingKey·계약누락 사전탐지(CI 게이트) |
| R6 | moduleKey=null 노드 staleness 누락 | recommend/sales/audit stale 미감지 | L2 `nodeUpdatedAt[NodeId]` + `currentSignature` 파생 판정(upstream 노드 타임스탬프 max 비교) |
| R7 | persist shape 충돌 | 기존 사용자 데이터 손상·계정누출 | 오케스트레이션 store **별도 키**(propai-orchestration). useProjectContextStore version:1·`purifyPersistedContextState` migrate **미접촉**(MEMORY `project_account_isolation` 보안경로 회피). nodeResult 영속 불필요(휘발) |
| R8 | 과금 회귀 — 기존 무료 동작이 과금됨 | 신뢰 훼손 | billingKey 미설정(`analysis_module_fees` 빈dict)=0원=무료. `preview-service-fee` 선표시 후 동의 실행. 가이드 CTA는 단계별 `stage:<name>` 단가만(미설정 0) |
| R9 | 자동 업스트림 실행이 사용자 의도 침범 | standalone 무단 실행 | 자동실행 금지 — "업스트림 자동실행 제안" 동의 버튼만(무자동전체분석 원칙) |
| R10 | provenance 가드 미적용 모듈 [graft A] | feasibility/finance/compliance 수동입력 보존 안 됨 | 해당 노드는 ProvenanceModule(5개) 밖 → merge가드 없음. `SsotInputSpec.provenanceGuarded:false` 정직표기. 상류 SSOT 의존 강해 수동입력 빈도 낮음(InputResolveModal에 명시) |
| R11 | audit 엔진 미머지 | 노드 깨짐 | `available:false` locked, 어댑터만, 미접촉. `state:"skipped-unavailable"` 정직 |
| R12 | 목업 제거가 화면 공백 | UX 후퇴 | 0 강제 대신 "미실행/준비중" 정직 카드 + 실행 CTA(AnalysisModuleSelector locked 패턴 준용) |
| R13 | 식별자 4중 불일치(NodeId/ModuleKey/LifecycleStage/StageType) | 배선 깨짐 | `stage-node-map.ts` 전수 `Record<...>` 매핑(누락 컴파일 차단) + lint 일관성 검사 |

**무회귀 코어 원칙**: (1) `ModuleKey`·`MODULE_UPSTREAM`·`isStale`·`useStageAutoRecalc`·`AnalysisModuleSelector` props·persist version:1·migrate **전부 불변(읽기 소비만)**. (2) 신규는 `lib/orchestration/**`·`hooks/useNodeRunner.ts`·`components/orchestration/**`로 격리. (3) 기존 2 adopter·13페이지 점진 마이그레이션(1곳씩 게이트). (4) 백엔드 무수정(charge_service `stage:` 규약·`pipeline.py:130` 선례). (5) 레지스트리 lint CI 상주로 구조 회귀 방지.

---

**핵심 요약**: 데이터 SSOT(`useProjectContextStore`, version:1·migrate)는 불변 유지하고, 오케스트레이션을 *정적 레지스트리(9노드) + 순수 그래프 엔진 + 별도 실행 store(propai-orchestration)*로 분리한다. `MODULE_UPSTREAM`(7키)을 9노드로 정밀화한 노드 그래프가 폐포·topo의 SSOT가 되고, `isStale`/`isReadyForFirstCompute`/`useStageAutoRecalc`는 읽기 소비, 과금은 `charge_service("stage:<name>")`(미설정 0=무료, `pipeline.py:130` 선례)로 배선해 분석모듈 과금 공백을 해소한다. `AnalysisModuleSelector`는 레지스트리 구동으로 전모듈 확산, 목업 3탭(legal/permit/operations)은 노드 결과 배선 또는 정직 placeholder로 교체한다. graft로 프로필 `order`/`defaultMode`·RunProgressTimeline·프로젝트별 복원(byProject, store migrate 미접촉)·provenance 한계 정직고지를 흡수했고, `lint-node-registry.ts`가 노드 불변계약 5단계를 빌드타임에 강제한다.
