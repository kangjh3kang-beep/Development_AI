import { create } from "zustand";
import { persist } from "zustand/middleware";

/* ── Types ── */

interface AnalysisResult {
  module: string;
  completedAt: string;
  summary: Record<string, unknown>;
}

/** 개별 필지 정보 */
interface ParcelData {
  pnu: string;
  address: string;
  areaSqm: number;
  landCategory: string; // 지목
  ownerType: string;
}

/** 토지이용계획 규제 항목 */
interface LandUseDistrict {
  districtName: string;
  districtCode: string;
  conflictStatus: string;
}

/** 지자체 조례 정보 */
interface OrdinanceData {
  sido: string;
  sigungu: string | null;
  nationalBcr: number;
  nationalFar: number;
  ordinanceBcr: number | null;
  ordinanceFar: number | null;
  effectiveBcr: number;
  effectiveFar: number;
  source: string; // "법제처API" | "캐시DB" | "법정상한"
  legalBasis: string;
}

/** 건축물대장 정보 */
interface BuildingInfo {
  buildingName: string;
  mainPurpose: string;
  totalAreaSqm: number;
  groundFloors: number;
  structure: string;
  useApprovalDate: string;
}

/** 공시지가 정보 */
interface OfficialPriceData {
  pnu: string;
  year: number;
  pricePerSqm: number;
}

/** 기초 데이터 파이프라인 — 모든 모듈의 근간 */
interface SiteAnalysisData {
  // 기본 정보
  estimatedValue: number | null;
  landAreaSqm: number | null;
  zoneCode: string | null;
  address: string | null;
  pnu: string | null;

  // 다필지 정보 (LAYER 0) — 선택적 (점진적 확장)
  parcels?: ParcelData[];
  landUseDistricts?: LandUseDistrict[];
  ordinance?: OrdinanceData | null;
  buildingInfo?: BuildingInfo | null;
  officialPrices?: OfficialPriceData[];
  coordinates?: { lat: number; lon: number } | null;
  infrastructure?: Record<string, unknown> | null;
  dataSource?: string;
  fetchedAt?: string | null;
}

interface DesignData {
  totalGfaSqm: number | null;
  floorCount: number | null;
  buildingType: string | null;
  bcr: number | null;
  far: number | null;
}

interface FeasibilityData {
  totalCostWon: number | null;
  totalRevenueWon: number | null;
  profitRatePct: number | null;
  grade: string | null;
}

// 공사비 분석 결과(건축개요 기반) — 수지·사업성과 단일 데이터원으로 연동.
interface CostData {
  totalConstructionCostWon: number | null;
  perSqmWon: number | null;
  perPyeongWon: number | null;
  abovegroundWon: number | null;
  undergroundWon: number | null;
  landscapeWon: number | null;
  directWon: number | null;
  indirectWon: number | null;
  rangeMinWon: number | null;
  rangeMaxWon: number | null;
  source: string | null; // overview | bim
}

interface EsgData {
  embodiedCarbonKg: number | null;
  operationalCarbonKg: number | null;
  totalCarbonPerSqm: number | null;
}

interface ComplianceData {
  bcrCompliant: boolean | null;
  farCompliant: boolean | null;
  heightCompliant: boolean | null;
  violations: string[];
}

/* ── Lifecycle stage order ── */

const LIFECYCLE_STAGES = [
  "site-analysis",
  "legal",
  "design",
  "bim",
  "construction",
  "feasibility",
  "finance",
  "esg",
  "permit",
  "report",
] as const;

export type LifecycleStage = (typeof LIFECYCLE_STAGES)[number];

/* ── Per-project snapshot ──
   프로젝트별 분석 상태를 보관해, 프로젝트 전환/재선택 시 이전 분석을 복원한다.
   (이전 버그: setProject가 전환 시 모든 분석을 초기화 → 불러오기 시 0/없음으로 표시) */
interface ProjectSnapshot {
  siteAnalysis: SiteAnalysisData | null;
  designData: DesignData | null;
  feasibilityData: FeasibilityData | null;
  costData: CostData | null;
  esgData: EsgData | null;
  complianceData: ComplianceData | null;
  completedStages: string[];
  currentStage: string | null;
  analysisResults: AnalysisResult[];
  updatedAt: Partial<Record<ModuleKey, number>>;
}

/* ── Staleness / 의존성 모델 ──
   모듈별 최종 갱신 타임스탬프(epoch ms)를 보관해, 업스트림이 다운스트림보다 최신이면
   다운스트림을 "stale(재계산 필요)"로 판정한다. 순수 store는 API를 호출하지 않으며,
   마운트된 다운스트림 컴포넌트가 isStale를 보고 1회 자동재계산하거나 CTA를 띄운다. */
type ModuleKey =
  | "siteAnalysis"
  | "design"
  | "cost"
  | "feasibility"
  | "esg"
  | "compliance";

/** 다운스트림 모듈 → 직접 업스트림 의존성 */
const MODULE_UPSTREAM: Record<ModuleKey, ModuleKey[]> = {
  siteAnalysis: [],
  design: ["siteAnalysis"],
  cost: ["siteAnalysis", "design"],
  feasibility: ["siteAnalysis", "design", "cost"],
  esg: ["design"],
  compliance: ["siteAnalysis", "design"],
};

/* ── State interface ── */

export interface ProjectContextState {
  // Current project
  projectId: string | null;
  projectName: string;
  projectStatus: string;

  // Lifecycle stage tracking
  completedStages: string[];
  currentStage: string | null;

  // Cross-module data (capillary network)
  siteAnalysis: SiteAnalysisData | null;
  designData: DesignData | null;
  feasibilityData: FeasibilityData | null;
  costData: CostData | null;
  esgData: EsgData | null;
  complianceData: ComplianceData | null;

  // Analysis history
  analysisResults: AnalysisResult[];

  // 프로젝트별 분석 스냅샷(영속) — 전환/재선택 시 복원
  snapshots: Record<string, ProjectSnapshot>;

  // 모듈별 최종 갱신 타임스탬프(epoch ms) — staleness 판정용
  updatedAt: Partial<Record<ModuleKey, number>>;

  // Actions
  // projectId 단일 SSOT writer. name/status를 원자 저장하고, address가 주어지면
  // (스냅샷 복원이 우선이되) 신규/주소 미설정 프로젝트에 한해 siteAnalysis.address를 시드한다.
  setProject: (id: string, name: string, status: string, address?: string) => void;
  clearProject: () => void;

  updateSiteAnalysis: (data: Partial<SiteAnalysisData>) => void;
  updateDesignData: (data: DesignData) => void;
  updateFeasibilityData: (data: FeasibilityData) => void;
  updateCostData: (data: CostData) => void;
  updateEsgData: (data: EsgData) => void;
  updateComplianceData: (data: ComplianceData) => void;

  markStageComplete: (stage: string) => void;
  setCurrentStage: (stage: string) => void;
  addAnalysisResult: (result: AnalysisResult) => void;

  // Computed
  getNextRecommendedStage: () => string | null;
  // 다운스트림 모듈이 업스트림 갱신 이후로 재계산되지 않았으면 true.
  isStale: (downstream: ModuleKey) => boolean;
  // 수지분석에 실제 반영된 업스트림 단계 완성도(0~100, 무목업: 실데이터 유무 기반).
  feasibilityCompleteness: () => FeasibilityCompleteness;
}

/* ── 수지 완성도/신뢰도 파생 모델 ──
   업스트림 단계(부지/설계/공사비/금융)별로 "수지에 반영 가능한 실데이터가 있는가"를
   판정해 단계 칩과 반영도(%)를 산출한다. 무목업: 실데이터가 없으면 done=false. */
export interface FeasibilityCompletenessStage {
  key: "site" | "design" | "cost" | "finance";
  label: string;
  done: boolean;
  weightPct: number; // 누적 가중치(부지30/설계60/공사비85/금융100)
}
export interface FeasibilityCompleteness {
  stages: FeasibilityCompletenessStage[];
  pct: number; // 반영도(%) — 완료된 마지막 단계의 누적 가중치
}

/* ── Initial cross-module state ── */

const INITIAL_CROSS_MODULE = {
  siteAnalysis: null as SiteAnalysisData | null,
  designData: null as DesignData | null,
  feasibilityData: null as FeasibilityData | null,
  costData: null as CostData | null,
  esgData: null as EsgData | null,
  complianceData: null as ComplianceData | null,
};

/** 현재 cross-module 상태를 스냅샷으로 추출 */
function snapOf(s: ProjectContextState): ProjectSnapshot {
  return {
    siteAnalysis: s.siteAnalysis,
    designData: s.designData,
    feasibilityData: s.feasibilityData,
    costData: s.costData,
    esgData: s.esgData,
    complianceData: s.complianceData,
    completedStages: s.completedStages,
    currentStage: s.currentStage,
    analysisResults: s.analysisResults,
    updatedAt: s.updatedAt,
  };
}

/** 모듈 갱신 타임스탬프를 현재 시각으로 stamp한 updatedAt 객체를 반환. */
function stampedAt(
  state: ProjectContextState,
  key: ModuleKey,
): Partial<Record<ModuleKey, number>> {
  return { ...state.updatedAt, [key]: Date.now() };
}

/** patch 적용 결과를 현재 프로젝트 스냅샷에도 함께 영속화한다. */
function withSnap(
  state: ProjectContextState,
  patch: Partial<ProjectContextState>,
): Partial<ProjectContextState> {
  if (!state.projectId) return patch;
  const merged = { ...state, ...patch } as ProjectContextState;
  return {
    ...patch,
    snapshots: { ...state.snapshots, [state.projectId]: snapOf(merged) },
  };
}

/* ── Store ── */

export const useProjectContextStore = create<ProjectContextState>()(
  persist(
    (set, get) => ({
      // Current project
      projectId: null,
      projectName: "",
      projectStatus: "",

      // Lifecycle
      completedStages: [],
      currentStage: null,

      // Cross-module
      ...INITIAL_CROSS_MODULE,

      // Analysis history
      analysisResults: [],

      // 프로젝트별 스냅샷
      snapshots: {},

      // 모듈별 갱신 타임스탬프
      updatedAt: {},

      /* ── Actions ── */

      setProject: (id, name, status, address) => {
        const prev = get();
        // projectId가 동일하면 cross-module 데이터를 리셋하지 않는다(회귀 방지).
        // name/status만 원자 갱신하고, address가 주어졌고 아직 없으면 보조 시드.
        if (prev.projectId === id) {
          const patch: Partial<ProjectContextState> = {
            projectId: id,
            projectName: name,
            projectStatus: status,
          };
          if (address && !prev.siteAnalysis?.address) {
            patch.siteAnalysis = {
              ...(prev.siteAnalysis ?? {
                estimatedValue: null,
                landAreaSqm: null,
                zoneCode: null,
                pnu: null,
              }),
              address,
            } as SiteAnalysisData;
          }
          set(withSnap(prev, patch));
          return;
        }
        // 전환 전, 현재 프로젝트 상태를 스냅샷에 보존
        const snapshots = prev.projectId
          ? { ...prev.snapshots, [prev.projectId]: snapOf(prev) }
          : prev.snapshots;
        // 대상 프로젝트의 이전 분석이 있으면 복원, 없으면 초기화.
        // 구 hydrated 스냅샷 shape 호환을 위해 모든 필드에 ?? 폴백을 둔다.
        const snap = snapshots[id];
        const seededSite: SiteAnalysisData | null = address
          ? {
              estimatedValue: null,
              landAreaSqm: null,
              zoneCode: null,
              pnu: null,
              address,
            }
          : null;
        set({
          projectId: id,
          projectName: name,
          projectStatus: status,
          snapshots,
          ...(snap
            ? {
                // 복원 우선. 단, 복원 스냅샷에 주소가 없고 시드 주소가 있으면 보조 주입.
                siteAnalysis:
                  snap.siteAnalysis ??
                  (seededSite as SiteAnalysisData | null) ??
                  null,
                designData: snap.designData ?? null,
                feasibilityData: snap.feasibilityData ?? null,
                costData: snap.costData ?? null,
                esgData: snap.esgData ?? null,
                complianceData: snap.complianceData ?? null,
                completedStages: snap.completedStages ?? [],
                currentStage: snap.currentStage ?? null,
                analysisResults: snap.analysisResults ?? [],
                updatedAt: snap.updatedAt ?? {},
              }
            : {
                completedStages: [],
                currentStage: null,
                analysisResults: [],
                updatedAt: {},
                ...INITIAL_CROSS_MODULE,
                siteAnalysis: seededSite,
              }),
        });
      },

      clearProject: () => {
        const prev = get();
        // 현재 분석을 스냅샷에 보존(나중에 같은 프로젝트 재선택 시 복원)
        const snapshots = prev.projectId
          ? { ...prev.snapshots, [prev.projectId]: snapOf(prev) }
          : prev.snapshots;
        set({
          projectId: null,
          projectName: "",
          projectStatus: "",
          completedStages: [],
          currentStage: null,
          analysisResults: [],
          snapshots,
          updatedAt: {},
          ...INITIAL_CROSS_MODULE,
        });
      },

      updateSiteAnalysis: (data) => {
        set((state) =>
          withSnap(state, {
            siteAnalysis: {
              ...(state.siteAnalysis ?? {
                estimatedValue: null,
                landAreaSqm: null,
                zoneCode: null,
                address: null,
                pnu: null,
              }),
              ...data,
            } as SiteAnalysisData,
            updatedAt: stampedAt(state, "siteAnalysis"),
          }),
        );
      },

      updateDesignData: (data) => {
        set((state) =>
          withSnap(state, {
            designData: data,
            updatedAt: stampedAt(state, "design"),
          }),
        );
      },

      updateFeasibilityData: (data) => {
        set((state) =>
          withSnap(state, {
            feasibilityData: data,
            updatedAt: stampedAt(state, "feasibility"),
          }),
        );
      },
      updateCostData: (data) => {
        set((state) =>
          withSnap(state, {
            costData: data,
            updatedAt: stampedAt(state, "cost"),
          }),
        );
      },

      updateEsgData: (data) => {
        set((state) =>
          withSnap(state, {
            esgData: data,
            updatedAt: stampedAt(state, "esg"),
          }),
        );
      },

      updateComplianceData: (data) => {
        set((state) =>
          withSnap(state, {
            complianceData: data,
            updatedAt: stampedAt(state, "compliance"),
          }),
        );
      },

      markStageComplete: (stage) => {
        const prev = get();
        if (prev.completedStages.includes(stage)) return;
        set(withSnap(prev, { completedStages: [...prev.completedStages, stage] }));
      },

      setCurrentStage: (stage) => {
        set((state) => withSnap(state, { currentStage: stage }));
      },

      addAnalysisResult: (result) => {
        set((state) =>
          withSnap(state, { analysisResults: [...state.analysisResults, result] }),
        );
      },

      getNextRecommendedStage: () => {
        const { completedStages } = get();
        for (const stage of LIFECYCLE_STAGES) {
          if (!completedStages.includes(stage)) {
            return stage;
          }
        }
        return null;
      },

      isStale: (downstream) => {
        const { updatedAt } = get();
        const own = updatedAt[downstream];
        // 다운스트림이 아직 한 번도 계산되지 않았으면 stale로 보지 않는다
        // (자동재계산 무한 트리거 방지 — 최초 산출은 사용자/자동로드가 담당).
        if (own == null) return false;
        return MODULE_UPSTREAM[downstream].some((up) => {
          const upAt = updatedAt[up];
          return upAt != null && upAt > own;
        });
      },

      feasibilityCompleteness: () => {
        const s = get();
        // 단계별 실데이터 반영 판정(무목업): 값이 존재해야 done.
        const siteDone = !!(
          (s.siteAnalysis?.landAreaSqm && s.siteAnalysis.landAreaSqm > 0) ||
          s.siteAnalysis?.address
        );
        const designDone = !!(
          s.designData?.totalGfaSqm && s.designData.totalGfaSqm > 0
        );
        const costDone = !!(
          s.costData?.totalConstructionCostWon &&
          s.costData.totalConstructionCostWon > 0
        );
        const financeDone = !!(
          s.feasibilityData?.totalRevenueWon &&
          s.feasibilityData.totalRevenueWon > 0
        );
        const stages: FeasibilityCompletenessStage[] = [
          { key: "site", label: "부지", done: siteDone, weightPct: 30 },
          { key: "design", label: "설계", done: designDone, weightPct: 60 },
          { key: "cost", label: "공사비", done: costDone, weightPct: 85 },
          { key: "finance", label: "금융", done: financeDone, weightPct: 100 },
        ];
        // 반영도 = 연속으로 완료된 마지막 단계의 누적 가중치(중간 누락 시 직전까지).
        let pct = 0;
        for (const st of stages) {
          if (!st.done) break;
          pct = st.weightPct;
        }
        return { stages, pct };
      },
    }),
    {
      name: "propai-project-context",
    },
  ),
);

export { LIFECYCLE_STAGES };
export type { ModuleKey };
export type {
  AnalysisResult,
  SiteAnalysisData,
  DesignData,
  FeasibilityData,
  CostData,
  EsgData,
  ComplianceData,
};
