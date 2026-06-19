// 분석 오케스트레이션 — 노드 스키마(L0 레지스트리 타입 SSOT)
// Phase B 블루프린트 §1-A 정합. 이 파일은 useProjectContextStore를 "타입만" 가져온다
// (런타임 의존 0). 데이터 SSOT(store)는 불변, 오케스트레이션은 별도 레이어다.
//
// 쉬운 설명: 분석 "노드"는 화면에서 한 번에 실행하는 분석 단위다(예: 토지분석·법규검토).
// 각 노드가 "무엇을 읽고(입력)", "무엇을 만들고(출력)", "어느 백엔드를 부르는지(runner)",
// "얼마를 과금하는지(billingKey)"를 한 곳에 적어 두는 게 이 타입들의 목적이다.

import type {
  ModuleKey,
  LifecycleStage,
  ProjectContextState,
} from "@/store/useProjectContextStore";

/**
 * 노드가 읽고/쓰는 SSOT 데이터 슬롯 이름.
 * useProjectContextStore의 데이터 필드명과 정합한다.
 * finance는 별도 데이터 필드가 없고 markFinanceUpdated() 스탬프만 남기므로 "financeStamp"로 표기.
 */
export type SsotSlot =
  | "siteAnalysis"
  | "designData"
  | "costData"
  | "feasibilityData"
  | "esgData"
  | "complianceData"
  | "financeStamp";

/**
 * 노드 식별자 — 실무 스토리라인 노드.
 * store의 ModuleKey(7개)와는 별개 집합이다(노드는 ModuleKey보다 세분화된 오케스트레이션 레이어).
 * (B6-3) "permit"(인허가 분석)을 표시·판단분기 전용 노드로 추가 — 기존 9노드 불변.
 */
export type NodeId =
  | "land"
  | "legal"
  | "recommend"
  | "design"
  | "audit"
  | "sales"
  | "qto"
  | "feasibility"
  | "finance"
  | "permit";

/** 전문가 패널 관점(다관점 협업 렌즈). */
export type Lens =
  | "site"
  | "legal"
  | "market"
  | "design"
  | "feasibility"
  | "esg"
  | "construction"
  | "permit"; // (B6-3) 인허가 분석 노드 전용 렌즈(7개 개발방식·상위법령↔조례 다관점)

/**
 * 보고서 참여 계약 — bank-report/generate·report 단계가 수집하는 섹션.
 * 이 노드가 보고서의 어느 섹션·필드를 채우는지, 그리고 데이터가 없을 때 어떻게 정직 표기할지 정의.
 */
export interface ReportContract {
  /** 보고서 섹션 키(미참여면 ""). */
  sectionKey: string;
  /** 이 노드가 채우는 보고서 필드(없으면 비참여). */
  fields: string[];
  /** unavailable 시 정직 표기 라벨(0 강제 금지 — 빈 문자열이면 lint fail). */
  unavailableLabel: string;
}

/**
 * 노드가 store 어디서 입력을 읽는지(자동해소) 스펙. standalone 모드의 입력 자동주입에 사용.
 * readyCheck는 store isModuleReady 기준을 재사용한다(무목업: 실데이터 유무로 판정).
 */
export interface SsotInputSpec {
  /** 읽을 store 슬롯. */
  slot: SsotSlot;
  /** 세부 필드(예: "landAreaSqm"). 없으면 슬롯 존재 여부로 판정. */
  field?: string;
  /** store 상태를 받아 이 입력이 준비됐는지 판정(isModuleReady 기준 재사용). */
  readyCheck: (s: ProjectContextState) => boolean;
  /** 자동해소 우선순위: SSOT 직접 → 업스트림 자동실행 제안 → 수동입력. */
  resolution: ("ssot" | "upstream-suggest" | "manual")[];
  /** SSOT 미확보 시 수동입력 라벨. */
  manualPrompt?: string;
  /**
   * provenance 머지가드 적용 여부(정직표기용).
   * feasibility/finance/compliance는 ProvenanceModule 밖이라 수동입력 merge가드가 없음 → false로 정직 표기.
   */
  provenanceGuarded: boolean;
}

/** 노드 산출 후 store로 되먹임(환류)하는 매핑. */
export interface SsotOutputSpec {
  /** 산출을 store에 쓰는 액션명(store의 update*Data / markFinanceUpdated). */
  updateAction:
    | "updateSiteAnalysis"
    | "updateDesignData"
    | "updateCostData"
    | "updateFeasibilityData"
    | "updateEsgData"
    | "updateComplianceData"
    | "markFinanceUpdated";
  /** 노드 산출은 항상 auto(머지가드가 user 입력값을 보존). */
  source: "auto";
  /** true=부분패치(예: sales→feasibilityData의 매출만 갱신). */
  partial?: boolean;
}

/** 분석 엔드포인트 호출 사양. bodyBuilder는 body를 만드는 함수/전략의 식별 문자열(실호출은 B2). */
export interface NodeRunner {
  method: "GET" | "POST";
  /** 백엔드 라우트 전체 경로(코드 대조 확인됨). */
  path: string;
  /** body 구성 전략 식별자(B2 useNodeRunner가 해석). */
  bodyBuilder: string;
}

/** 노드 불변계약 (d) 가드 — 교차검증·할루시네이션 검증 수행 여부. */
export interface NodeVerify {
  /** trust.cross_validate(상류 사실근거 교차검증) 수행 여부. */
  crossValidate: boolean;
  /** POST /verify/analysis(할루시네이션 검증) 수행 여부. */
  verifyAnalysis: boolean;
}

/** 9노드 정적 메타(불변). 단 하나의 진실 출처(SSOT). */
export interface AnalysisNode {
  id: NodeId;
  /** 한국어 노드명. */
  label: string;
  /** 스토리라인 위상순(가이드 기본 정렬·topoSort tiebreak). */
  storyOrder: number;
  /** LIFECYCLE_STAGES 11단계 매핑(가이드 진행레일). */
  storylineStage: LifecycleStage;
  /** staleness/폐포 매핑용 ModuleKey. null=파생/보조(legal·recommend·audit·sales는 별도 staleness). */
  moduleKey: ModuleKey | null;
  /** 노드 DAG(폐포 SSOT). MODULE_UPSTREAM의 노드레벨 정밀화. */
  upstream: NodeId[];

  /** 사실근거 입력(모세혈관 상류 컨텍스트). */
  ssotInputs: SsotInputSpec[];
  /** 산출 슬롯(하류 사실근거). [] = store 비기록(표시·검증 노드). */
  ssotOutputs: SsotOutputSpec[];

  /** 분석 엔드포인트. */
  runner: NodeRunner;
  /** 노드 전담 해석 LLM interpreter 클래스명(백엔드). 미존재/미확인이면 null. */
  expertInterpreter: string | null;
  /** true → POST /expert-panel/analyze 다관점 협업. */
  expertPanel: boolean;
  /** (d) 가드 계약. */
  verify: NodeVerify;
  /** charge_service action. "stage:<name>" 규약. null=과금없음. */
  billingKey: string | null;
  /** 보고서 참여 계약. */
  reportContract: ReportContract;
  /** 전문가 패널 렌즈. */
  lens: Lens;
  /** (a) 사실기반 그라운딩 출처(unavailable 정직 대상). */
  groundingSources: string[];
  /** false면 selector locked(audit=심의엔진 미머지 시). */
  available: boolean;
  /** 노드 아이콘 키. */
  icon: string;
}

// 재export(소비측 import 편의 — 런타임 값 아님, 타입만).
export type { ModuleKey, LifecycleStage, ProjectContextState };
