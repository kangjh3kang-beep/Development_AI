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
  esgData: EsgData | null;
  complianceData: ComplianceData | null;
  completedStages: string[];
  currentStage: string | null;
  analysisResults: AnalysisResult[];
}

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
  esgData: EsgData | null;
  complianceData: ComplianceData | null;

  // Analysis history
  analysisResults: AnalysisResult[];

  // 프로젝트별 분석 스냅샷(영속) — 전환/재선택 시 복원
  snapshots: Record<string, ProjectSnapshot>;

  // Actions
  setProject: (id: string, name: string, status: string) => void;
  clearProject: () => void;

  updateSiteAnalysis: (data: Partial<SiteAnalysisData>) => void;
  updateDesignData: (data: DesignData) => void;
  updateFeasibilityData: (data: FeasibilityData) => void;
  updateEsgData: (data: EsgData) => void;
  updateComplianceData: (data: ComplianceData) => void;

  markStageComplete: (stage: string) => void;
  setCurrentStage: (stage: string) => void;
  addAnalysisResult: (result: AnalysisResult) => void;

  // Computed
  getNextRecommendedStage: () => string | null;
}

/* ── Initial cross-module state ── */

const INITIAL_CROSS_MODULE = {
  siteAnalysis: null as SiteAnalysisData | null,
  designData: null as DesignData | null,
  feasibilityData: null as FeasibilityData | null,
  esgData: null as EsgData | null,
  complianceData: null as ComplianceData | null,
};

/** 현재 cross-module 상태를 스냅샷으로 추출 */
function snapOf(s: ProjectContextState): ProjectSnapshot {
  return {
    siteAnalysis: s.siteAnalysis,
    designData: s.designData,
    feasibilityData: s.feasibilityData,
    esgData: s.esgData,
    complianceData: s.complianceData,
    completedStages: s.completedStages,
    currentStage: s.currentStage,
    analysisResults: s.analysisResults,
  };
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

      /* ── Actions ── */

      setProject: (id, name, status) => {
        const prev = get();
        if (prev.projectId === id) {
          set({ projectId: id, projectName: name, projectStatus: status });
          return;
        }
        // 전환 전, 현재 프로젝트 상태를 스냅샷에 보존
        const snapshots = prev.projectId
          ? { ...prev.snapshots, [prev.projectId]: snapOf(prev) }
          : prev.snapshots;
        // 대상 프로젝트의 이전 분석이 있으면 복원, 없으면 초기화
        const snap = snapshots[id];
        set({
          projectId: id,
          projectName: name,
          projectStatus: status,
          snapshots,
          ...(snap
            ? {
                siteAnalysis: snap.siteAnalysis,
                designData: snap.designData,
                feasibilityData: snap.feasibilityData,
                esgData: snap.esgData,
                complianceData: snap.complianceData,
                completedStages: snap.completedStages ?? [],
                currentStage: snap.currentStage ?? null,
                analysisResults: snap.analysisResults ?? [],
              }
            : {
                completedStages: [],
                currentStage: null,
                analysisResults: [],
                ...INITIAL_CROSS_MODULE,
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
          }),
        );
      },

      updateDesignData: (data) => {
        set((state) => withSnap(state, { designData: data }));
      },

      updateFeasibilityData: (data) => {
        set((state) => withSnap(state, { feasibilityData: data }));
      },

      updateEsgData: (data) => {
        set((state) => withSnap(state, { esgData: data }));
      },

      updateComplianceData: (data) => {
        set((state) => withSnap(state, { complianceData: data }));
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
    }),
    {
      name: "propai-project-context",
    },
  ),
);

export { LIFECYCLE_STAGES };
export type {
  AnalysisResult,
  SiteAnalysisData,
  DesignData,
  FeasibilityData,
  EsgData,
  ComplianceData,
};
