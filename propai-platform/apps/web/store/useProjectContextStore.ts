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

  // Actions
  setProject: (id: string, name: string, status: string) => void;
  clearProject: () => void;

  updateSiteAnalysis: (data: SiteAnalysisData) => void;
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

      /* ── Actions ── */

      setProject: (id, name, status) => {
        const prev = get();
        // If switching projects, reset cross-module data
        if (prev.projectId !== id) {
          set({
            projectId: id,
            projectName: name,
            projectStatus: status,
            completedStages: [],
            currentStage: null,
            analysisResults: [],
            ...INITIAL_CROSS_MODULE,
          });
        } else {
          set({ projectId: id, projectName: name, projectStatus: status });
        }
      },

      clearProject: () => {
        set({
          projectId: null,
          projectName: "",
          projectStatus: "",
          completedStages: [],
          currentStage: null,
          analysisResults: [],
          ...INITIAL_CROSS_MODULE,
        });
      },

      updateSiteAnalysis: (data) => {
        set({ siteAnalysis: data });
      },

      updateDesignData: (data) => {
        set({ designData: data });
      },

      updateFeasibilityData: (data) => {
        set({ feasibilityData: data });
      },

      updateEsgData: (data) => {
        set({ esgData: data });
      },

      updateComplianceData: (data) => {
        set({ complianceData: data });
      },

      markStageComplete: (stage) => {
        const prev = get();
        if (prev.completedStages.includes(stage)) return;
        set({
          completedStages: [...prev.completedStages, stage],
        });
      },

      setCurrentStage: (stage) => {
        set({ currentStage: stage });
      },

      addAnalysisResult: (result) => {
        set((state) => ({
          analysisResults: [...state.analysisResults, result],
        }));
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
